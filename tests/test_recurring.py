import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api import index
from src import investments, storage, recurring, trust, planning, portability


class RecurringTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.today=date(2026,10,14)
        self.patches=[patch.object(storage,'DATABASE',Path(self.temp.name)/'db.sqlite'),patch.object(storage,'BACKUPS',Path(self.temp.name)/'backups'),patch.object(investments,'investment_today',side_effect=lambda:self.today)]
        for mock in self.patches:mock.start()
        investments.set_cash_balance({'amount':1000})
        self.plan={'enabled':True,'source':'Empresa','start_month':'2026-10','payments':[{'day':15,'amount':1500},{'day':30,'amount':2500}]}

    def tearDown(self):
        for mock in reversed(self.patches):mock.stop()
        self.temp.cleanup()

    def prefs(self):return investments.load_store().get('preferences',{})

    def test_split_salary_only_posts_when_each_date_arrives_and_is_idempotent(self):
        self.assertEqual(0,recurring.save_plan(self.plan)['posted']);self.assertEqual(0,trust.insights('2026-10')['income']['used'])
        self.today=date(2026,10,15);self.assertEqual(1,recurring.process_due()['posted']);self.assertEqual(1500,trust.insights('2026-10')['income']['used']);self.assertEqual(4000,trust.insights('2026-10')['income']['expected'])
        self.today=date(2026,10,30);self.assertEqual(1,recurring.process_due()['posted']);self.assertEqual(0,recurring.process_due()['posted'])
        self.assertEqual(4000,planning.monthly_report('2026-10')['income']);self.assertEqual(4000,planning.monthly_report('2026-10')['expected_income']);self.assertEqual(2,len(self.prefs()['salary_receipts']))
        self.assertEqual(1000,investments.portfolio()['summary']['cash_balance'])

    def test_salary_not_double_counted_with_declared_or_imported_salary(self):
        self.today=date(2026,10,30);storage.set_income({'month':'2026-10','cash':4000,'voucher':600})
        storage.add_income_entry({'date':'2026-10-15','amount':4000,'where':'Empresa','category':'Salário'})
        recurring.save_plan(self.plan)
        recurring.receipt_action('2026-10:1',{'action':'confirm','amount':1500});recurring.receipt_action('2026-10:2',{'action':'confirm','amount':2500})
        self.assertEqual(4000,trust.insights('2026-10')['income']['used']);self.assertEqual('scheduled',planning.monthly_report('2026-10')['income_source'])
        storage.set_income({'month':'2026-10','cash':3500,'voucher':600,'income_mode':'declared'})
        self.assertEqual(3500,planning.monthly_report('2026-10')['income'])

    def test_february_uses_last_day_for_day_thirty_and_leap_year(self):
        self.assertEqual('2027-02-28',recurring.due_date('2027-02',30));self.assertEqual('2028-02-29',recurring.due_date('2028-02',30))
        self.today=date(2027,2,28);recurring.save_plan({**self.plan,'start_month':'2027-02'})
        receipts=self.prefs()['salary_receipts'];self.assertEqual(['2027-02-15','2027-02-28'],[entry['date'] for entry in receipts]);self.assertEqual(4000,sum(entry['amount'] for entry in receipts))

    def test_missing_visits_catch_up_later_months_without_duplicates(self):
        recurring.save_plan(self.plan);self.today=date(2026,12,31);recurring.process_due();recurring.process_due()
        self.assertEqual(6,len(self.prefs()['salary_receipts']));self.assertEqual(4000,planning.monthly_report('2026-11')['expected_income']);self.assertEqual(4000,planning.monthly_report('2026-11')['income'])

    def test_edits_preserve_due_receipts_and_pause_stops_future_posts(self):
        self.today=date(2026,10,15);recurring.save_plan(self.plan)
        recurring.save_plan({**self.plan,'payments':[{'day':15,'amount':1600},{'day':30,'amount':2600}]})
        self.assertEqual(1500,self.prefs()['salary_receipts'][0]['amount'])
        recurring.save_plan({'enabled':False});self.today=date(2026,11,30);self.assertEqual(0,recurring.process_due()['posted']);self.assertEqual(1,len(self.prefs()['salary_receipts']))

    def test_confirm_skip_and_restore_adjust_month_once(self):
        self.today=date(2026,10,30);recurring.save_plan(self.plan)
        recurring.receipt_action('2026-10:1',{'action':'confirm','amount':1500})
        recurring.receipt_action('2026-10:2',{'action':'confirm','amount':2300})
        self.assertEqual(3800,planning.monthly_report('2026-10')['income'])
        recurring.receipt_action('2026-10:1',{'action':'skip'});recurring.process_due();self.assertEqual(2300,planning.monthly_report('2026-10')['income'])
        recurring.receipt_action('2026-10:1',{'action':'restore'});self.assertEqual(3800,planning.monthly_report('2026-10')['income'])
        self.assertEqual(2,len(self.prefs()['salary_receipts']))

    def test_concurrent_reads_do_not_post_twice(self):
        recurring.save_plan(self.plan);self.today=date(2026,10,30)
        with ThreadPoolExecutor(max_workers=4) as executor:list(executor.map(lambda _:recurring.process_due(),range(8)))
        self.assertEqual(2,len(self.prefs()['salary_receipts']));self.assertEqual(4000,planning.monthly_report('2026-10')['expected_income']);self.assertEqual(4000,planning.monthly_report('2026-10')['income'])

    def test_delayed_receipt_stays_out_until_received_and_carries_forward(self):
        self.today=date(2026,10,30);recurring.save_plan(self.plan)
        recurring.receipt_action('2026-10:2',{'action':'delay'})
        recurring.process_due()
        self.assertEqual(1500,trust.insights('2026-10')['income']['used'])
        self.assertEqual(4000,trust.insights('2026-10')['income']['expected'])
        self.today=date(2026,11,2)
        self.assertEqual(1500,trust.insights('2026-11')['opening_balance'])
        recurring.receipt_action('2026-10:2',{'action':'confirm','amount':2500,'received_date':'2026-11-02'})
        self.assertEqual(4000,trust.insights('2026-11')['accumulated_balance'])

    def test_existing_unconfirmed_receipts_migrate_once_except_explicit_delays(self):
        self.today=date(2026,10,30);recurring.save_plan(self.plan)
        def legacy(store):
            for entry in store['preferences']['salary_receipts']:
                entry['status']='scheduled'
                entry.pop('received_date',None)
            store['preferences']['salary_receipts'][1]['manual_pending']=True
        investments.mutate_store(legacy)
        recurring.process_due();recurring.process_due()
        self.assertEqual(1500,trust.insights('2026-10')['income']['used'])
        self.assertEqual(2,len(self.prefs()['salary_receipts']))

    def test_invalid_plan_does_not_change_data(self):
        before=investments.load_store()
        for change in [{'payments':[{'day':15,'amount':0}]},{'payments':[{'day':32,'amount':100}]},{'payments':[{'day':15,'amount':100},{'day':15,'amount':200}]},{'start_month':'bad'}]:
            with self.assertRaises(ValueError):recurring.save_plan({**self.plan,**change})
            self.assertEqual(before,investments.load_store())

    def test_cards_edit_delete_and_next_due_dates_do_not_create_debt(self):
        card=recurring.save_card({'name':'Nubank','due_day':30});item_id=card['id']
        self.assertEqual('2027-02-28',recurring.card_dates([card],'2027-02-20')[0]['next_due'])
        self.assertEqual('2027-04-30',recurring.card_dates([card],'2027-03-31')[0]['next_due'])
        recurring.save_card({'id':item_id,'name':'Cartão principal','due_day':10});self.assertEqual(1,len(self.prefs()['credit_cards']))
        self.assertEqual('Cartão principal',self.prefs()['credit_cards'][0]['name']);self.assertEqual([],storage.read_expenses())
        recurring.delete_card(item_id);self.assertEqual([],self.prefs()['credit_cards'])

    def test_export_restore_preserves_plans_cards_and_posted_keys(self):
        self.today=date(2026,10,30);recurring.save_plan(self.plan);recurring.save_card({'name':'Itaú','due_day':10})
        backup=storage.export_financial_data();portability.validate(backup);storage.restore_financial_data(backup);recurring.process_due()
        self.assertEqual(2,len(self.prefs()['salary_receipts']));self.assertEqual(1,len(self.prefs()['credit_cards']))
        bad=copy.deepcopy(backup);bad['data']['portfolio']['preferences']['salary_plan']['payments'][0]['day']=99
        with self.assertRaises(ValueError):portability.validate(bad)

    def test_routes_require_auth_and_post_due_on_bootstrap(self):
        client=TestClient(index.fastapi_app)
        self.assertEqual(401,client.get('/api/recurring?month=2026-10').status_code)
        with patch.object(index.auth,'session_user',return_value=1):
            self.assertEqual(200,client.post('/api/recurring/salary',json=self.plan).status_code)
            self.today=date(2026,10,15);data=client.get('/api/bootstrap').json()
            self.assertEqual(1,len(data['portfolio']['preferences']['salary_receipts']))
            self.assertEqual(200,client.post('/api/recurring/card',json={'name':'Visa','due_day':20}).status_code)
            self.assertEqual(400,client.post('/api/recurring/card',json={'name':'Visa','due_day':99}).status_code)
