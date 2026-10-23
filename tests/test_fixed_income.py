from datetime import date, timedelta
import unittest
from unittest.mock import patch

from src import investments


class FixedIncomeTests(unittest.TestCase):
    today = date(2026, 10, 23)

    def setUp(self):
        self.clock = patch.object(investments, 'investment_today', return_value=self.today)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def item(self, **changes):
        item = {'type': 'Renda fixa', 'name': 'CDB', 'institution': 'Banco',
                'amount_invested': 1000, 'application_date': (self.today-timedelta(days=365)).isoformat(),
                'profitability_type': 'Prefixado', 'contracted_rate': 12,
                'rate_period': 'year', 'valuation_mode': 'automatic'}
        return {**item, **changes}

    def test_annual_fixed_yield_is_automatic_and_monthly_equivalent_is_compound(self):
        result = investments.calculated(self.item())
        self.assertEqual(1120, result['current_value'])
        self.assertEqual(120, result['profit_loss'])
        self.assertAlmostEqual(0.948879, result['monthly_rate_percent'], places=5)
        self.assertEqual(10.63, result['monthly_estimated_gain'])

    def test_monthly_rate_and_equivalent_annual_rate_give_same_value(self):
        monthly = investments.calculated(self.item(contracted_rate=1, rate_period='month'))
        equivalent = investments.calculated(self.item(contracted_rate=((1.01**12)-1)*100))
        self.assertEqual(1126.83, monthly['current_value'])
        self.assertEqual(monthly['current_value'], equivalent['current_value'])

    def test_value_and_history_stop_accruing_at_maturity(self):
        item = self.item(maturity_date=(self.today-timedelta(days=100)).isoformat())
        result = investments.calculated(item)
        history = investments.fixed_income_history(item, '1y')
        self.assertEqual(round(1000*1.12**(265/365), 2), result['current_value'])
        self.assertEqual(result['current_value'], history[-1]['value'])
        self.assertEqual(history[-1]['value'], history[-2]['value'])
        self.assertEqual('matured', result['calculation_status'])
        self.assertIsNone(result['monthly_estimated_gain'])

    def test_legacy_balance_continues_yield_from_its_reference_date(self):
        item = self.item(current_value_manual=1100, updated_at='2026-09-23T12:00:00Z')
        item.pop('valuation_mode')
        result = investments.calculated(item)
        self.assertEqual(round(1100*1.12**(30/365), 2), result['current_value'])
        self.assertEqual('balance', result['valuation_mode'])
        self.assertEqual(result['current_value'], investments.fixed_income_history(item, '1m')[-1]['value'])

    def test_explicit_manual_balance_stays_manual_and_automatic_ignores_stale_balance(self):
        manual = investments.calculated(self.item(valuation_mode='manual', current_value_manual=1050,
                                                   current_value_date='2026-10-01'))
        automatic = investments.calculated(self.item(current_value_manual=1050))
        self.assertEqual(1050, manual['current_value'])
        self.assertIsNone(manual['monthly_estimated_gain'])
        self.assertEqual(1120, automatic['current_value'])

    def test_missing_index_is_visible_instead_of_showing_zero_as_a_known_return(self):
        pending = investments.calculated(self.item(profitability_type='CDI', contracted_rate=110))
        self.assertEqual('pending_rate', pending['calculation_status'])
        self.assertIsNone(pending['monthly_estimated_gain'])
        ready = investments.calculated(self.item(profitability_type='CDI', contracted_rate=110, cdi_rate=12))
        self.assertGreater(ready['current_value'], 1120)
        ipca = investments.calculated(self.item(profitability_type='IPCA + taxa', contracted_rate=6, ipca_rate=4))
        self.assertEqual(1102.40, ipca['current_value'])

    def test_future_application_has_no_earnings_or_fake_history(self):
        item = self.item(application_date=(self.today+timedelta(days=5)).isoformat())
        result = investments.calculated(item)
        self.assertEqual(1000, result['current_value'])
        self.assertIsNone(result['monthly_estimated_gain'])
        self.assertEqual([], investments.fixed_income_history(item, '1y'))

    def test_normalization_validates_rate_period_and_reference_balance(self):
        normalized = investments.normalize_payload(self.item())
        self.assertEqual('automatic', normalized['valuation_mode'])
        for changes in ({'rate_period': 'day'}, {'valuation_mode': 'unknown'},
                        {'valuation_mode': 'balance'}, {'contracted_rate': -1},
                        {'valuation_mode': 'balance', 'current_value_manual': 1000,
                         'current_value_date': '2027-01-01'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                investments.normalize_payload(self.item(**changes))

    def test_fixed_portfolio_graph_is_generated_immediately_and_matches_summary(self):
        item = self.item()
        store = {'investments': [item], 'history': [], 'updated_at': None}
        with patch.object(investments, 'load_store', return_value=store):
            portfolio = investments.portfolio()
        self.assertEqual('estimated', portfolio['history_source'])
        self.assertGreater(len(portfolio['history']), 2)
        self.assertEqual(1000, portfolio['history'][0]['current_value'])
        self.assertEqual(portfolio['summary']['current_value'], portfolio['history'][-1]['current_value'])
        self.assertEqual([], store['history'])

    def test_manual_balance_after_maturity_is_preserved(self):
        item = self.item(valuation_mode='manual', current_value_manual=1200,
                         current_value_date=self.today.isoformat(),
                         maturity_date=(self.today-timedelta(days=10)).isoformat())
        self.assertEqual(1200, investments.fixed_income_value(item))

    def test_portfolio_graph_excludes_capital_before_each_application(self):
        first = self.item()
        second = self.item(amount_invested=500, application_date=self.today.isoformat())
        history = investments.fixed_portfolio_history([first, second])
        self.assertEqual(1000, history[0]['amount_applied'])
        self.assertEqual(1500, history[-1]['amount_applied'])
        self.assertEqual(1620, history[-1]['current_value'])
