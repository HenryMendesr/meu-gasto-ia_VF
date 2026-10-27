import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from api import index
from src import investments, storage, cloud_storage


def stock(**changes):
    result={'type':'Ações','symbol':'PETR4','quantity':10,'average_price':30,
            'current_price':30,'purchase_date':'2026-10-27'}
    result.update(changes)
    return result


class CashFundingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'test.db'),
                      patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups')]
        for mock in self.patches:mock.start()

    def tearDown(self):
        for mock in reversed(self.patches):mock.stop()
        self.temp.cleanup()

    def test_stock_debits_purchase_cost_not_market_value(self):
        investments.set_cash_balance({'amount':1000})
        item=investments.create_investment(stock(current_price=35))
        summary=investments.portfolio()['summary']
        self.assertEqual(300,item['cash_funded_amount'])
        self.assertEqual(700,summary['cash_balance'])
        self.assertEqual(350,summary['current_value'])
        self.assertEqual(50,summary['profit_loss'])
        self.assertEqual(1050,summary['total_with_cash'])

    def test_fractional_share_cost_and_display_use_the_same_cent_rounding(self):
        investments.set_cash_balance({'amount':100})
        item=investments.create_investment(stock(quantity=1,average_price=1.005,current_price=1.005))
        self.assertEqual(1.01,item['cash_funded_amount'])
        self.assertEqual(1.01,item['amount_applied'])
        self.assertEqual(0,item['profit_loss'])
        self.assertEqual(98.99,investments.portfolio()['summary']['cash_balance'])

    def test_fixed_income_debits_principal_and_allows_exact_balance(self):
        investments.set_cash_balance({'amount':1000})
        item=investments.create_investment({'type':'Renda fixa','name':'CDB','institution':'Banco',
            'amount_invested':1000,'application_date':'2026-01-01','profitability_type':'Prefixado',
            'contracted_rate':12,'valuation_mode':'manual','current_value_manual':1100,'current_value_date':'2026-10-27'})
        self.assertEqual(1000,item['cash_funded_amount'])
        self.assertEqual(0,investments.portfolio()['summary']['cash_balance'])

    def test_insufficient_funds_changes_neither_cash_nor_investments(self):
        investments.set_cash_balance({'amount':100})
        before=copy.deepcopy(investments.load_store())
        with self.assertRaisesRegex(ValueError,'Saldo insuficiente'):
            investments.create_investment(stock())
        self.assertEqual(before,investments.load_store())

    def test_edit_uses_only_cost_difference_and_cancellation_refunds(self):
        investments.set_cash_balance({'amount':1000})
        item=investments.create_investment(stock())
        investments.update_investment(item['id'],stock(current_price=40))
        self.assertEqual(700,investments.portfolio()['summary']['cash_balance'])
        investments.update_investment(item['id'],stock(quantity=20))
        self.assertEqual(400,investments.portfolio()['summary']['cash_balance'])
        before=copy.deepcopy(investments.load_store())
        with self.assertRaises(ValueError):investments.update_investment(item['id'],stock(quantity=100))
        self.assertEqual(before,investments.load_store())
        investments.update_investment(item['id'],stock(quantity=5))
        self.assertEqual(850,investments.portfolio()['summary']['cash_balance'])
        investments.delete_investment(item['id'])
        self.assertEqual(1000,investments.portfolio()['summary']['cash_balance'])
        self.assertEqual([],investments.portfolio()['investments'])

    def test_legacy_holdings_do_not_receive_retroactive_cash_movements(self):
        legacy=investments.normalize_payload(stock())
        data=investments.empty_store();data['cash_balance']=100;data['investments']=[legacy]
        investments.save_store(data)
        investments.update_investment(legacy['id'],stock(quantity=20))
        self.assertEqual(100,investments.portfolio()['summary']['cash_balance'])
        investments.delete_investment(legacy['id'])
        self.assertEqual(100,investments.portfolio()['summary']['cash_balance'])

    def test_simultaneous_purchases_cannot_overdraw_or_lose_a_debit(self):
        investments.set_cash_balance({'amount':1000})
        def buy(_):
            try:return investments.create_investment(stock(quantity=1,average_price=700))
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(buy,range(2)))
        self.assertEqual(1,sum(result is not None for result in results))
        result=investments.portfolio()
        self.assertEqual(300,result['summary']['cash_balance'])
        self.assertEqual(1,len(result['investments']))

    def test_refresh_merges_prices_without_overwriting_a_new_purchase(self):
        investments.set_cash_balance({'amount':1000})
        investments.create_investment(stock())
        def fetch(_):
            investments.create_investment(stock(symbol='VALE3',quantity=2,average_price=50))
            return {'price':35,'daily_change_percent':1,'source':'Teste','updated_at':'2026-10-27T00:00:00Z'}
        result=investments.refresh_investments(quote_fetcher=fetch)
        self.assertEqual(600,result['summary']['cash_balance'])
        self.assertEqual(2,len(result['investments']))

    def test_failure_during_write_rolls_back_asset_and_cash(self):
        investments.set_cash_balance({'amount':1000})
        before=copy.deepcopy(investments.load_store())
        with patch.object(investments,'record_snapshot',side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):investments.create_investment(stock())
        self.assertEqual(before,investments.load_store())

    def test_postgres_locks_user_portfolio_and_saves_asset_and_debit_together(self):
        db,cursor=MagicMock(),MagicMock();db.__enter__.return_value=db;cursor.__enter__.return_value=cursor;db.cursor.return_value=cursor
        data=investments.empty_store();data['cash_balance']=1000
        cursor.fetchone.return_value={'value':data}
        def buy(store):store['cash_balance']-=300;store['investments'].append({'id':'new'});return 'ok'
        with patch.object(cloud_storage,'initialize'),patch.object(cloud_storage,'connect',return_value=db):
            self.assertEqual('ok',cloud_storage.mutate_investments(buy,42))
        calls=cursor.execute.call_args_list
        self.assertIn('FOR UPDATE',calls[1].args[0]);self.assertEqual(('investments:42',),calls[1].args[1])
        saved=json.loads(calls[2].args[1][0]);self.assertEqual(700,saved['cash_balance']);self.assertEqual([{'id':'new'}],saved['investments'])
        self.assertEqual('investments:42',calls[2].args[1][1]);db.commit.assert_called_once()

    def test_api_returns_insufficient_funds_then_accepts_purchase_after_deposit(self):
        client=TestClient(index.fastapi_app)
        with patch.object(index.auth,'session_user',return_value=1):
            self.assertEqual(400,client.post('/api/investments',json=stock()).status_code)
            client.post('/api/investments/cash',json={'amount':1000})
            self.assertEqual(201,client.post('/api/investments',json=stock()).status_code)
            summary=client.get('/api/investments').json()['summary']
            self.assertEqual(700,summary['cash_balance'])
