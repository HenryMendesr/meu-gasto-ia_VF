import unittest
from decimal import Decimal

from src.finance_rules import expense_finance, installment_plan, money


class FinancingTests(unittest.TestCase):
    def test_price_schedule_amortizes_principal_and_discounts_future_payments(self):
        parts = installment_plan(1000, 12, '2027-01-31', rate_value='2,5')
        self.assertEqual(97.49, parts[0]['amount'])
        self.assertEqual(25, parts[0]['interest'])
        self.assertEqual(72.49, parts[0]['amortization'])
        self.assertEqual(0, parts[-1]['balance_after'])
        self.assertEqual(1000, round(sum(p['amortization'] for p in parts), 2))
        present_value = sum(p['amount'] / 1.025 ** p['number'] for p in parts)
        self.assertAlmostEqual(1000, present_value, delta=0.05)
        self.assertEqual('2027-02-28', parts[1]['date'])

    def test_missing_quantity_is_inferred_without_a_phantom_cent_installment(self):
        parts = installment_plan(100, '', '2027-01-31', 33.33)
        self.assertEqual(3, len(parts))
        self.assertEqual(33.34, parts[-1]['amount'])

    def test_missing_payment_is_calculated_with_interest(self):
        parts = installment_plan(1000, 12, '2027-01-01', '', 2)
        self.assertEqual(94.56, parts[0]['amount'])
        inferred = installment_plan(1000, '', '2027-01-01', 94.56, 2)
        self.assertEqual(12, len(inferred))

    def test_invalid_rates_counts_and_non_amortizing_payments_are_rejected(self):
        for count, payment, rate in [(12, 20, 2), (12, None, -1), (12, None, 'NaN'),
                                     (12, None, 101), (2.5, None, 0), ('', 1, 0),
                                     (2, 1000, 0)]:
            with self.subTest(count=count, payment=payment, rate=rate), self.assertRaises(ValueError):
                installment_plan(1000, count, '2027-01-01', payment, rate)

    def test_non_finite_money_is_rejected(self):
        for value in ('NaN', 'Infinity', Decimal('-Infinity')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value)

    def test_sac_mortgage_has_constant_principal_and_declining_interest(self):
        parts = installment_plan(240000, 360, '2027-01-31', rate_value='0,8',
                                 system='sac', max_count=600, min_count=1)
        self.assertEqual(360, len(parts))
        self.assertEqual(2586.67, parts[0]['amount'])
        self.assertEqual(666.67, parts[0]['amortization'])
        self.assertLess(parts[-1]['amount'], parts[0]['amount'])
        self.assertEqual(0, parts[-1]['balance_after'])
        self.assertEqual(240000, round(sum(p['amortization'] for p in parts), 2))

    def test_dedicated_debt_supports_single_payment_and_validates_type(self):
        payload = {'date': '2026-10-23', 'amount': 500, 'financing_kind': 'debt',
                   'debt_entry': True, 'debt_type': 'Acordo / renegociação',
                   'installment': True, 'installment_count': 1, 'interest_rate': 2,
                   'first_charge_date': '2026-11-23'}
        _, parts, details = expense_finance(payload, payload['date'], 'Pix')
        self.assertEqual([510], [p['amount'] for p in parts])
        self.assertEqual('debt', details['financing_kind'])
        with self.assertRaises(ValueError):
            expense_finance({**payload, 'debt_type': 'Imóvel'}, payload['date'], 'Pix')

    def test_financing_rejects_inconsistent_down_payment_and_unknown_system(self):
        payload = {'date': '2026-10-23', 'amount': 800, 'financing_kind': 'asset',
                   'debt_entry': True, 'debt_type': 'Veículo', 'asset_name': 'Carro',
                   'asset_value': 1000, 'down_payment': 200, 'installment': True,
                   'installment_count': 12, 'first_charge_date': '2026-11-23'}
        _, parts, details = expense_finance(payload, payload['date'], 'Transferência')
        self.assertEqual(800, details['principal'])
        for changes in ({'down_payment': 1000}, {'down_payment': -1},
                        {'down_payment': 'NaN'}, {'amount': 900},
                        {'asset_name': ''}, {'amortization_system': 'unknown'},
                        {'installment_count': 601}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                expense_finance({**payload, **changes}, payload['date'], 'Transferência')
