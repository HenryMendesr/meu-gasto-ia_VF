import copy
import unittest
from src import investments, portfolio_ops as ops


class PositionHistoryTests(unittest.TestCase):
    def item(self):
        item={'id':'a'*32,'type':'Ações','symbol':'ALUP11','quantity':10,'average_price':30,'purchase_date':'2026-10-01','current_price':30}
        item['buys']=[ops.initial_buy(item)]
        return item

    def test_closed_position_keeps_trade_prices_cost_and_daily_sale_result(self):
        item=self.item();item['sales']=[{'id':'sale','date':'2026-10-10','quantity':10,'unit_price':31,'total':310,'net_total':308,'fees':2,'sequence':1}]
        result=investments.calculated(item)
        self.assertEqual('closed',result['position_status']);self.assertEqual(0,result['remaining_quantity'])
        ledger=result['operation_positions']
        self.assertEqual(0,ledger['initial-'+item['id']]['quantity_before']);self.assertEqual(10,ledger['initial-'+item['id']]['quantity_after'])
        self.assertEqual(10,ledger['sale']['quantity_before']);self.assertEqual(0,ledger['sale']['quantity_after']);self.assertEqual(8,ledger['sale']['profit_loss'])
        self.assertEqual(30,ledger['sale']['average_before']);self.assertEqual(300,ledger['sale']['basis_before']);self.assertEqual(0,ledger['sale']['basis_after'])

    def test_repurchase_reopens_position_without_changing_realized_history(self):
        item=self.item();item['sales']=[{'id':'sale','date':'2026-10-10','quantity':10,'total':310,'net_total':308,'fees':2,'sequence':1}]
        item['buys'].append({'id':'repurchase','date':'2026-10-20','quantity':2,'unit_price':35,'total':70,'sequence':2})
        result=investments.calculated(item)
        self.assertEqual('active',result['position_status']);self.assertEqual(2,result['remaining_quantity']);self.assertEqual(35,result['average_price']);self.assertEqual(8,result['realized_profit_loss'])
        self.assertEqual(0,result['operation_positions']['repurchase']['quantity_before']);self.assertEqual(2,result['operation_positions']['repurchase']['quantity_after'])

    def test_reversed_sale_has_no_ledger_or_result_and_reopens_position(self):
        item=self.item();item['sales']=[{'id':'sale','date':'2026-10-10','quantity':10,'total':310,'reversed':True,'profit_loss':999}]
        original=copy.deepcopy(item);result=investments.calculated(item)
        self.assertEqual('active',result['position_status']);self.assertEqual(10,result['remaining_quantity']);self.assertEqual(0,result['realized_profit_loss']);self.assertNotIn('sale',result['operation_positions']);self.assertEqual(original,item)

    def test_multiple_buys_use_cost_of_open_position_with_fees(self):
        item=self.item();item['buys'].append({'id':'buy2','date':'2026-10-10','quantity':10,'unit_price':40,'total':402,'fees':2,'sequence':1})
        item['sales']=[{'id':'sale','date':'2026-10-10','quantity':5,'total':200,'net_total':199,'fees':1,'sequence':2}]
        ledger=investments.calculated(item)['operation_positions']
        self.assertEqual(20,ledger['buy2']['quantity_after']);self.assertEqual(35.1,ledger['buy2']['average_after'])
        self.assertEqual(20,ledger['sale']['quantity_before']);self.assertEqual(15,ledger['sale']['quantity_after']);self.assertEqual(23.5,ledger['sale']['profit_loss'])
