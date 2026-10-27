import unittest
from src.daily_summary import summaries
from src import investments, portfolio_ops


class DailySummaryTests(unittest.TestCase):
    def item(self):
        return {'id':'a'*32,'type':'Ações','symbol':'PETR4','quantity':10,'average_price':30,
                'purchase_date':'2026-10-01','current_price':33,'quote_source':'Yahoo Finance',
                'quote_date':'2026-10-27','previous_close':30}

    def result(self,item,expenses=None):
        return summaries({'investments':[item]},expenses or [],'2026-10-27')

    def test_latest_and_today_are_explicit_and_do_not_treat_capital_as_profit(self):
        data=self.result(self.item())
        self.assertEqual('2026-10-01',data['latest']['date']);self.assertEqual(300,data['latest']['invested'])
        self.assertIsNone(data['latest']['performance']);self.assertEqual(30,data['today']['performance'])
        self.assertEqual(0,data['today']['realized_profit'])

    def test_new_buy_sale_fees_and_receipt_reconcile_with_price_movement(self):
        item=self.item();item['buys']=[portfolio_ops.initial_buy(item),{'id':'buy','date':'2026-10-27','quantity':5,'unit_price':32,'total':162,'fees':2,'sequence':1}]
        item['sales']=[{'id':'sale','date':'2026-10-27','quantity':4,'total':136,'net_total':135,'fees':1,'sequence':2}]
        item['incomes']=[{'id':'income','date':'2026-10-27','amount':5,'kind':'Dividendos'}]
        data=self.result(item)['today']
        self.assertEqual(162,data['invested']);self.assertEqual(135,data['sales']);self.assertEqual(3,data['fees'])
        # End position 11*33 - opening 10*30 - buy 162 + sell 135 + income 5.
        self.assertEqual(41,data['performance']);self.assertEqual(-22,data['cash_flow'])
        self.assertEqual(11.8,data['realized_profit']);self.assertEqual(16.8,data['realized_with_income'])

    def test_manual_or_wrong_day_quote_cannot_masquerade_as_daily_result(self):
        for change in [{'quote_source':'Manual'},{'quote_date':'2026-10-26'},{'previous_close':None}]:
            item={**self.item(),**change};data=self.result(item)['today']
            self.assertIsNone(data['performance']);self.assertEqual(1,data['missing_quotes'])

    def test_reversed_operations_are_excluded_and_realized_is_recomputed(self):
        item=self.item();item['sales']=[{'id':'sale','date':'2026-10-27','quantity':4,'total':140,'fees':0,'reversed':True,'profit_loss':999}]
        data=self.result(item)
        self.assertEqual('2026-10-01',data['latest']['date']);self.assertEqual([],data['today']['operations'])
        self.assertEqual(0,data['today']['realized_profit']);self.assertEqual(30,data['today']['performance'])

    def test_debt_expenses_use_payment_date_and_never_affect_investment_profit(self):
        rows=[{'where':'Mercado','date':'2026-10-27','amount':20,'payment':'Pix'},
              {'where':'Banco','date':'2026-10-01','amount':100,'payment':'Pix','finance':{'financing_kind':'loan','paid':True,'paid_date':'2026-10-27'}},
              {'where':'Pendente','date':'2026-10-27','amount':999,'payment':'Pix','finance':{'financing_kind':'loan','paid':False}}]
        data=self.result(self.item(),rows)['today'];self.assertEqual(120,data['personal_expenses']);self.assertEqual(30,data['performance'])

    def test_empty_portfolio_has_no_fabricated_performance(self):
        data=summaries({'investments':[]},[],'2026-10-27')['latest']
        self.assertEqual('2026-10-27',data['date']);self.assertIsNone(data['performance']);self.assertEqual([],data['operations'])

    def test_market_timestamp_uses_sao_paulo_date(self):
        self.assertEqual('2026-10-26',investments.market_date('2026-10-27T01:00:00Z'))
        self.assertIsNone(investments.market_date(None))
        self.assertIsNone(investments.market_date('invalid'))

    def test_quote_uses_last_prior_trading_close_instead_of_range_start(self):
        from datetime import datetime
        from unittest.mock import patch
        stamp=lambda value:int(datetime.fromisoformat(value+'T18:00:00+00:00').timestamp())
        result={'meta':{'regularMarketPrice':104,'regularMarketTime':stamp('2026-10-27'),'chartPreviousClose':90},
                'timestamp':[stamp('2026-10-26'),stamp('2026-10-27')],
                'indicators':{'quote':[{'close':[101,104]}]}}
        with patch.object(investments,'fetch_json',return_value={'chart':{'result':[result]}}):
            quote=investments.fetch_quote('BTC-USD')
        self.assertEqual(101,quote['previous_close']);self.assertEqual('2026-10-27',quote['quote_date'])
        self.assertAlmostEqual(2.9703,quote['daily_change_percent'])
