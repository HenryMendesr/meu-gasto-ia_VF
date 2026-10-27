import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api import index
from src import storage, investments, recurring, cards, trust, planning, portability


class CardBillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'db.sqlite'),patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups'),patch.object(investments,'investment_today',return_value=date(2026,10,27))]
        for mock in self.patches:mock.start()
        investments.set_cash_balance({'amount':1000});self.card=recurring.save_card({'name':'Nubank','due_day':5,'closing_day':20,'limit':5000})
        self.payload={'card_id':self.card['id'],'date':'2026-10-19','where':'Loja','amount':100,'category':'Mercado','installments':3}

    def tearDown(self):
        for mock in reversed(self.patches):mock.stop()
        self.temp.cleanup()

    def prefs(self):return investments.load_store().get('preferences',{})

    def test_closing_boundary_year_rollover_and_short_month(self):
        self.assertEqual('2026-11',cards.first_invoice(self.card,'2026-10-19'))
        self.assertEqual('2026-12',cards.first_invoice(self.card,'2026-10-20'))
        self.assertEqual('2027-02',cards.first_invoice(self.card,'2026-12-31'))
        card={**self.card,'closing_day':10,'due_day':30}
        self.assertEqual('2026-10',cards.first_invoice(card,'2026-10-09'))
        item=cards.purchase({**self.payload,'first_invoice_month':'2027-02','installments':1})
        self.assertEqual('2027-02-05',cards.parts(item)[0]['date'])

    def test_installments_preserve_cents_and_do_not_create_cash_expense(self):
        item=cards.purchase(self.payload);self.assertEqual([33.33,33.33,33.34],[part['amount'] for part in cards.parts(item)])
        self.assertEqual(100,sum(part['amount'] for part in cards.parts(item)))
        self.assertEqual(0,planning.monthly_report('2026-11')['cash_expenses'])
        self.assertEqual(33.33,trust.insights('2026-11')['cash_expenses'])
        self.assertEqual(1000,investments.portfolio()['summary']['cash_balance'])

    def test_partial_payment_only_counts_once_then_reversal_reopens(self):
        cards.purchase(self.payload);key=cards.status('2026-11')['invoices'][0]['key']
        payload={'invoice_key':key,'date':'2026-10-27','amount':20,'request_id':'payment1'}
        payment=cards.pay(payload);cards.pay(payload)
        bill=cards.status('2026-11')['invoices'][0];self.assertEqual(13.33,bill['remaining']);self.assertEqual('partial',bill['status'])
        self.assertEqual(20,planning.monthly_report('2026-10')['cash_expenses']);self.assertEqual(0,planning.monthly_report('2026-11')['cash_expenses'])
        cards.reverse_payment(payment['id']);cards.reverse_payment(payment['id'])
        self.assertEqual(0,planning.monthly_report('2026-10')['cash_expenses']);self.assertEqual(33.33,cards.status('2026-11')['remaining'])

    def test_purchase_edit_and_deletion_require_reversing_affected_payments(self):
        item=cards.purchase(self.payload);bill=cards.status('2026-11')['invoices'][0]
        payment=cards.pay({'invoice_key':bill['key'],'date':'2026-10-27','amount':20,'request_id':'paid'})
        before=investments.load_store()
        with self.assertRaises(ValueError):cards.purchase({**self.payload,'id':item['id'],'amount':200})
        with self.assertRaises(ValueError):cards.delete_purchase(item['id'])
        self.assertEqual(before,investments.load_store());cards.reverse_payment(payment['id']);cards.delete_purchase(item['id'])
        self.assertEqual([],cards.status('2026-11')['invoices']);portability.validate(storage.export_financial_data())

    def test_linking_existing_credit_expense_suppresses_original_and_survives_restore(self):
        original=storage.add_expense({'date':'2026-10-10','amount':100,'where':'Loja','category':'Mercado','payment':'Crédito'})
        self.assertEqual(100,planning.monthly_report('2026-10')['cash_expenses'])
        item=cards.purchase({**self.payload,'linked_expense_id':original['id'],'installments':1})
        self.assertEqual(0,planning.monthly_report('2026-10')['cash_expenses'])
        backup=storage.export_financial_data();storage.restore_financial_data(backup)
        planned=cards.planned_expenses(storage.read_expenses(),self.prefs());self.assertEqual(1,len(planned));self.assertTrue(planned[0]['finance']['card_purchase_id'])
        key=cards.status('2026-11')['invoices'][0]['key'];cards.pay({'invoice_key':key,'date':'2026-10-27','amount':100,'request_id':'full'})
        self.assertEqual(100,planning.monthly_report('2026-10')['cash_expenses']);self.assertEqual('paid',cards.status('2026-11')['invoices'][0]['status'])

    def test_duplicate_requests_and_overpayment_do_not_duplicate_or_mutate(self):
        first=cards.purchase({**self.payload,'request_id':'same'});again=cards.purchase({**self.payload,'request_id':'same'})
        self.assertEqual(first['id'],again['id']);self.assertEqual(1,len(self.prefs()['card_purchases']))
        bill=cards.status('2026-11')['invoices'][0];before=investments.load_store()
        with self.assertRaises(ValueError):cards.pay({'invoice_key':bill['key'],'date':'2026-10-27','amount':50,'request_id':'too-much'})
        self.assertEqual(before,investments.load_store())

    def test_invalid_backup_with_orphan_purchase_or_overpayment_is_rejected(self):
        cards.purchase(self.payload);backup=storage.export_financial_data();bad=copy.deepcopy(backup)
        bad['data']['portfolio']['preferences']['card_purchases'][0]['card_id']='f'*32
        with self.assertRaises(ValueError):portability.validate(bad)
        key=cards.status('2026-11')['invoices'][0]['key'];cards.pay({'invoice_key':key,'date':'2026-10-27','amount':20,'request_id':'paid'})
        bad=storage.export_financial_data();bad['data']['portfolio']['preferences']['card_payments'][0]['amount']=500
        with self.assertRaises(ValueError):portability.validate(bad)

    def test_manual_income_is_forecast_until_explicitly_confirmed(self):
        storage.set_income({'month':'2026-10','cash':4000,'voucher':0,'confirmed':False})
        data=trust.insights('2026-10')['income'];self.assertEqual(0,data['used']);self.assertEqual(4000,data['expected']);self.assertEqual(4000,data['pending'])
        storage.set_income({'month':'2026-10','cash':3800,'voucher':0,'confirmed':True})
        data=trust.insights('2026-10')['income'];self.assertEqual(3800,data['used']);self.assertEqual(0,data['pending'])

    def test_scheduled_income_preserves_forecast_and_confirmed_separately(self):
        recurring.save_plan({'enabled':True,'start_month':'2026-10','source':'Empresa','payments':[{'day':15,'amount':1500},{'day':30,'amount':2500}]})
        data=trust.insights('2026-10');self.assertEqual(0,data['confirmed_income']);self.assertEqual(4000,data['expected_income'])
        recurring.receipt_action('2026-10:1',{'action':'confirm','amount':1400})
        data=trust.insights('2026-10');self.assertEqual(1400,data['confirmed_income']);self.assertEqual(3900,data['expected_income']);self.assertEqual(2500,data['income']['pending'])
        self.assertEqual(1400,planning.monthly_report('2026-10')['income'])

    def test_card_api_scoped_bootstrap_and_missing_card_rejected(self):
        client=TestClient(index.fastapi_app)
        self.assertEqual(401,client.get('/api/cards?month=2026-11').status_code)
        with patch.object(index.auth,'session_user',return_value=1):
            self.assertEqual(400,client.post('/api/cards/purchase',json={**self.payload,'card_id':'f'*32}).status_code)
            self.assertEqual(200,client.post('/api/cards/purchase',json=self.payload).status_code)
            rows=client.get('/api/bootstrap').json()['expenses'];self.assertEqual(3,len(rows));self.assertTrue(all(row['finance']['card_purchase_id'] for row in rows))
            self.assertEqual(33.33,client.get('/api/cards?month=2026-11').json()['total'])

    def test_early_payment_moves_projection_to_payment_month_without_duplicate_future_reserve(self):
        cards.purchase({**self.payload,'installments':1});bill=cards.status('2026-11')['invoices'][0]
        cards.pay({'invoice_key':bill['key'],'date':'2026-10-27','amount':100,'request_id':'early'})
        october=trust.insights('2026-10');november=trust.insights('2026-11')
        self.assertEqual(100,october['projected_expenses']);self.assertEqual(0,november['projected_expenses'])
        self.assertEqual(100,november['cash_expenses']);self.assertEqual(100,planning.monthly_report('2026-10')['cash_expenses'])

    def test_linked_original_is_protected_from_generic_expense_api_edits(self):
        original=storage.add_expense({'date':'2026-10-10','amount':100,'where':'Loja','category':'Mercado','payment':'Crédito'})
        cards.purchase({**self.payload,'linked_expense_id':original['id'],'installments':1})
        with patch.object(index.auth,'session_user',return_value=1):
            client=TestClient(index.fastapi_app)
            self.assertEqual(400,client.delete('/api/expenses/'+str(original['id'])).status_code)
            self.assertEqual(400,client.put('/api/expenses/'+str(original['id']),json={'amount':2}).status_code)
        self.assertEqual(1,len(storage.read_expenses()))

    def test_later_purchase_can_reopen_bill_already_paid(self):
        cards.purchase({**self.payload,'installments':1});bill=cards.status('2026-11')['invoices'][0]
        cards.pay({'invoice_key':bill['key'],'date':'2026-10-27','amount':100,'request_id':'paid'})
        cards.purchase({**self.payload,'where':'Outra compra','amount':25,'installments':1})
        bill=cards.status('2026-11')['invoices'][0];self.assertEqual(25,bill['remaining']);self.assertEqual(100,bill['paid'])

    def test_imported_invoice_payment_requires_review_instead_of_automatic_selection(self):
        from src import statement_import
        entry={'date':'2026-10-27','amount':100,'where':'Pagamento de fatura Nubank','kind':'expense','category':'Contas','payment':'Débito','selected':True,'flags':[],'confidence':.9,'description':'','needs_review':False}
        result=statement_import.analyze([entry],[],[])
        self.assertFalse(result['items'][0]['selected']);self.assertTrue(result['items'][0]['needs_review'])
        self.assertTrue(any('fatura' in flag for flag in result['items'][0]['flags']))

    def test_salary_received_in_another_month_is_counted_on_actual_date(self):
        recurring.save_plan({'enabled':True,'start_month':'2026-09','source':'Empresa','payments':[{'day':15,'amount':1500}]})
        recurring.receipt_action('2026-09:1',{'action':'confirm','amount':1400,'received_date':'2026-10-01'})
        september=trust.insights('2026-09')['income'];october=trust.insights('2026-10')['income']
        self.assertEqual(0,september['used']);self.assertEqual(0,september['expected'])
        self.assertEqual(1400,october['used']);self.assertEqual(2900,october['expected'])
        transaction=next(entry for entry in planning.monthly_report('2026-10')['transactions'] if entry['kind']=='Salário confirmado')
        self.assertEqual('2026-10-01',transaction['date']);self.assertEqual(1400,transaction['amount'])
