import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src import budget_groups, investments, portability, recurring, storage, trust


class IsolatedStore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(storage, 'DATABASE', Path(self.temp.name) / 'db.sqlite'),
                        patch.object(storage, 'BACKUPS', Path(self.temp.name) / 'backups'),
                        patch.object(investments, 'investment_today', return_value=date(2026, 11, 20))]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()


class CardGoalTests(IsolatedStore):
    def test_goals_are_optional_and_saved_with_the_card(self):
        plain = recurring.validate_card({'name': 'Nubank', 'due_day': '10', 'closing_day': '3'})
        self.assertIsNone(plain['spending_goal'])
        self.assertIsNone(plain['installment_cap'])
        card = recurring.save_card({'name': 'Nubank', 'due_day': '10', 'closing_day': '3',
                                    'spending_goal': '1500', 'installment_cap': '600.5'})
        self.assertEqual(1500, card['spending_goal'])
        self.assertEqual(600.5, card['installment_cap'])
        stored = investments.load_store()['preferences']['credit_cards'][0]
        self.assertEqual(600.5, stored['installment_cap'])

    def test_invalid_goals_are_rejected(self):
        for field, value in (('spending_goal', '-1'), ('installment_cap', '20000000'), ('spending_goal', 'abc')):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                recurring.validate_card({'name': 'Itaú', 'due_day': 5, field: value})

    def test_backup_keeps_card_goals(self):
        recurring.save_card({'name': 'Inter', 'due_day': '15', 'closing_day': '8', 'installment_cap': '400'})
        restored = portability.validate(storage.export_financial_data())
        self.assertEqual(400, restored['portfolio']['preferences']['credit_cards'][0]['installment_cap'])


class BudgetPlanTests(IsolatedStore):
    def test_recommended_plan_leaves_room_to_save(self):
        plan = budget_groups.RECOMMENDED_PLAN
        self.assertEqual(set(plan), budget_groups.GROUP_IDS)
        self.assertEqual(85, sum(plan.values()))

    def test_plan_is_validated_and_saved_in_preferences(self):
        plan = {**budget_groups.RECOMMENDED_PLAN, '@budget:fixed': 45.555}
        saved = trust.preferences({'budget_plan': plan})
        self.assertEqual(45.56, saved['budget_plan']['@budget:fixed'])
        restored = portability.validate(storage.export_financial_data())
        self.assertEqual(saved['budget_plan'], restored['portfolio']['preferences']['budget_plan'])

    def test_invalid_plans_are_rejected(self):
        over = {group: 30 for group in budget_groups.GROUP_IDS}
        missing = dict(list(budget_groups.RECOMMENDED_PLAN.items())[:4])
        negative = {**budget_groups.RECOMMENDED_PLAN, '@budget:other': -1}
        text = {**budget_groups.RECOMMENDED_PLAN, '@budget:other': '5'}
        for plan in (over, missing, negative, text, []):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                trust.preferences({'budget_plan': plan})


if __name__ == '__main__':
    unittest.main()
