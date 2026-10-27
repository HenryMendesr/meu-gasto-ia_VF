import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from api import index
from src import storage, cloud_storage
from src.finance_rules import expense_finance, inferred_interest_rate


def debt(**overrides):
    payload = {'date': '2026-10-27', 'amount': 1000, 'where': 'Banco de teste',
               'category': 'Contas', 'payment': 'Pix', 'description': 'Contrato original',
               'financing_kind': 'loan', 'debt_type': 'Pessoal', 'debt_entry': True,
               'installment': True, 'installment_count': 12, 'interest_rate': '2,5',
               'first_charge_date': '2026-11-30', 'amortization_system': 'price'}
    payload.update(overrides)
    return payload


class ImpliedRateTests(unittest.TestCase):
    def test_recovers_rate_and_preserves_payment_and_principal(self):
        rate = inferred_interest_rate(1000, '97.49', 12)
        self.assertAlmostEqual(2.5, float(rate), delta=.001)
        payload = debt(calculation_mode='payment', installment_amount='97.49', interest_rate=99)
        _, parts, metadata = expense_finance(payload, payload['date'], payload['payment'])
        self.assertEqual('payment', metadata['calculation_mode'])
        self.assertAlmostEqual(2.5, metadata['interest_rate'], delta=.001)
        self.assertEqual(97.49, parts[0]['amount'])
        self.assertAlmostEqual(97.49, parts[-1]['amount'], delta=.05)
        self.assertEqual(0, parts[-1]['balance_after'])
        self.assertEqual(1000, round(sum(part['amortization'] for part in parts), 2))

    def test_zero_interest_single_payment_and_rounded_installments(self):
        self.assertEqual(0, inferred_interest_rate(1000, 100, 10))
        self.assertAlmostEqual(10, float(inferred_interest_rate(1000, 1100, 1)))
        payload = debt(calculation_mode='payment', installment_amount=333.33, installment_count=3)
        _, parts, _ = expense_finance(payload, payload['date'], 'Pix')
        self.assertEqual([333.33, 333.33, 333.34], [part['amount'] for part in parts])

    def test_rejects_inconsistent_or_invalid_inputs(self):
        for payment, count in [(50, 12), (0, 12), ('NaN', 12), (100, 2.5), (100, 0), (100, 601), (2001, 12)]:
            with self.subTest(payment=payment,count=count), self.assertRaises(ValueError):
                inferred_interest_rate(1000, payment, count)
        payload = debt(calculation_mode='payment', installment_amount=100, financing_kind='asset',
                       asset_value=1200, down_payment=200, asset_name='Carro', debt_type='Veículo', amortization_system='sac')
        with self.assertRaises(ValueError):
            expense_finance(payload, payload['date'], 'Pix')


class DebtEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(storage, 'DATABASE', Path(self.temp.name)/'test.db'),
                        patch.object(storage, 'BACKUPS', Path(self.temp.name)/'backups')]
        for mock in self.patches: mock.start()
        self.original = storage.add_expense(debt())
        self.unrelated = storage.add_expense({'date':'2026-10-27','amount':20,'where':'Mercado',
                                              'category':'Mercado','payment':'Pix'})

    def tearDown(self):
        for mock in reversed(self.patches): mock.stop()
        self.temp.cleanup()

    def test_edit_replaces_whole_schedule_and_preserves_other_expenses(self):
        result = storage.update_debt(self.original['id'], debt(amount=2000, installment_count=20,
            where='Banco corrigido', first_charge_date='2027-01-31', calculation_mode='payment', installment_amount=130))
        self.assertEqual(self.original['installment_group'], result['installment_group'])
        rows = storage.read_expenses()
        self.assertEqual(21, len(rows))
        self.assertEqual(20, len(result['ids']))
        unchanged = next(row for row in rows if row['id']==self.unrelated['id'])
        self.assertEqual(20, unchanged['amount'])
        parts = [row for row in rows if row['installment_group']==result['installment_group']]
        self.assertEqual('2027-01-31', parts[0]['date'])
        self.assertEqual('2027-02-28', parts[1]['date'])
        self.assertTrue(all(row['where']=='Banco corrigido' for row in parts))
        self.assertEqual(2000, round(sum(row['finance']['principal_part'] for row in parts),2))
        self.assertEqual(0, parts[-1]['finance']['balance_after'])
        self.assertTrue(all(row['finance']['calculation_mode']=='payment' for row in parts))

    def test_invalid_edit_and_edit_of_non_debt_preserve_original_data(self):
        before = storage.read_expenses()
        with self.assertRaises(ValueError):
            storage.update_debt(self.original['id'], debt(calculation_mode='payment', installment_amount=10))
        with self.assertRaises(KeyError):
            storage.update_debt(self.unrelated['id'], debt())
        self.assertEqual(before, storage.read_expenses())

    def test_failure_during_replacement_rolls_back_deleted_rows(self):
        before = storage.read_expenses()
        with patch.object(storage.json,'dumps',side_effect=RuntimeError('Simulated failure')):
            with self.assertRaises(RuntimeError):
                storage.update_debt(self.original['id'], debt(amount=2000))
        self.assertEqual(before, storage.read_expenses())

    def test_postgres_write_scopes_all_queries_to_user_and_uses_one_transaction(self):
        db, cursor = MagicMock(), MagicMock()
        db.__enter__.return_value=db;cursor.__enter__.return_value=cursor;db.cursor.return_value=cursor
        cursor.fetchone.side_effect=[{'installment_group':'contract','finance_details':json.dumps({'financing_kind':'loan'})}]+[{'id':i} for i in range(1,4)]
        with patch.object(cloud_storage,'connect',return_value=db), patch.object(cloud_storage,'read_categories',return_value=['Contas']):
            result=cloud_storage.update_debt(123,debt(installment_count=3),42)
        calls=cursor.execute.call_args_list
        self.assertIn('user_id=%s FOR UPDATE',calls[0].args[0])
        self.assertEqual((123,42),calls[0].args[1])
        self.assertEqual((42,'contract'),calls[1].args[1])
        for call in calls[2:]: self.assertEqual(42,call.args[1][0])
        db.commit.assert_called_once()
        self.assertEqual([1,2,3],result['ids'])

    def test_debt_edit_api_authentication_and_authenticated_user(self):
        client=TestClient(index.fastapi_app)
        with patch.object(index.auth,'session_user',return_value=None):
            self.assertEqual(401,client.put('/api/debts/1',json=debt()).status_code)
        with patch.object(index.auth,'session_user',return_value=42), patch.object(index.storage,'update_debt',return_value={'id':1}) as edit:
            self.assertEqual(200,client.put('/api/debts/1',json=debt()).status_code)
            edit.assert_called_once_with(1,debt(),42)
