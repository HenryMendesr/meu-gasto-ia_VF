import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from api import index
from src import investments, planning, storage, cloud_storage


def asset(**changes):
    item={'type':'Ações','symbol':'PETR4','quantity':10,'average_price':30,'current_price':30,'purchase_date':'2026-10-01'}
    item.update(changes)
    return item


def contract():
    return {'date':'2026-10-01','amount':1000,'where':'Banco','category':'Contas','payment':'Pix',
            'financing_kind':'loan','debt_type':'Pessoal','debt_entry':True,'installment':True,
            'installment_count':12,'interest_rate':2.5,'first_charge_date':'2026-11-01'}


class WealthFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'test.db'),
                      patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups'),
                      patch.object(investments,'investment_today',return_value=date(2026,10,27))]
        for mock in self.patches:mock.start()
        investments.set_cash_balance({'amount':10000})
        self.item=investments.create_investment(asset())

    def tearDown(self):
        for mock in reversed(self.patches):mock.stop()
        self.temp.cleanup()

    def test_sale_credits_net_cash_exactly_once(self):
        payload={'date':'2026-10-10','quantity':4,'mode':'unit','value':40,'fees':5,'request_id':'sale-1'}
        result=investments.sell_investment(self.item['id'],payload)
        self.assertEqual(155,result['sale']['net_total'])
        self.assertEqual(35,result['sale']['profit_loss'])
        self.assertEqual(9855,investments.portfolio()['summary']['cash_balance'])
        investments.sell_investment(self.item['id'],payload)
        self.assertEqual(9855,investments.portfolio()['summary']['cash_balance'])
        self.assertEqual(1,len(investments.load_store()['investments'][0]['sales']))

    def test_additional_buy_after_partial_sale_uses_open_cost_basis_and_fees(self):
        investments.sell_investment(self.item['id'],{'date':'2026-10-10','quantity':4,'mode':'unit','value':40,'fees':5})
        payload={'date':'2026-10-15','quantity':4,'unit_price':50,'fees':4,'request_id':'buy-1'}
        result=investments.add_buy(self.item['id'],payload)
        self.assertEqual(204,result['buy']['total'])
        self.assertEqual(10,result['investment']['remaining_quantity'])
        self.assertEqual(384,result['investment']['amount_applied'])
        self.assertEqual(38.4,result['investment']['average_price'])
        self.assertEqual(35,result['investment']['realized_profit_loss'])
        self.assertEqual(9651,investments.portfolio()['summary']['cash_balance'])
        investments.add_buy(self.item['id'],payload)
        self.assertEqual(9651,investments.portfolio()['summary']['cash_balance'])
        self.assertEqual(2,len(investments.portfolio()['investments'][0]['buys']))

    def test_income_is_added_once_to_cash_and_result_without_changing_quantity(self):
        payload={'date':'2026-10-20','kind':'Dividendos','amount':20,'request_id':'income-1'}
        investments.add_investment_income(self.item['id'],payload)
        investments.add_investment_income(self.item['id'],payload)
        result=investments.portfolio()
        self.assertEqual(9720,result['summary']['cash_balance'])
        self.assertEqual(20,result['summary']['income_received'])
        self.assertEqual(20,result['summary']['profit_loss'])
        self.assertEqual(0,result['summary']['realized_profit_loss'])
        self.assertEqual(10,result['investments'][0]['remaining_quantity'])
        self.assertEqual(20,result['history'][-1]['profit_loss'])
        with self.assertRaises(ValueError):investments.delete_investment(self.item['id'])

    def test_personal_history_follows_buys_and_receipts_without_future_leakage(self):
        investments.add_buy(self.item['id'],{'date':'2026-10-15','quantity':10,'unit_price':40})
        investments.add_investment_income(self.item['id'],{'date':'2026-10-20','kind':'JCP','amount':20})
        quotes=lambda *_:{'source':'Teste','points':[{'date':'2026-10-01','price':30},{'date':'2026-10-10','price':35},
            {'date':'2026-10-15','price':40},{'date':'2026-10-20','price':40}]}
        result=investments.investment_history(self.item['id'],'all',market_fetcher=quotes)
        history={point['date']:point['value'] for point in result['gain_points']}
        self.assertEqual(50,history['2026-10-10'])
        self.assertEqual(100,history['2026-10-15'])
        self.assertEqual(120,history['2026-10-20'])

    def test_closed_position_receipt_does_not_appear_before_payment_date(self):
        investments.sell_investment(self.item['id'],{'date':'2026-10-10','quantity':10,'mode':'unit','value':35})
        investments.add_investment_income(self.item['id'],{'date':'2026-10-20','kind':'Dividendos','amount':20})
        result=investments.investment_history(self.item['id'],'all',market_fetcher=lambda *_:{'source':'Teste','points':[{'date':'2026-10-01','price':30},{'date':'2026-10-10','price':35}]})
        history={point['date']:point['value'] for point in result['gain_points']}
        self.assertEqual(50,history['2026-10-10'])
        self.assertEqual(70,history['2026-10-20'])
        self.assertEqual(70,history['2026-10-27'])

    def test_invalid_trade_inputs_and_insufficient_cash_do_not_mutate_state(self):
        before=copy.deepcopy(investments.load_store())
        actions=[lambda:investments.add_buy(self.item['id'],{'date':'2026-10-28','quantity':1,'unit_price':30}),
                 lambda:investments.add_buy(self.item['id'],{'date':'2026-10-20','quantity':10000,'unit_price':30}),
                 lambda:investments.sell_investment(self.item['id'],{'date':'2026-10-20','quantity':1,'value':30,'fees':30}),
                 lambda:investments.add_investment_income(self.item['id'],{'date':'2026-10-20','kind':'Dividendos','amount':-1})]
        for action in actions:
            with self.assertRaises(ValueError):action()
            self.assertEqual(before,investments.load_store())

    def test_paid_installment_is_updated_in_place_and_can_be_undone(self):
        debt=storage.add_expense(contract())
        before=storage.read_expenses()
        storage.set_debt_payment(debt['id'],{'paid':True,'paid_date':'2026-10-27'})
        after=storage.read_expenses()
        self.assertEqual(len(before),len(after))
        self.assertTrue(after[0]['finance']['paid'])
        self.assertEqual(before[0]['amount'],after[0]['amount'])
        with self.assertRaises(ValueError):storage.update_debt(debt['id'],contract())
        with self.assertRaises(ValueError):storage.delete_expense(debt['id'],scope='all')
        storage.set_debt_payment(debt['id'],{'paid':False})
        self.assertFalse(storage.read_expenses()[0]['finance']['paid'])
        self.assertNotIn('paid_date',storage.read_expenses()[0]['finance'])

    def test_goals_update_progress_without_moving_cash_or_assets(self):
        before=investments.portfolio()['summary']
        goal=planning.save_goal({'name':'Reserva','target_amount':10000,'current_amount':1000,'target_date':'2027-10-27'})
        changed=planning.save_goal({**goal,'current_amount':1500})
        self.assertEqual(1500,changed['current_amount'])
        self.assertEqual(1,len(investments.portfolio()['goals']))
        self.assertEqual(before,investments.portfolio()['summary'])
        planning.delete_goal(goal['id'])
        self.assertEqual([],investments.portfolio()['goals'])

    def test_report_does_not_duplicate_salary_and_counts_debts_by_payment_date(self):
        storage.set_income({'month':'2026-10','cash':5000,'voucher':600})
        storage.add_income_entry({'date':'2026-10-01','amount':5000,'where':'Empresa','category':'Salário'})
        storage.add_expense({'date':'2026-10-10','amount':100,'where':'Mercado','category':'Mercado','payment':'Pix'})
        debt=storage.add_expense(contract())
        unpaid=planning.monthly_report('2026-10')
        self.assertEqual(5000,unpaid['income'])
        self.assertEqual(5000,unpaid['imported_income'])
        self.assertEqual(100,unpaid['cash_expenses'])
        storage.set_debt_payment(debt['id'],{'paid':True,'paid_date':'2026-10-27'})
        result=planning.monthly_report('2026-10')
        self.assertEqual(197.49,result['cash_expenses'])
        self.assertEqual(97.49,result['debt_paid'])
        self.assertEqual(300,result['invested'])
        self.assertEqual(6,len(result['flow']))
        self.assertTrue(result['wealth_history'])
        for month in ('2026-13','2026-00','invalid'):
            with self.assertRaises(ValueError):planning.monthly_report(month)

    def test_report_sales_and_dividends_are_separate_from_buy_amount(self):
        investments.sell_investment(self.item['id'],{'date':'2026-10-10','quantity':4,'value':40,'fees':5})
        investments.add_investment_income(self.item['id'],{'date':'2026-10-20','kind':'Dividendos','amount':20})
        report=planning.monthly_report('2026-10')
        self.assertEqual(300,report['invested'])
        self.assertEqual(155,report['sales'])
        self.assertEqual(20,report['investment_income'])
        self.assertEqual(55,report['realized_result'])

    def test_postgres_payment_reads_and_updates_only_authenticated_users_row(self):
        db,cursor=MagicMock(),MagicMock();db.__enter__.return_value=db;db.cursor.return_value=cursor;cursor.__enter__.return_value=cursor
        cursor.fetchone.return_value={'finance_details':json.dumps({'financing_kind':'loan','principal_part':80})}
        with patch.object(cloud_storage,'connect',return_value=db):
            cloud_storage.set_debt_payment(123,{'paid':True,'paid_date':'2026-10-27'},42)
        self.assertEqual((123,42),cursor.execute.call_args_list[0].args[1])
        self.assertEqual((123,42),cursor.execute.call_args_list[1].args[1][1:])
        db.commit.assert_called_once()

    def test_legacy_sales_are_not_credited_again_when_new_operations_are_added(self):
        data=investments.empty_store();legacy=investments.normalize_payload(asset())
        legacy['sales']=[{'id':'old-sale','date':'2026-10-10','quantity':5,'unit_price':40,'total':200,'profit_loss':50}]
        data['investments']=[legacy];data['cash_balance']=100
        investments.save_store(data)
        investments.add_buy(legacy['id'],{'date':'2026-10-15','quantity':2,'unit_price':50})
        result=investments.portfolio()
        self.assertEqual(0,result['summary']['cash_balance'])
        self.assertEqual(7,result['investments'][0]['remaining_quantity'])
        self.assertEqual(50,result['summary']['realized_profit_loss'])

    def test_goal_and_operations_cannot_access_another_users_records(self):
        stores={42:investments.empty_store(),99:investments.empty_store()}
        def mutate(operation,user_id):
            data=copy.deepcopy(stores[user_id]);result=operation(data);stores[user_id]=data;return result
        with patch.object(investments.storage,'mutate_investments',side_effect=mutate),patch.object(investments.storage,'load_investments',side_effect=lambda user_id:copy.deepcopy(stores[user_id])):
            investments.set_cash_balance({'amount':1000},42)
            first=investments.create_investment(asset(),42)
            goal=planning.save_goal({'name':'Reserva','target_amount':1000,'current_amount':0,'target_date':'2027-10-27'},42)
            before=copy.deepcopy(stores)
            with self.assertRaises(ValueError):investments.add_buy(first['id'],{'date':'2026-10-20','quantity':1,'unit_price':10},99)
            with self.assertRaises(ValueError):investments.add_investment_income(first['id'],{'date':'2026-10-20','amount':10,'kind':'JCP'},99)
            with self.assertRaises(KeyError):planning.save_goal({**goal,'current_amount':100},99)
            with self.assertRaises(KeyError):planning.delete_goal(goal['id'],99)
            self.assertEqual(before,stores)

    def test_invalid_goal_and_payment_date_preserve_original_records(self):
        before=copy.deepcopy(investments.load_store())
        for payload in ({'name':'a','target_amount':100,'current_amount':0,'target_date':'2027-01-01'},
                        {'name':'Reserva','target_amount':'NaN','current_amount':0,'target_date':'2027-01-01'},
                        {'name':'Reserva','target_amount':100,'current_amount':-1,'target_date':'2027-01-01'}):
            with self.assertRaises(ValueError):planning.save_goal(payload)
        self.assertEqual(before,investments.load_store())
        debt=storage.add_expense(contract())
        records=copy.deepcopy(storage.read_expenses())
        for payload in ({'paid':True,'paid_date':'2099-01-01'},{'paid':'yes','paid_date':'2026-10-27'}):
            with self.assertRaises(ValueError):storage.set_debt_payment(debt['id'],payload)
        self.assertEqual(records,storage.read_expenses())

    def test_generic_expense_edit_cannot_overwrite_a_paid_installment(self):
        debt=storage.add_expense(contract())
        storage.set_debt_payment(debt['id'],{'paid':True,'paid_date':'2026-10-27'})
        rows=storage.read_expenses();payload={'date':'2026-10-27','amount':200,'where':'Banco','category':'Contas','payment':'Pix'}
        with self.assertRaises(ValueError):storage.update_expense(debt['id'],payload)
        with self.assertRaises(ValueError):storage.update_expense(rows[1]['id'],{**payload,'scope':'all'})
        self.assertEqual(rows,storage.read_expenses())

    def test_new_endpoints_require_auth_and_goals_route_precedes_generic_resource(self):
        client=TestClient(index.fastapi_app)
        with patch.object(index.auth,'session_user',return_value=None):
            for endpoint in (f'/api/investments/{self.item["id"]}/buys',f'/api/investments/{self.item["id"]}/incomes','/api/debts/1/payment','/api/goals'):
                self.assertEqual(401,client.post(endpoint,json={}).status_code)
            self.assertEqual(401,client.get('/api/reports/monthly?month=2026-10').status_code)
        with patch.object(index.auth,'session_user',return_value=1):
            response=client.post('/api/goals',json={'name':'Reserva','target_amount':1000,'current_amount':100,'target_date':'2027-10-27'})
            self.assertEqual(200,response.status_code,response.text)
            goal_id=response.json()['goal']['id']
            self.assertEqual(200,client.delete('/api/goals/'+goal_id).status_code)
            self.assertEqual(200,client.get('/api/reports/monthly?month=2026-10').status_code)
