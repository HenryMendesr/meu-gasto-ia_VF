import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api import index
from src import investments, storage, portability


class AssetTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'db.sqlite'),patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups')]
        for p in self.patches:p.start()
        investments.set_cash_balance({'amount':10000})
        self.payload={'type':'Ações','symbol':'VALE3','quantity':1,'average_price':50,'purchase_date':'2026-10-01'}

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def fetch(self,symbol):
        return {'price':60,'daily_change_percent':1,'source':'Teste','updated_at':investments.now_iso(),'currency':'BRL'}

    def test_all_variable_asset_types_can_be_automatically_queried(self):
        pairs=[('Ações','VALE3'),('Fundos imobiliários','HGLG11'),('ETFs','IVVB11'),('Criptomoedas','BTC-BRL'),('Outros','TEST11')]
        for kind,symbol in pairs:investments.create_investment({**self.payload,'type':kind,'symbol':symbol})
        with patch.object(investments,'fetch_quote',side_effect=self.fetch) as fetch:
            result=investments.refresh_investments(quote_fetcher=fetch,automatic=True)
        self.assertEqual({s for _,s in pairs},{c.args[0] for c in fetch.call_args_list})
        self.assertTrue(all(i['current_value']==60 for i in result['investments']))

    def test_disabled_asset_is_not_automatically_fetched_but_manual_refresh_works(self):
        item=investments.create_investment({**self.payload,'auto_tracking':False})
        with patch.object(investments,'fetch_quote',side_effect=self.fetch) as fetch:
            investments.refresh_investments(quote_fetcher=fetch,automatic=True);self.assertEqual(0,fetch.call_count)
            result=investments.refresh_investments(quote_fetcher=fetch);self.assertEqual(1,fetch.call_count)
        self.assertFalse(result['investments'][0]['auto_tracking']);self.assertEqual(60,result['investments'][0]['current_value'])

    def test_preference_is_independent_per_position_even_for_same_symbol(self):
        first=investments.create_investment(self.payload)
        investments.create_investment({**self.payload,'auto_tracking':False})
        result=investments.refresh_investments(quote_fetcher=self.fetch,automatic=True)
        self.assertEqual([60,50],[i['current_value'] for i in result['investments']])
        before=investments.portfolio()['summary']['cash_balance']
        investments.set_auto_tracking(first['id'],{'enabled':False})
        self.assertEqual(before,investments.portfolio()['summary']['cash_balance'])

    def test_legacy_assets_default_to_enabled(self):
        item=investments.create_investment(self.payload)
        investments.mutate_store(lambda store:store['investments'][0].pop('auto_tracking'))
        with patch.object(investments,'fetch_quote',side_effect=self.fetch) as fetch:
            investments.refresh_investments(quote_fetcher=fetch,automatic=True)
        self.assertEqual(1,fetch.call_count)

    def test_preference_survives_export_and_rejects_nonboolean(self):
        item=investments.create_investment({**self.payload,'auto_tracking':False})
        data=storage.export_financial_data();validated=portability.validate(data)
        self.assertFalse(validated['portfolio']['investments'][0]['auto_tracking'])
        invalid=copy.deepcopy(data);invalid['data']['portfolio']['investments'][0]['auto_tracking']='false'
        with self.assertRaises(ValueError):portability.validate(invalid)
        with self.assertRaises(ValueError):investments.set_auto_tracking(item['id'],{'enabled':'false'})
        with self.assertRaises(ValueError):investments.create_investment({**self.payload,'auto_tracking':'true'})

    def test_fixed_income_can_disable_index_fetch_without_changing_valuation(self):
        item=investments.create_investment({'type':'Renda fixa','name':'CDB','institution':'Banco','amount_invested':1000,'application_date':'2026-10-01','profitability_type':'CDI','contracted_rate':100,'cdi_rate':10,'auto_tracking':False})
        before=investments.portfolio()['investments'][0]['current_value']
        with patch.object(investments,'fetch_cdi_rate') as fetch:
            investments.refresh_investments(cdi_fetcher=fetch,automatic=True)
        self.assertEqual(0,fetch.call_count);self.assertEqual(before,investments.portfolio()['investments'][0]['current_value'])
        investments.set_auto_tracking(item['id'],{'enabled':True})
        with patch.object(investments,'fetch_cdi_rate',return_value={'rate':11,'source':'Teste','updated_at':investments.now_iso()}) as fetch:
            investments.refresh_investments(cdi_fetcher=fetch,automatic=True)
        self.assertEqual(1,fetch.call_count)

    def test_tracking_endpoint_works_for_locked_fixed_income_with_redemption(self):
        item=investments.create_investment({'type':'Renda fixa','name':'CDB','institution':'Banco','amount_invested':1000,'application_date':'2026-10-01','profitability_type':'Prefixado','contracted_rate':10})
        investments.redeem_fixed(item['id'],{'date':investments.investment_today().isoformat(),'gross':100,'tax':0,'request_id':'r'})
        with patch.object(index,'protected',return_value=None),TestClient(index.app) as client:
            response=client.post('/api/investments/'+item['id']+'/tracking',json={'enabled':False})
        self.assertEqual(200,response.status_code);self.assertFalse(response.json()['investment']['auto_tracking'])

    def test_pausing_during_fetch_prevents_automatic_result_from_overwriting_asset(self):
        item=investments.create_investment(self.payload)
        def fetch(symbol):
            investments.set_auto_tracking(item['id'],{'enabled':False})
            return self.fetch(symbol)
        result=investments.refresh_investments(quote_fetcher=fetch,automatic=True)
        self.assertFalse(result['investments'][0]['auto_tracking']);self.assertEqual(50,result['investments'][0]['current_value'])

    def test_yahoo_symbol_resolution_is_not_limited_to_brazilian_stocks(self):
        with patch.object(investments,'fetch_json',return_value={'chart':{'result':[{}]}}) as fetch:
            investments.yahoo_chart('BTC-BRL');self.assertIn('/BTC-BRL?',fetch.call_args.args[0])
            investments.yahoo_chart('HGLG11');self.assertIn('/HGLG11.SA?',fetch.call_args.args[0])
            investments.yahoo_chart('AAPL');self.assertIn('/AAPL?',fetch.call_args.args[0])
