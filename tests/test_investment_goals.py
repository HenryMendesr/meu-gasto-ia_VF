import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api import index
from src import investments, planning, storage, portability


class InvestmentGoalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'db.sqlite'),patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups'),patch.object(investments,'investment_today',return_value=date(2026,10,27))]
        for mock in self.patches:mock.start()
        investments.set_cash_balance({'amount':10000})
        self.asset={'type':'Ações','symbol':'PETR4','quantity':10,'average_price':30,'current_price':40,'purchase_date':'2026-10-01'}
        self.item=investments.create_investment(self.asset)
        self.goal={'name':'R$ 50 mil investidos','target_amount':50000,'target_date':'2027-10-27'}

    def tearDown(self):
        for mock in reversed(self.patches):mock.stop()
        self.temp.cleanup()

    def test_value_goal_tracks_current_holdings_not_cash_and_ignores_manual_override(self):
        goal=planning.save_goal({**self.goal,'tracking_mode':'portfolio_value','current_amount':999999})
        self.assertEqual(400,goal['current_amount']);self.assertEqual(50000,goal['target_amount'])
        self.assertEqual(0,investments.load_store()['goals'][0]['current_amount'])
        investments.set_cash_balance({'amount':20000})
        self.assertEqual(400,investments.portfolio()['goals'][0]['current_amount'])
        investments.update_investment(self.item['id'],{**self.asset,'current_price':50})
        self.assertEqual(500,investments.portfolio()['goals'][0]['current_amount'])

    def test_cost_goal_excludes_appreciation_and_sold_positions(self):
        planning.save_goal({**self.goal,'tracking_mode':'portfolio_cost'})
        self.assertEqual(300,investments.portfolio()['goals'][0]['current_amount'])
        investments.sell_investment(self.item['id'],{'date':'2026-10-27','quantity':4,'mode':'unit','value':50})
        self.assertEqual(180,investments.portfolio()['goals'][0]['current_amount'])
        investments.sell_investment(self.item['id'],{'date':'2026-10-27','quantity':6,'mode':'unit','value':50})
        self.assertEqual(0,investments.portfolio()['goals'][0]['current_amount'])

    def test_manual_goal_and_cash_are_not_changed_by_automatic_goals(self):
        planning.save_goal({**self.goal,'current_amount':123})
        before=investments.portfolio()['summary']['cash_balance']
        automatic=planning.save_goal({**self.goal,'tracking_mode':'portfolio_value'})
        goals=investments.portfolio()['goals'];self.assertEqual([123,400],[goal['current_amount'] for goal in goals])
        planning.delete_goal(automatic['id']);self.assertEqual(before,investments.portfolio()['summary']['cash_balance'])
        self.assertEqual(123,investments.portfolio()['goals'][0]['current_amount'])

    def test_backup_roundtrip_recalculates_and_rejects_unknown_mode(self):
        planning.save_goal({**self.goal,'tracking_mode':'portfolio_value'})
        backup=storage.export_financial_data();storage.restore_financial_data(backup)
        self.assertEqual(400,investments.portfolio()['goals'][0]['current_amount'])
        bad=copy.deepcopy(backup);bad['data']['portfolio']['goals'][0]['tracking_mode']='unknown'
        with self.assertRaises(ValueError):portability.validate(bad)

    def test_api_returns_calculated_goal_and_validation_preserves_state(self):
        with patch.object(index.auth,'session_user',return_value=1):
            client=TestClient(index.fastapi_app)
            response=client.post('/api/goals',json={**self.goal,'tracking_mode':'portfolio_value'})
            self.assertEqual(200,response.status_code);self.assertEqual(400,response.json()['goal']['current_amount'])
            before=investments.load_store()
            invalid=client.post('/api/goals',json={**self.goal,'tracking_mode':'unknown'})
            self.assertEqual(400,invalid.status_code);self.assertEqual(before,investments.load_store())
