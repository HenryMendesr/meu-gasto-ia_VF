"""Questionnaire persistence, API validation and independent financial checks."""
import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api import index
from src import investments, investor_education, storage, trust, portability


class InvestorEducationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(storage, 'DATABASE', Path(self.temp.name) / 'test.db')
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def answers(self, **changes):
        return {**dict.fromkeys(investor_education.QUESTION_KEYS, 2), **changes}

    def test_profile_respects_liquidity_horizon_loss_and_knowledge(self):
        def profile(**changes):
            return investor_education.validate_education({'experience':'beginner','answers':self.answers(**changes)})['profile']
        self.assertEqual('aggressive', profile())
        for field in ('horizon','liquidity','loss'):
            self.assertEqual('conservative', profile(**{field:0}))
        self.assertEqual('moderate', profile(knowledge=0))
        self.assertEqual('moderate', profile(**dict.fromkeys(investor_education.QUESTION_KEYS,1)))

    def test_preferences_persist_and_do_not_change_financial_state(self):
        investments.set_cash_balance({'amount':1234})
        trust.preferences({'analytics_consent':True})
        before = copy.deepcopy(investments.portfolio()['summary'])
        saved = trust.preferences({'investment_education':{'experience':'beginner','answers':self.answers()}})
        self.assertEqual('aggressive', saved['investment_education']['profile'])
        self.assertTrue(saved['analytics_consent'])
        self.assertEqual(saved, investments.portfolio()['preferences'])
        self.assertEqual(before, investments.portfolio()['summary'])
        self.assertEqual(saved['investment_education'], portability.validate(storage.export_financial_data())['portfolio']['preferences']['investment_education'])

    def test_invalid_questionnaires_are_atomic(self):
        original = investments.load_store()
        for value in (None, [], {}, {'experience':'bad'}, {'experience':'beginner','answers':{'goal':0}},
                      {'experience':'beginner','answers':self.answers(loss=True)},
                      {'experience':'beginner','answers':self.answers(loss=3)},
                      {'experience':'beginner','answers':self.answers(loss='1')},
                      {'experience':'beginner','unknown':'value'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                trust.preferences({'analytics_consent':True, 'investment_education':value})
            self.assertEqual(original, investments.load_store())

    def test_server_derives_profile_and_saves_skip_or_experienced(self):
        result = trust.preferences({'investment_education':{'experience':'beginner','answers':self.answers(liquidity=0),'profile':'aggressive'}})
        self.assertEqual('conservative', result['investment_education']['profile'])
        for choice in ('skipped','experienced'):
            saved = trust.preferences({'investment_education':{'experience':choice}})
            self.assertEqual(choice, saved['investment_education']['experience'])
            self.assertIsNone(saved['investment_education']['profile'])

    def test_authenticated_api_passes_owner_and_rejects_malformed_data(self):
        with patch.object(index.auth,'session_user',return_value=17), patch.object(index.trust,'preferences',wraps=trust.preferences) as save:
            client = TestClient(index.fastapi_app)
            response = client.post('/api/preferences',json={'investment_education':{'experience':'skipped'}})
            self.assertEqual(200,response.status_code)
            self.assertEqual(17,save.call_args.args[1])
            self.assertEqual(400,client.post('/api/preferences',json={'investment_education':{'experience':'bad'}}).status_code)
        with patch.object(index.auth,'session_user',return_value=None):
            self.assertEqual(401,client.post('/api/preferences',json={'investment_education':{'experience':'skipped'}}).status_code)

    def test_simulator_financial_regressions(self):
        subprocess.run(['node',str(Path(__file__).with_name('investment_simulator.test.js'))],check=True,capture_output=True,text=True)
