"""Grouped planning limits preserve detailed expenses and legacy backups."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import budget_groups, cloud_storage, portability, storage


class GroupedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(storage, 'DATABASE', Path(self.temp.name) / 'test.db'),
            patch.object(storage, 'BACKUPS', Path(self.temp.name) / 'backups'),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_default_categories_have_one_group_and_custom_categories_are_preserved(self):
        categories = [category for group in budget_groups.GROUPS for category in group['categories']]
        self.assertEqual(storage.CATEGORIES, set(categories))
        self.assertEqual(len(categories), len(set(categories)))
        self.assertEqual('@budget:fixed', budget_groups.group_id('Transporte'))
        self.assertEqual('@budget:fixed', budget_groups.group_id('Saúde'))
        self.assertEqual('@budget:other', budget_groups.group_id('Minha categoria'))
        # A matching label maps to the group but remains a distinct expense category.
        self.assertEqual('@budget:fixed', budget_groups.group_id('Custos fixos'))

    def test_aliases_ignore_case_and_accents_without_changing_detailed_categories(self):
        for category in ['carro', ' AUTOMOVEL ', 'gasolina', 'COMBUSTIVEL',
                         'aluguel', 'farmacia', 'internet', 'luz', 'agua', 'SAUDE']:
            with self.subTest(category=category):
                self.assertEqual('@budget:fixed', budget_groups.group_id(category))
        self.assertEqual('@budget:learning', budget_groups.group_id('cursos'))
        storage.add_category('Carro')
        storage.add_category('Custos fixos')
        self.assertIn('Carro', storage.read_categories())
        self.assertIn('Custos fixos', storage.read_categories())
        self.assertEqual(300, budget_groups.effective_limits({'Carro': 100, 'Saúde': 200})['@budget:fixed'])

    def test_reserved_group_ids_cannot_become_detailed_categories(self):
        storage.add_category('Personalizada')
        for reserved in ['@budget:fixed', '@budget:unknown', '@BUDGET:fixed']:
            with self.subTest(name=reserved):
                with self.assertRaisesRegex(ValueError, 'reservado'):
                    storage.add_category(reserved)
                with self.assertRaisesRegex(ValueError, 'reservado'):
                    storage.rename_category('Personalizada', reserved)
                with self.assertRaisesRegex(ValueError, 'reservado'):
                    cloud_storage.add_category(reserved, 42)
                with self.assertRaisesRegex(ValueError, 'reservado'):
                    cloud_storage.rename_category('Personalizada', reserved, 42)
        backup = storage.export_financial_data()
        backup['data']['budget_categories'].append({'name': '@budget:fixed'})
        with self.assertRaisesRegex(ValueError, 'reservada'):
            portability.validate(backup)

    def test_legacy_limits_sum_with_explicit_override_including_zero(self):
        raw = {'Moradia': 1000, 'Saúde': 200.1, 'Transporte': 99.9,
               'Lazer': 150, 'Educação': 80, 'Minha categoria': 20,
               '@budget:fixed': 1600, '@budget:leisure': 0}
        original = copy.deepcopy(raw)
        result = budget_groups.effective_limits(raw)
        self.assertEqual(1600, result['@budget:fixed'])
        self.assertEqual(0, result['@budget:leisure'])
        self.assertEqual(80, result['@budget:learning'])
        self.assertEqual(20, result['@budget:other'])
        self.assertEqual(1700, sum(result.values()))
        self.assertEqual(original, raw)
        del raw['@budget:fixed']
        self.assertEqual(1300, budget_groups.effective_limits(raw)['@budget:fixed'])

    def test_group_budget_does_not_become_an_expense_category_or_change_legacy_months(self):
        storage.set_budget({'month': '2026-09', 'category': 'Moradia', 'limit': 1000})
        storage.set_budget({'month': '2026-10', 'category': '@budget:fixed', 'limit': 2500})
        self.assertEqual({'2026-09': {'Moradia': 1000}, '2026-10': {'@budget:fixed': 2500}}, storage.read_budgets())
        self.assertNotIn('@budget:fixed', storage.read_categories())
        with self.assertRaises(ValueError):
            storage.add_expense({'date': '2026-10-01', 'amount': 100, 'where': 'Casa',
                                 'category': '@budget:fixed', 'payment': 'Pix'})
        with self.assertRaises(ValueError):
            storage.set_budget({'month': '2026-10', 'category': '@budget:unknown', 'limit': 100})

    def test_grouped_and_legacy_limits_round_trip_in_backup_without_losing_expense_details(self):
        storage.add_expense({'date': '2026-10-01', 'amount': 100, 'where': 'Clínica',
                             'category': 'Saúde', 'payment': 'Pix'})
        storage.set_budget({'month': '2026-09', 'category': 'Saúde', 'limit': 300})
        storage.set_budget({'month': '2026-10', 'category': 'Saúde', 'limit': 200})
        storage.set_budget({'month': '2026-10', 'category': '@budget:fixed', 'limit': 1000})
        backup = storage.export_financial_data()
        validated = portability.validate(backup)
        self.assertEqual(3, len(validated['budgets']))
        storage.set_budget({'month': '2026-10', 'category': '@budget:fixed', 'limit': 0})
        storage.restore_financial_data(backup)
        self.assertEqual({'Saúde': 200, '@budget:fixed': 1000}, storage.read_budgets()['2026-10'])
        self.assertEqual('Saúde', storage.read_expenses()[0]['category'])
        invalid = copy.deepcopy(backup)
        invalid['data']['budgets'][0]['category'] = '@budget:unknown'
        with self.assertRaises(ValueError):
            portability.validate(invalid)

    def test_hosted_group_save_keeps_user_scope_and_rejects_unknown_ids(self):
        connection, cursor = MagicMock(), MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with patch.object(cloud_storage, 'connect') as connect, \
             patch.object(cloud_storage, 'initialize'), \
             patch.object(cloud_storage, 'read_categories', return_value=['Moradia']):
            connect.return_value.__enter__.return_value = connection
            result = cloud_storage.set_budget({'month': '2026-10', 'category': '@budget:fixed', 'limit': 1500}, 42)
            self.assertEqual(1500, result['limit'])
            self.assertEqual((42, '2026-10', '@budget:fixed', 1500), cursor.execute.call_args.args[1])
            with self.assertRaises(ValueError):
                cloud_storage.set_budget({'month': '2026-10', 'category': '@budget:unknown', 'limit': 100}, 42)


if __name__ == '__main__':
    unittest.main()
