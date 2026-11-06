import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from src import investments, storage


def stamp(day):return int(datetime.fromisoformat(day+'T18:00:00+00:00').timestamp())


class QuoteProviderTests(unittest.TestCase):
    def test_brapi_returns_unit_price_and_actual_session(self):
        data={'results':[{'currency':'BRL','regularMarketPrice':20,'regularMarketPreviousClose':19,'regularMarketTime':stamp('2026-10-29')}]}
        with patch.object(investments,'fetch_json',return_value=data) as fetch:
            result=investments.fetch_quote('BBAS3')
        self.assertEqual(20,result['price']);self.assertEqual('Brapi',result['source'])
        self.assertEqual('2026-10-29',result['quote_date']);self.assertAlmostEqual(5.2632,result['daily_change_percent'])
        self.assertEqual(1,fetch.call_count)

    def test_server_token_is_encoded_and_not_returned(self):
        with patch.dict(os.environ,{'BRAPI_TOKEN':'test-token&scope'}),patch.object(investments,'fetch_json',return_value={'results':[{'regularMarketPrice':20,'regularMarketTime':stamp('2026-10-29')}]}) as fetch:
            result=investments.fetch_quote('BPAC11')
        self.assertIn('token=test-token%26scope',fetch.call_args.args[0])
        self.assertNotIn('test-token',str(result))
        self.assertIsNone(result['daily_change_percent'])

    def test_yahoo_second_host_fallback_preserves_previous_session(self):
        result={'chart':{'result':[{'meta':{'currency':'BRL','regularMarketPrice':65,'regularMarketTime':stamp('2026-10-29'),'chartPreviousClose':50},'timestamp':[stamp('2026-10-28'),stamp('2026-10-29')],'indicators':{'quote':[{'close':[64,65]}]}}]}}
        with patch.object(investments,'fetch_json',side_effect=[ValueError('Brapi indisponível'),ValueError('Primeiro host indisponível'),result]) as fetch:
            info=investments.fetch_quote('BPAC11')
        self.assertEqual('Yahoo Finance',info['source']);self.assertEqual(64,info['previous_close'])
        self.assertEqual(1.5625,info['daily_change_percent'])
        self.assertIn('query2.finance.yahoo.com',fetch.call_args.args[0]);self.assertIn('BPAC11.SA',fetch.call_args.args[0])

    def test_unknown_previous_close_or_day_does_not_produce_fake_zero(self):
        for meta in ({'regularMarketPrice':65,'regularMarketTime':stamp('2026-10-29'),'chartPreviousClose':50},{'regularMarketPrice':65,'previousClose':64}):
            self.assertIsNone(investments.quote_values(meta,'Yahoo Finance')['daily_change_percent'])
        for price in (float('nan'),float('inf'),-1,0):
            with self.assertRaises(ValueError):investments.quote_values({'regularMarketPrice':price},'Brapi')

    def test_history_fallback_identifies_brapi_source(self):
        with patch.object(investments,'fetch_json',side_effect=[ValueError(),ValueError(),{'results':[{'currency':'BRL','historicalDataPrice':[{'date':stamp('2026-10-29'),'close':65}]}]}]):
            result=investments.fetch_market_history('BPAC11','1m')
        self.assertEqual('Brapi',result['source']);self.assertEqual(65,result['points'][0]['price'])


class AutomaticQuoteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'db.sqlite'),patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups')]
        for p in self.patches:p.start()
        investments.set_cash_balance({'amount':2000})
        self.first=investments.create_investment({'type':'Ações','symbol':'BBAS3','quantity':20,'average_price':17.96,'purchase_date':'2026-10-01'})
        self.lots=[investments.create_investment({'type':'Ações','symbol':'BPAC11','quantity':10,'average_price':cost,'purchase_date':'2026-10-01'}) for cost in (61.52,59.50)]

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def quote(self,symbol):
        return {'price':20 if symbol=='BBAS3' else 65,'currency':'BRL','previous_close':19 if symbol=='BBAS3' else 64,'daily_change_percent':5.2632 if symbol=='BBAS3' else 1.5625,'source':'Brapi','quote_date':investments.investment_today().isoformat(),'updated_at':investments.now_iso()}

    def test_duplicate_ticker_uses_one_fetch_but_lots_keep_individual_costs(self):
        with patch.object(investments,'fetch_quote',side_effect=self.quote) as fetch:
            result=investments.refresh_investments(quote_fetcher=fetch,automatic=True)
            self.assertEqual(2,fetch.call_count)
            investments.refresh_investments(quote_fetcher=fetch,automatic=True)
            self.assertEqual(2,fetch.call_count)
        items=result['investments'];self.assertEqual([400,650,650],[i['current_value'] for i in items])
        self.assertEqual([40.8,34.8,55],[i['profit_loss'] for i in items])
        self.assertEqual([1,1],[i['unit_daily_change'] for i in items[1:]])
        self.assertEqual(430.6,result['summary']['cash_balance'])

    def test_failure_keeps_last_price_and_reports_specific_ticker(self):
        investments.refresh_investments(quote_fetcher=self.quote)
        def fail(_):raise ValueError('Provedor temporariamente indisponível')
        result=investments.refresh_investments(quote_fetcher=fail)
        self.assertEqual([400,650,650],[i['current_value'] for i in result['investments']])
        self.assertTrue(all(i.get('quote_error') for i in result['investments']))
        self.assertEqual(3,len(result['errors']))
        with patch.object(investments,'fetch_quote',side_effect=AssertionError('Não deve consultar novamente agora')) as fetch:
            investments.refresh_investments(quote_fetcher=fetch,automatic=True)
        self.assertEqual(0,fetch.call_count)

    def test_missing_quote_is_flagged_without_presenting_cost_as_current_price(self):
        result=investments.portfolio()
        self.assertTrue(all(i['quote_pending'] for i in result['investments']))
        self.assertTrue(all(i['daily_price_change'] is None for i in result['investments']))

    def test_invalid_external_price_does_not_overwrite_valid_quote(self):
        investments.refresh_investments(quote_fetcher=self.quote)
        result=investments.refresh_investments(quote_fetcher=lambda symbol:{**self.quote(symbol),'price':float('nan')})
        self.assertEqual([400,650,650],[i['current_value'] for i in result['investments']])
        self.assertEqual(3,len(result['errors']))

    def test_stale_quotes_are_updated_automatically(self):
        investments.refresh_investments(quote_fetcher=self.quote)
        def age(store):
            for item in store['investments']:
                old=(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()
                item.update(quote_updated_at=old,quote_checked_at=old)
        investments.mutate_store(age)
        with patch.object(investments,'fetch_quote',side_effect=self.quote) as fetch:
            investments.refresh_investments(quote_fetcher=fetch,automatic=True)
        self.assertEqual(2,fetch.call_count)

class FractionalAndFallbackTests(unittest.TestCase):
    def test_fractional_ticker_uses_standard_quote_without_changing_trade(self):
        with patch.object(investments, 'brapi_data', return_value={'currency':'BRL','regularMarketPrice':30,'regularMarketTime':stamp('2026-10-29')}) as fetch:
            result=investments.fetch_quote(' petr4f ')
        fetch.assert_called_once_with('PETR4')
        self.assertEqual('Brapi',result['source'])
        normalized=investments.normalize_payload({'type':'Ações','symbol':'petr4f','quantity':1,'average_price':29,'purchase_date':'2026-10-01'})
        self.assertEqual('PETR4F',normalized['symbol'])
        self.assertEqual(1,normalized['quantity'])

    def test_fractional_history_and_yahoo_use_standard_symbol(self):
        with patch.object(investments,'fetch_json',return_value={'chart':{'result':[{}]}}) as fetch:
            investments.yahoo_chart('PETR4F')
        self.assertIn('/PETR4.SA?',fetch.call_args.args[0])
        self.assertEqual('BTC-BRL',investments.quote_symbol('BTC-BRL'))
        self.assertEqual('HGLG11',investments.quote_symbol('HGLG11'))

    def test_third_provider_takes_over_and_parses_trading_day(self):
        data={'Global Quote':{'01. symbol':'PETR4.SAO','05. price':'30','08. previous close':'29','07. latest trading day':'2026-10-29'}}
        with patch.dict(os.environ,{'ALPHAVANTAGE_API_KEY':'secret&key'}),patch.object(investments,'fetch_json',side_effect=[ValueError(),ValueError(),ValueError(),data]) as fetch:
            result=investments.fetch_quote('PETR4F')
        self.assertEqual(4,fetch.call_count)
        self.assertEqual('Alpha Vantage',result['source'])
        self.assertEqual('BRL',result['currency'])
        self.assertEqual('2026-10-29',result['quote_date'])
        self.assertEqual(30,result['price'])
        self.assertAlmostEqual(100/29,result['daily_change_percent'],places=4)
        self.assertIn('apikey=secret%26key',fetch.call_args.args[0])
        self.assertNotIn('secret',str(result))

    def test_bad_or_rate_limited_third_provider_is_rejected(self):
        for data in ({'Note':'Limit reached'},{'Global Quote':{}},{'Global Quote':{'01. symbol':'AAPL','05. price':'30','07. latest trading day':'2026-10-29'}}):
            with self.subTest(data=data),patch.dict(os.environ,{'ALPHAVANTAGE_API_KEY':'secret'}),patch.object(investments,'fetch_json',return_value=data):
                with self.assertRaises(ValueError) as error:
                    investments.alpha_vantage_quote('PETR4')
                self.assertNotIn('secret',str(error.exception))

    def test_missing_key_skips_network_and_reports_configuration(self):
        with patch.dict(os.environ,{'ALPHAVANTAGE_API_KEY':''}),patch.object(investments,'fetch_json') as fetch:
            with self.assertRaisesRegex(ValueError,'ALPHAVANTAGE_API_KEY'):
                investments.alpha_vantage_quote('PETR4')
            fetch.assert_not_called()
