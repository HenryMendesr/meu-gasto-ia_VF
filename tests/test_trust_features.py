"""Financial reversibility and account ownership regression checks."""
import copy
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api import index
from src import investments, storage, trust, portability, auth, account_security, account_service, planning


def stock():return {'type':'Ações','symbol':'PETR4','quantity':10,'average_price':30,'current_price':30,'purchase_date':'2026-10-01'}


class TrustFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.patches=[patch.object(storage,'DATABASE',root/'test.db'),patch.object(storage,'BACKUPS',root/'backups'),patch.object(auth,'AUTH_FILE',root/'auth.json'),patch.object(auth,'PBKDF2_ITERATIONS',1000),patch.object(investments,'investment_today',return_value=date(2026,10,27)),patch.dict(os.environ,{},clear=False)]
        for p in self.patches:p.start()
        for key in ('APP_PASSWORD','DATABASE_URL','SESSION_SECRET'):os.environ.pop(key,None)
        investments.set_cash_balance({'amount':10000});self.item=investments.create_investment(stock());self.op='initial-'+self.item['id']

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def change(self,payload,op=None):
        result=trust.operation_change(self.item['id'],op or self.op,payload,preview=True)
        return trust.operation_change(self.item['id'],op or self.op,{**payload,'revision':result['revision']})

    def test_correction_preview_is_readonly_then_cash_and_basis_change_once(self):
        before=investments.load_store();payload={'action':'edit','date':'2026-10-01','quantity':10,'unit_price':32,'fees':2,'reason':'Nota de corretagem'}
        preview=trust.operation_change(self.item['id'],self.op,payload,preview=True)
        self.assertEqual(before,investments.load_store());self.assertEqual(9678,preview['cash_after']);self.assertEqual(32.2,preview['average_after'])
        self.change(payload);self.assertEqual(9678,investments.portfolio()['summary']['cash_balance'])
        self.assertEqual('operation_edit',investments.load_store()['audit_log'][-1]['kind'])
        with self.assertRaises(ValueError):trust.operation_change(self.item['id'],self.op,{**payload,'revision':preview['revision']})

    def test_reversal_restoration_and_later_sale_dependencies(self):
        self.change({'action':'reverse','reason':'Compra duplicada'})
        self.assertEqual(10000,investments.portfolio()['summary']['cash_balance']);self.assertEqual(0,investments.portfolio()['investments'][0]['remaining_quantity'])
        self.change({'action':'restore','reason':'Compra conferida'});self.assertEqual(9700,investments.portfolio()['summary']['cash_balance'])
        investments.sell_investment(self.item['id'],{'date':'2026-10-10','quantity':4,'mode':'unit','value':40})
        before=investments.load_store()
        with self.assertRaises(ValueError):self.change({'action':'reverse','reason':'Compra duplicada'})
        self.assertEqual(before,investments.load_store())

    def test_sale_reversal_debits_only_net_and_report_excludes_it(self):
        sale=investments.sell_investment(self.item['id'],{'date':'2026-10-10','quantity':4,'mode':'unit','value':40,'fees':5})['sale']
        self.change({'action':'reverse','reason':'Venda duplicada'},sale['id'])
        self.assertEqual(9700,investments.portfolio()['summary']['cash_balance']);self.assertEqual(10,investments.portfolio()['investments'][0]['remaining_quantity'])
        self.assertEqual(0,planning.monthly_report('2026-10')['sales'])

    def test_insufficient_cash_reversal_is_atomic(self):
        income=investments.add_investment_income(self.item['id'],{'date':'2026-10-15','kind':'Dividendos','amount':20})['income']
        investments.set_cash_balance({'amount':0});before=investments.load_store()
        with self.assertRaises(ValueError):self.change({'action':'reverse','reason':'Provento duplicado'},income['id'])
        self.assertEqual(before,investments.load_store())

    def test_legacy_correction_does_not_retroactively_debit_cash(self):
        def legacy(store):
            item=store['investments'][0];item.pop('cash_funded_amount');item.pop('buys')
        investments.mutate_store(legacy)
        self.change({'action':'edit','date':'2026-10-01','quantity':10,'unit_price':40,'reason':'Preço original errado'})
        self.assertEqual(9700,investments.portfolio()['summary']['cash_balance'])
        item=investments.load_store()['investments'][0];investments.update_investment(item['id'],item)
        self.assertEqual(9700,investments.portfolio()['summary']['cash_balance']);self.assertTrue(investments.load_store()['investments'][0]['operation_corrected'])

    def test_income_mode_is_consistent_and_does_not_double_count(self):
        storage.add_income_entry({'date':'2026-10-01','amount':5000,'where':'Empresa','category':'Salário'})
        for mode,expected in [('auto',4000),('declared',4000),('imported',5000)]:
            storage.set_income({'month':'2026-10','cash':4000,'voucher':100,'income_mode':mode})
            self.assertEqual(expected,trust.insights('2026-10')['income']['used']);self.assertEqual(expected,planning.monthly_report('2026-10')['income'])

    def test_backup_roundtrip_safety_copy_and_no_credentials(self):
        auth.setup('old-password-123','old-password-123');account_security.generate_codes('old-password-123')
        storage.add_expense({'date':'2026-10-02','amount':100,'where':'Mercado','category':'Mercado','payment':'Pix'})
        exported=storage.export_financial_data();data=portability.validate(exported)
        self.assertEqual(1,len(data['expenses']));self.assertNotIn('password_hash',json.dumps(exported));self.assertNotIn('recovery_hashes',json.dumps(exported))
        investments.set_cash_balance({'amount':1234});storage.restore_financial_data(exported)
        self.assertEqual(9700,investments.portfolio()['summary']['cash_balance']);self.assertEqual(1234,storage.previous_financial_backup()['data']['portfolio']['cash_balance'])
        self.assertFalse(investments.load_store()['preferences']['analytics_consent']);self.assertTrue(auth.verify_password('old-password-123'))

    def test_malformed_backup_cannot_mutate_account(self):
        original=storage.export_financial_data();before=investments.load_store()
        for value in [None,[],{'income_modes':[]},{'analytics_consent':'true'}]:
            bad=copy.deepcopy(original);bad['data']['portfolio']['preferences']=value
            with self.assertRaises(ValueError):storage.restore_financial_data(bad)
            self.assertEqual(before,investments.load_store())
        bad=copy.deepcopy(original);bad['data']['portfolio']['investments'][0]['buys'][0]['total']=123
        with self.assertRaises(ValueError):storage.restore_financial_data(bad)

    def test_recovery_codes_single_use_and_session_revocation(self):
        auth.setup('old-password-123','old-password-123');token=auth.create_session();codes=account_security.generate_codes('old-password-123')
        self.assertEqual(6,len(codes));self.assertNotIn(codes[0],auth.AUTH_FILE.read_text())
        account_security.recover('',codes[0],'new-password-123');self.assertFalse(auth.verify_session(token));self.assertTrue(auth.verify_password('new-password-123'))
        with self.assertRaises(ValueError):account_security.recover('',codes[0],'another-password')
        self.assertEqual(5,account_security.status()['recovery_codes_remaining'])
        fresh=auth.create_session();account_security.change_password('new-password-123','third-password-123');self.assertFalse(auth.verify_session(fresh))

    def test_consent_off_drops_counts_and_feedback_stays_in_account(self):
        self.assertFalse(trust.usage_event({'name':'report_opened'})['recorded'])
        trust.preferences({'analytics_consent':True});self.assertTrue(trust.usage_event({'name':'report_opened'})['recorded'])
        self.assertEqual(1,investments.load_store()['usage_metrics']['2026-10-27']['report_opened'])
        trust.preferences({'analytics_consent':False});self.assertNotIn('usage_metrics',investments.load_store())
        trust.feedback({'rating':4,'message':'Gostaria de uma busca melhor'});self.assertEqual(1,len(investments.load_store()['feedback']))

    def test_account_actions_require_password_and_explicit_confirmation(self):
        auth.setup('old-password-123','old-password-123');backup=storage.export_financial_data()
        with self.assertRaises(ValueError):account_service.restore({'backup':backup,'password':'wrong','confirmation':'RESTAURAR'})
        with self.assertRaises(ValueError):account_service.delete({'password':'old-password-123','confirmation':'sim'})
        self.assertTrue(auth.configured())

    def test_api_request_reference_and_authenticated_controls(self):
        with patch.object(index.auth,'session_user',return_value=1):
            client=TestClient(index.fastapi_app)
            result=client.get('/api/insights?month=2026-10');self.assertEqual(200,result.status_code);self.assertIn('x-request-id',result.headers)
            self.assertEqual(200,client.post('/api/preferences',json={'onboarding_dismissed':True}).status_code)
            self.assertEqual(400,client.post('/api/account/restore-preview',json={}).status_code)
            with patch.object(index.account_service,'diagnostic',side_effect=RuntimeError('private financial detail')):
                failed=client.get('/api/support/status');self.assertEqual(503,failed.status_code);self.assertNotIn('private financial detail',failed.text);self.assertIn('request_id',failed.json())

    def test_import_partial_retry_preserves_success_and_learns_confirmed_category(self):
        from src import statement_import
        rows=[{'kind':'expense','date':'2026-10-02','amount':25,'where':'Loja Teste','category':'Mercado','payment':'Pix'},
              {'kind':'expense','date':'invalid','amount':30,'where':'Outra loja','category':'Mercado','payment':'Pix'}]
        result=statement_import.commit_items({'items':rows})
        self.assertEqual([0],result['processed']);self.assertEqual(1,result['imported']);self.assertEqual(1,len(result['errors']))
        self.assertEqual(1,len(storage.read_expenses()))
        rules=investments.load_store()['preferences']['category_rules'];self.assertEqual('Mercado',rules['expense:'+statement_import.merchant_key('Loja Teste')])
        rows[1]['date']='2026-10-03';retry=statement_import.commit_items({'items':rows})
        self.assertEqual(1,retry['skipped']);self.assertEqual(1,retry['imported']);self.assertEqual(2,len(storage.read_expenses()))

    def test_hosted_export_and_delete_always_scope_owned_rows(self):
        from src import cloud_storage
        from unittest.mock import MagicMock
        cursor=MagicMock();cursor.fetchall.return_value=[];cursor.fetchone.return_value={'value':{'investments':[]}}
        db=MagicMock();db.cursor.return_value.__enter__.return_value=cursor
        with patch.object(cloud_storage,'initialize'),patch.object(cloud_storage,'connect') as connect:
            connect.return_value.__enter__.return_value=db
            cloud_storage.export_financial_data(42)
            queries=cursor.execute.call_args_list
            for call in queries:
                if ' FROM ' in call.args[0]:self.assertEqual((42,) if 'user_id' in call.args[0] else ('investments:42',),call.args[1])
            cursor.reset_mock();cursor.fetchone.return_value={'id':42}
            cloud_storage.delete_financial_account(42)
            for call in cursor.execute.call_args_list:
                sql=call.args[0]
                if sql.startswith('DELETE FROM app_state'):self.assertEqual(('investments:42','safety_backup:42'),call.args[1])
                elif sql.startswith('DELETE'):self.assertIn('WHERE',sql);self.assertEqual((42,),call.args[1])

    def test_hosted_session_revocation_rejects_prechange_token(self):
        with patch.object(index,'MULTI_USER',True),patch.object(index.storage,'session_version',return_value=2,create=True),patch.object(index.auth,'session_user',return_value=42),patch.object(index.auth,'token_version',return_value=1):
            self.assertEqual(401,TestClient(index.fastapi_app).get('/api/account/export').status_code)

    def test_account_delete_removes_finances_backups_and_access(self):
        auth.setup('old-password-123','old-password-123')
        account_service.delete({'password':'old-password-123','confirmation':'EXCLUIR'})
        self.assertFalse(auth.AUTH_FILE.exists());self.assertEqual([],storage.read_expenses());self.assertEqual([],investments.load_store()['investments'])

    def test_asset_remaining_balance_edit_keeps_original_asset_and_paid_row(self):
        payload={'date':'2026-10-01','amount':1000,'where':'Banco','category':'Contas','payment':'Pix','financing_kind':'asset','debt_entry':True,'asset_name':'Carro','asset_value':1500,'down_payment':500,'debt_type':'Veículo','installment':True,'installment_count':2,'interest_rate':0,'first_charge_date':'2026-10-10'}
        debt=storage.add_expense(payload);storage.set_debt_payment(debt['id'],{'paid':True,'paid_date':'2026-10-10'})
        paid=next(row for row in storage.read_expenses() if row['id']==debt['id'])
        storage.update_debt(debt['id'],{**payload,'amount':400,'installment_count':1,'first_charge_date':'2026-11-10','remaining_balance':True})
        rows=storage.read_expenses();self.assertEqual(paid,next(row for row in rows if row['id']==debt['id']))
        pending=next(row for row in rows if not row['finance'].get('paid'))
        self.assertEqual(400,pending['amount']);self.assertEqual(1500,pending['finance']['asset_value']);self.assertEqual(500,pending['finance']['down_payment'])
