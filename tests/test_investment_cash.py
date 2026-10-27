import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api import index
from src import investments, storage


class InvestmentCashTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'test.db'),
                      patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups')]
        for mock in self.patches:mock.start()

    def tearDown(self):
        for mock in reversed(self.patches):mock.stop()
        self.temp.cleanup()

    def test_cash_persists_separately_from_assets_and_does_not_change_returns(self):
        investments.set_cash_balance({'amount':3000})
        stock=investments.create_investment({'type':'Ações','symbol':'PETR4','quantity':100,
                                           'average_price':30,'current_price':34,'purchase_date':'2026-01-01'})
        before=investments.portfolio()
        snapshots=copy.deepcopy(investments.load_store()['history'])
        result=investments.set_cash_balance({'amount':2500})
        self.assertEqual(2500,result['summary']['cash_balance'])
        self.assertEqual(5900,result['summary']['total_with_cash'])
        for field in ('current_value','amount_applied','profit_loss','return_percent','monthly_estimated_gain'):
            self.assertEqual(before['summary'][field],result['summary'][field])
        self.assertEqual(snapshots,investments.load_store()['history'])
        self.assertEqual(2500,investments.portfolio()['summary']['cash_balance'])
        self.assertEqual(stock['id'],result['investments'][0]['id'])
        self.assertEqual([],storage.read_expenses())

    def test_old_accounts_default_to_zero_and_balance_can_be_cleared(self):
        self.assertEqual(0,investments.portfolio()['summary']['cash_balance'])
        self.assertEqual(0,investments.portfolio()['summary']['total_with_cash'])
        self.assertEqual(12.13,investments.set_cash_balance({'amount':'12.125'})['summary']['cash_balance'])
        result=investments.set_cash_balance({'amount':0})
        self.assertEqual(0,result['summary']['cash_balance'])
        self.assertEqual([],result['investments'])
        self.assertEqual(0,result['summary']['profit_loss'])

    def test_invalid_balances_do_not_replace_saved_cash(self):
        investments.set_cash_balance({'amount':100})
        for payload in ({'amount':-1},{'amount':'NaN'},{'amount':'Infinity'},{'amount':1000000001},{},[]):
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                investments.set_cash_balance(payload)
        self.assertEqual(100,investments.portfolio()['summary']['cash_balance'])

    def test_cash_is_scoped_to_current_users_store(self):
        stores={42:investments.empty_store(),99:investments.empty_store()}
        def save(data,user_id):stores[user_id]=copy.deepcopy(data)
        def mutate(operation,user_id):
            data=copy.deepcopy(stores[user_id]);result=operation(data);save(data,user_id);return result
        with patch.object(investments.storage,'mutate_investments',side_effect=mutate), patch.object(investments.storage,'load_investments',side_effect=lambda user_id:copy.deepcopy(stores[user_id])),patch.object(investments.storage,'save_investments',side_effect=save):
            investments.set_cash_balance({'amount':500},42)
            self.assertEqual(500,investments.portfolio(42)['summary']['cash_balance'])
            self.assertEqual(0,investments.portfolio(99)['summary']['cash_balance'])

    def test_cash_api_requires_authentication_and_validates_inputs(self):
        client=TestClient(index.fastapi_app)
        with patch.object(index.auth,'session_user',return_value=None):
            self.assertEqual(401,client.post('/api/investments/cash',json={'amount':100}).status_code)
        with patch.object(index.auth,'session_user',return_value=1):
            response=client.post('/api/investments/cash',json={'amount':100})
            self.assertEqual(200,response.status_code)
            self.assertEqual(100,response.json()['summary']['cash_balance'])
            self.assertEqual(400,client.post('/api/investments/cash',json={'amount':-1}).status_code)
