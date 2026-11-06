import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api import index
from src import fixed_expenses as fixed, investments, storage, cards, trust, planning, portability, recurring


class FixedExpenseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'db.sqlite'),patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups'),patch.object(investments,'investment_today',return_value=date(2026,10,29))]
        for p in self.patches:p.start()
        self.payload={'name':'Aluguel','amount':'900','day':'31','from_month':'2026-09','category':'Moradia','payment':'Pix'}

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def create(self,**changes):return fixed.save({**self.payload,**changes})

    def test_fixed_expense_repeats_clamps_day_and_only_paid_is_actual(self):
        self.create()
        self.assertEqual('2026-09-30',fixed.status('2026-09')['items'][0]['row']['date'])
        self.assertEqual(900,fixed.status('2027-02')['total'])
        self.assertEqual('2027-02-28',fixed.status('2027-02')['items'][0]['row']['date'])
        self.assertEqual(900,trust.insights('2026-10')['projected_expenses'])
        self.assertEqual(0,trust.insights('2026-10')['actual_expenses'])
        self.assertEqual(0,planning.monthly_report('2026-10')['cash_expenses'])

    def test_confirmation_is_idempotent_and_follows_actual_date(self):
        plan=self.create()
        payload={'id':plan['id'],'month':'2026-11','action':'pay','paid_date':'2026-10-29'}
        fixed.payment(payload);fixed.payment(payload)
        self.assertEqual(900,planning.monthly_report('2026-10')['cash_expenses'])
        self.assertEqual(0,planning.monthly_report('2026-11')['cash_expenses'])
        self.assertEqual(1800,trust.insights('2026-10')['projected_expenses']) # October pending + November paid early.
        self.assertEqual(0,trust.insights('2026-11')['projected_expenses'])
        self.assertEqual(0,planning.monthly_report('2026-10')['debt_paid'])
        self.assertEqual('Gasto fixo pago',planning.monthly_report('2026-10')['transactions'][0]['kind'])
        self.assertEqual(0,investments.portfolio()['summary']['cash_balance'])
        fixed.payment({**payload,'action':'undo'})
        self.assertEqual(0,planning.monthly_report('2026-10')['cash_expenses'])
        self.assertEqual(900,trust.insights('2026-11')['projected_expenses'])

    def test_edit_keeps_history_and_confirmed_payment_but_changes_future(self):
        plan=self.create()
        fixed.payment({'id':plan['id'],'month':'2026-10','action':'pay','paid_date':'2026-10-20'})
        self.create(id=plan['id'],amount=950,from_month='2026-10',name='Aluguel novo')
        self.assertEqual(900,fixed.status('2026-09')['total'])
        self.assertEqual(900,fixed.status('2026-10')['total'])
        self.assertEqual(950,fixed.status('2026-11')['total'])
        self.assertEqual('Aluguel',fixed.status('2026-10')['items'][0]['row']['where'])
        with self.assertRaises(ValueError):self.create(id=plan['id'],from_month='2026-09')

    def test_pause_and_skip_preserve_other_months_and_paid_snapshot(self):
        plan=self.create()
        fixed.payment({'id':plan['id'],'month':'2026-10','action':'skip'})
        self.assertEqual(0,fixed.status('2026-10')['total'])
        self.assertEqual(900,fixed.status('2026-11')['total'])
        fixed.payment({'id':plan['id'],'month':'2026-10','action':'restore'})
        fixed.payment({'id':plan['id'],'month':'2026-10','action':'pay','paid_date':'2026-10-20'})
        self.create(id=plan['id'],enabled=False,from_month='2026-10')
        self.assertEqual(900,fixed.status('2026-10')['total'])
        self.assertEqual(0,fixed.status('2026-11')['total'])
        self.assertEqual(900,fixed.status('2026-09')['total'])
        portability.validate(storage.export_financial_data())

    def test_invalid_values_and_future_payment_are_atomic(self):
        plan=self.create();before=investments.load_store()
        for changes in ({'day':'0'},{'day':'1.5'},{'amount':float('nan')},{'payment':'Crédito'},{'category':'Desconhecida'}):
            with self.assertRaises(ValueError):self.create(id=plan['id'],from_month='2026-10',**changes)
            self.assertEqual(before,investments.load_store())
        with self.assertRaises(ValueError):fixed.payment({'id':plan['id'],'month':'2026-10','action':'pay','paid_date':'2026-10-30'})
        self.assertEqual(before,investments.load_store())

    def test_export_restore_validates_owner_links_and_preserves_totals(self):
        plan=self.create();fixed.payment({'id':plan['id'],'month':'2026-10','action':'pay','paid_date':'2026-10-20'})
        backup=storage.export_financial_data();validated=portability.validate(backup)
        self.assertEqual(900,fixed.expense_rows(validated['portfolio']['preferences'])[1]['amount'])
        bad=copy.deepcopy(backup);p=bad['data']['portfolio']['preferences'];p['fixed_payments']['f'*32+':2026-10']=p['fixed_payments'].pop(plan['id']+':2026-10')
        with self.assertRaises(ValueError):portability.validate(bad)
        with self.assertRaises(ValueError):cards.ensure_category_editable('Moradia')

    def test_salary_legacy_and_fixed_expense_do_not_duplicate_income(self):
        self.create()
        recurring.save_plan({'enabled':True,'source':'Empresa','start_month':'2026-10','payments':[{'day':15,'amount':1500},{'day':30,'amount':2000}]})
        insights=trust.insights('2026-10')
        self.assertEqual(3500,insights['expected_income']);self.assertEqual(2600,insights['balance'])
        # Day 15 has passed; day 30 remains forecast on the fixed October 29 clock.
        self.assertEqual(1500,insights['confirmed_income'])
        self.assertEqual(2000,insights['income']['pending'])

    def test_new_routes_return_same_fixed_rows_as_bootstrap(self):
        with patch.object(index,'protected',return_value=None),TestClient(index.app) as client:
            result=client.post('/api/recurring/fixed-save',json=self.payload)
            self.assertEqual(200,result.status_code);plan=result.json()['item']
            listing=client.get('/api/fixed-expenses?month=2026-10').json()
            self.assertEqual(900,listing['total'])
            response=client.post('/api/recurring/fixed-payment',json={'id':plan['id'],'month':'2026-10','action':'pay','paid_date':'2026-10-20'})
            self.assertEqual(200,response.status_code)
            bootstrap=client.get('/api/bootstrap').json()
            rows=[r for r in bootstrap['expenses'] if r['finance'].get('fixed_expense_id')==plan['id'] and r['date'].startswith('2026-10')]
            self.assertEqual(1,len(rows));self.assertTrue(rows[0]['finance']['paid'])

    def test_voucher_fixed_expense_stays_out_of_cash_summary(self):
        self.create(payment='Voucher')
        state=fixed.status('2026-10')
        self.assertEqual(0,state['total']);self.assertEqual(900,state['voucher_total'])
        self.assertEqual(0,trust.insights('2026-10')['projected_expenses'])
        self.assertEqual(900,trust.insights('2026-10')['voucher_expenses'])
