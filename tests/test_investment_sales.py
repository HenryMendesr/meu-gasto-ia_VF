import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api import index
from src import investments, storage


class InvestmentSalesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(storage, 'DATABASE', Path(self.temp.name) / 'test.db'),
                        patch.object(storage, 'BACKUPS', Path(self.temp.name) / 'backups'),
                        patch.object(investments, 'investment_today', return_value=date(2026, 10, 27))]
        for mock in self.patches:
            mock.start()
        investments.set_cash_balance({"amount": 10000})
        self.stock = investments.create_investment({'type': 'Ações', 'symbol': 'PETR4', 'quantity': 100,
                                                    'average_price': 30, 'current_price': 34,
                                                    'purchase_date': '2026-01-01'})

    def tearDown(self):
        for mock in reversed(self.patches):
            mock.stop()
        self.temp.cleanup()

    def sell(self, **overrides):
        payload = {'date': '2026-10-20', 'quantity': 40, 'mode': 'unit', 'value': 35}
        payload.update(overrides)
        return investments.sell_investment(self.stock['id'], payload)

    def test_partial_and_full_sale_keep_realized_gain_without_double_counting(self):
        partial = self.sell()
        self.assertEqual(1400, partial['sale']['total'])
        self.assertEqual(200, partial['sale']['profit_loss'])
        self.assertEqual(60, partial['investment']['remaining_quantity'])
        summary = investments.portfolio()['summary']
        self.assertEqual(2040, summary['current_value'])
        self.assertEqual(1800, summary['amount_applied'])
        self.assertEqual(200, summary['realized_profit_loss'])
        self.assertEqual(240, summary['unrealized_profit_loss'])
        self.assertEqual(440, summary['profit_loss'])
        final = self.sell(date='2026-10-21', quantity=60, mode='total', value=1800)
        self.assertEqual(30, final['sale']['unit_price'])
        self.assertEqual(0, final['investment']['remaining_quantity'])
        summary = investments.portfolio()['summary']
        self.assertEqual(0, summary['current_value'])
        self.assertEqual(0, summary['amount_applied'])
        self.assertEqual(200, summary['profit_loss'])
        self.assertAlmostEqual(200 / 3000 * 100, summary['return_percent'], places=4)
        self.assertEqual(200, investments.load_store()['history'][-1]['profit_loss'])

    def test_invalid_sales_do_not_modify_position(self):
        for invalid in ({'quantity': 101}, {'quantity': 0}, {'value': -1}, {'value': 'nan'},
                        {'mode': 'invalid'}, {'date': '2025-12-31'}, {'date': '2026-10-28'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.sell(**invalid)
        self.assertEqual(100, investments.portfolio()['investments'][0]['remaining_quantity'])
        self.assertNotIn('sales', investments.load_store()['investments'][0])

    def test_retries_are_idempotent_and_sales_survive_edits(self):
        self.sell(request_id='same-request')
        self.sell(request_id='same-request')
        item = investments.load_store()['investments'][0]
        self.assertEqual(1, len(item['sales']))
        result = investments.update_investment(item['id'], {**item, 'current_price': 36})
        self.assertEqual(1, len(result['sales']))
        self.assertEqual(60, result['remaining_quantity'])
        with self.assertRaises(ValueError):
            investments.update_investment(item['id'], {**item, 'quantity': 200})
        with self.assertRaises(ValueError):
            investments.delete_investment(item['id'])

    def test_gains_apply_sales_only_after_their_date_and_preserve_closed_result(self):
        self.sell()
        quotes = lambda *_: {'source': 'Teste', 'points': [
            {'date': '2025-12-31', 'price': 20},
            {'date': '2026-10-19', 'price': 32}, {'date': '2026-10-20', 'price': 34},
            {'date': '2026-10-27', 'price': 36}]}
        history = investments.investment_history(self.stock['id'], 'all', market_fetcher=quotes)
        gains = {point['date']: point['value'] for point in history['gain_points']}
        self.assertEqual(0, gains['2026-01-01'])
        self.assertEqual(200, gains['2026-10-19'])
        self.assertEqual(440, gains['2026-10-20'])
        self.assertEqual(560, gains['2026-10-27'])
        self.sell(date='2026-10-21', quantity=60, mode='total', value=1800)
        history = investments.investment_history(self.stock['id'], 'all', market_fetcher=quotes)
        self.assertEqual({'date': '2026-10-27', 'value': 200}, history['gain_points'][-1])

    def test_sale_api_requires_login_and_passes_authenticated_user(self):
        client = TestClient(index.fastapi_app)
        endpoint = f"/api/investments/{self.stock['id']}/sales"
        with patch.object(index.auth, 'session_user', return_value=None):
            self.assertEqual(401, client.post(endpoint, json={}).status_code)
        with patch.object(index.auth, 'session_user', return_value=42), patch.object(investments, 'sell_investment', return_value={'sale': {}}) as sell:
            response = client.post(endpoint, json={'quantity': 1})
            self.assertEqual(200, response.status_code)
            sell.assert_called_once_with(self.stock['id'], {'quantity': 1}, 42)
        with patch.object(index.auth, 'session_user', return_value=42), patch.object(investments, 'sell_investment', side_effect=ValueError('Quantidade inválida')):
            self.assertEqual(400, client.post(endpoint, json={}).status_code)

    def test_market_fetch_preserves_candle_and_volume_values(self):
        response = {'chart': {'result': [{'timestamp': [1793059200], 'indicators': {'quote': [
            {'close': [34], 'open': [32], 'high': [35], 'low': [31], 'volume': [1000]}]}}]}}
        with patch.object(investments, 'fetch_json', return_value=response):
            point = investments.fetch_market_history('PETR4', '3m')['points'][0]
        self.assertEqual(34, point['price'])
        self.assertEqual(32, point['open'])
        self.assertEqual(35, point['high'])
        self.assertEqual(31, point['low'])
        self.assertEqual(1000, point['volume'])
