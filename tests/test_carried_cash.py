import unittest
from datetime import date
from unittest.mock import patch
from src.trust import carried_cash, income_basis, actual_cash


class CarriedCashTests(unittest.TestCase):
    def test_rollover_spending_negative_and_next_receipt(self):
        incomes = {'2026-09': {'cash': 1000}, '2026-11': {'cash': 700}}
        prefs = {'income_confirmed': {'2026-09': True, '2026-11': True}}
        rows = [{'date': '2026-09-10', 'amount': 300, 'payment': 'Pix'},
                {'date': '2026-10-10', 'amount': 900, 'payment': 'Pix'}]
        with patch('src.investments.investment_today', return_value=date(2026, 11, 20)):
            self.assertEqual(700, carried_cash('2026-10', rows, incomes, [], prefs)['opening_balance'])
            carry = carried_cash('2026-11', rows, incomes, [], prefs)
            self.assertEqual(-200, carry['opening_balance'])
            self.assertEqual(500, carry['opening_balance'] + income_basis('2026-11', incomes, [], prefs)['used'])

    def test_unconfirmed_income_and_voucher_do_not_inflate_balance(self):
        incomes = {'2026-09': {'cash': 1000}}
        rows = [{'date': '2026-09-10', 'amount': 50, 'payment': 'Voucher'}]
        self.assertEqual(0, carried_cash('2026-10', rows, incomes, [], {})['opening_balance'])

    def test_sources_not_doubled_and_payment_uses_actual_date(self):
        incomes = {'2026-09': {'cash': 1000}}
        entries = [{'date': '2026-09-01', 'amount': 1000}]
        prefs = {'income_confirmed': {'2026-09': True}}
        rows = [{'date': '2026-08-01', 'amount': 200, 'payment': 'Pix',
                 'finance': {'fixed_expense_id': 'a', 'paid': True, 'paid_date': '2026-09-15'}},
                {'date': '2026-09-01', 'amount': 900, 'payment': 'Pix',
                 'finance': {'fixed_expense_id': 'b', 'paid': False}}]
        with patch('src.investments.investment_today', return_value=date(2026, 11, 20)):
            self.assertEqual(800, carried_cash('2026-10', rows, incomes, entries, prefs)['opening_balance'])
