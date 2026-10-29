import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from src import investments, storage, bank_accounts, cards, recurring, planning, portability, trust
from src.finance_rules import projected_expenses


class FinanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'db.sqlite'),patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups'),patch.object(investments,'investment_today',return_value=date(2026,10,29))]
        for p in self.patches:p.start()
        investments.set_cash_balance({'amount':2000})

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def fixed(self):
        return investments.create_investment({'type':'Renda fixa','name':'CDB','institution':'Banco','amount_invested':1000,'application_date':'2025-10-29','profitability_type':'Prefixado','contracted_rate':12,'valuation_mode':'automatic'})

    def test_partial_and_total_redemption_preserve_profit_and_cash(self):
        item=self.fixed();payload={'date':'2026-10-29','gross':560,'tax':12,'request_id':'redeem1'}
        first=investments.redeem_fixed(item['id'],payload)
        self.assertEqual(first,investments.redeem_fixed(item['id'],{**payload,'gross':'560','tax':'12'}))
        state=investments.portfolio();position=state['investments'][0]
        self.assertEqual(500,position['amount_applied']);self.assertEqual(560,position['current_value'])
        self.assertEqual(48,position['realized_profit_loss']);self.assertEqual(1548,state['summary']['cash_balance'])
        self.assertEqual(108,state['summary']['profit_loss'])
        investments.redeem_fixed(item['id'],{**payload,'request_id':'redeem2','tax':12})
        final=investments.portfolio()
        self.assertEqual(0,final['summary']['current_value']);self.assertEqual(0,final['summary']['amount_applied'])
        self.assertEqual(96,final['summary']['realized_profit_loss']);self.assertEqual(2096,final['summary']['cash_balance'])
        self.assertEqual('closed',final['investments'][0]['position_status'])
        report=planning.monthly_report('2026-10');self.assertEqual(1096,report['sales']);self.assertEqual(96,report['realized_result'])
        self.assertEqual(2,len(portability.validate(storage.export_financial_data())['portfolio']['investments'][0]['redemptions']))
        with self.assertRaises(ValueError):investments.delete_investment(item['id'])

    def test_invalid_redemption_does_not_change_cash(self):
        item=self.fixed();before=investments.load_store()
        for payload in ({'gross':1200,'tax':0,'date':'2026-10-29'}, {'gross':500,'tax':500,'date':'2026-10-29'}, {'gross':100,'tax':0,'date':'2027-01-01'}):
            with self.assertRaises(ValueError):investments.redeem_fixed(item['id'],{**payload,'request_id':'bad'})
            self.assertEqual(before,investments.load_store())

    def test_external_foreign_quotes_are_not_saved_as_reais(self):
        item=investments.create_investment({'type':'Criptomoedas','symbol':'BTC-USD','quantity':1,'average_price':100,'purchase_date':'2026-10-01'})
        result=investments.refresh_investments(lambda symbol:{'currency':'USD','price':99999})
        self.assertEqual(100,result['investments'][0]['current_value']);self.assertTrue(result['errors'])
        with self.assertRaises(ValueError):investments.investment_history(item['id'],market_fetcher=lambda *args:{'currency':'USD','points':[]})

    def test_account_transfer_and_reconciliation_do_not_change_income_or_portfolio_cash(self):
        for name,amount,req in [('Banco',100,'a'),('Carteira',20,'b')]:bank_accounts.action('create',{'date':'2026-10-01','name':name,'amount':amount,'request_id':req})
        first,second=bank_accounts.status()['accounts']
        payload={'date':'2026-10-29','account_id':first['id'],'target_id':second['id'],'amount':30,'reason':'Transferência própria','request_id':'t'}
        bank_accounts.action('transfer',payload);bank_accounts.action('transfer',payload)
        state=bank_accounts.status();self.assertEqual([70,50],[a['balance'] for a in state['accounts']]);self.assertEqual(120,state['total'])
        self.assertEqual(2,len(state['entries']))
        bank_accounts.action('reconcile',{'date':'2026-10-29','account_id':first['id'],'amount':65,'expected_balance':70,'reason':'Tarifa faltante','request_id':'r'})
        self.assertEqual(115,bank_accounts.status()['total'])
        self.assertEqual(2000,investments.portfolio()['summary']['cash_balance']);self.assertEqual(0,planning.monthly_report('2026-10')['income'])
        data=portability.validate(storage.export_financial_data());self.assertEqual(2,len(data['portfolio']['preferences']['bank_accounts']))
        bad=storage.export_financial_data();bad['data']['portfolio']['preferences']['account_entries'].pop(0)
        with self.assertRaises(ValueError):portability.validate(bad)

    def test_stale_reconciliation_rejected_and_failed_transfer_atomic(self):
        bank_accounts.action('create',{'date':'2026-10-01','name':'Banco','amount':100,'request_id':'a'})
        account=bank_accounts.status()['accounts'][0];before=investments.load_store()
        for kind,payload in [('transfer',{'target_id':'missing','amount':20}),('reconcile',{'amount':90,'expected_balance':99})]:
            with self.assertRaises(ValueError):bank_accounts.action(kind,{'date':'2026-10-29','account_id':account['id'],'reason':'Conferência de saldo','request_id':'bad',**payload})
            self.assertEqual(before,investments.load_store())

    def card(self):
        card=recurring.save_card({'name':'Cartão','closing_day':20,'due_day':5})
        purchase=cards.purchase({'card_id':card['id'],'date':'2026-10-19','where':'Loja','amount':100,'category':'Mercado','installments':1})
        return purchase,cards.status('2026-11')['invoices'][0]['key']

    def test_refund_paid_invoice_preserves_cash_and_shows_credit(self):
        purchase,key=self.card();cards.pay({'invoice_key':key,'date':'2026-10-29','amount':100,'request_id':'p'})
        payload={'invoice_key':key,'date':'2026-10-29','amount':30,'reason':'Devolução de produto','request_id':'r'}
        cards.refund(payload);cards.refund(payload)
        bill=cards.status('2026-11')['invoices'][0]
        self.assertEqual(70,bill['total']);self.assertEqual(0,bill['remaining']);self.assertEqual(30,bill['credit'])
        self.assertEqual(100,planning.monthly_report('2026-10')['cash_expenses'])
        self.assertEqual(0,trust.insights('2026-11')['projected_expenses'])
        self.assertEqual(100,trust.insights('2026-10')['projected_expenses'])
        review=cards.review({'invoice_key':key,'amount':70});self.assertEqual(0,review['difference'])
        cards.refund({**payload,'request_id':'r2','amount':10})
        self.assertEqual(10,cards.status('2026-11')['invoices'][0]['review_difference'])
        portability.validate(storage.export_financial_data())
        with self.assertRaises(ValueError):cards.delete_purchase(purchase['id'])

    def test_debt_paid_early_follows_actual_month_in_projection(self):
        row={'date':'2026-11-01','amount':100,'payment':'Pix','finance':{'financing_kind':'loan','paid':True,'paid_date':'2026-10-29'}}
        self.assertEqual(100,projected_expenses([row],'2026-10'));self.assertEqual(0,projected_expenses([row],'2026-11'))
        row['finance']['paid']=False
        self.assertEqual(0,projected_expenses([row],'2026-10'));self.assertEqual(100,projected_expenses([row],'2026-11'))

    def test_redemption_reversal_reopens_position_and_preserves_backup(self):
        item=self.fixed()
        first=investments.redeem_fixed(item['id'],{'date':'2026-10-29','gross':560,'tax':12,'request_id':'r1'})
        second=investments.redeem_fixed(item['id'],{'date':'2026-10-29','gross':560,'tax':12,'request_id':'r2'})
        with self.assertRaises(ValueError):investments.reverse_redemption(item['id'],{'id':first['id'],'reason':'Ordem incorreta'})
        for entry in (second,first):investments.reverse_redemption(item['id'],{'id':entry['id'],'reason':'Corrigir resgate informado'})
        state=investments.portfolio()
        self.assertEqual(1120,state['summary']['current_value']);self.assertEqual(1000,state['summary']['cash_balance'])
        self.assertEqual(0,state['summary']['realized_profit_loss'])
        portability.validate(storage.export_financial_data())

    def test_refund_can_be_undone_without_losing_history(self):
        _,key=self.card()
        entry=cards.refund({'invoice_key':key,'date':'2026-10-29','amount':30,'reason':'Produto devolvido','request_id':'r'})
        cards.reverse_refund({'id':entry['id'],'reason':'Crédito registrado por engano'})
        self.assertEqual(100,cards.status('2026-11')['invoices'][0]['remaining'])
        self.assertEqual(100,trust.insights('2026-11')['projected_expenses'])
        portability.validate(storage.export_financial_data())

    def test_legacy_foreign_reference_is_not_used_as_brl(self):
        item=investments.normalize_payload({'type':'Criptomoedas','symbol':'BTC-USD','quantity':1,'average_price':100,'purchase_date':'2026-10-01'})
        item.update(current_price=99999,quote_source='Yahoo Finance')
        result=investments.calculated(item)
        self.assertEqual(100,result['current_value']);self.assertTrue(result['currency_warning'])
