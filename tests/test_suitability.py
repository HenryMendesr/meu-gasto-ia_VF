import unittest
from unittest.mock import patch
from src import suitability, trust


class SuitabilityTests(unittest.TestCase):
    def payload(self, value=3):
        return {'version': 1, 'answers': {q['id']: min(value, len(q['options'])-1) for q in suitability.QUESTIONS}}

    def test_profiles_and_knowledge(self):
        self.assertEqual('Conservador', suitability.evaluate(self.payload(0))['profile'])
        self.assertEqual('Arrojado', suitability.evaluate(self.payload())['profile'])
        data = self.payload()
        for q in suitability.QUESTIONS:
            if q['dimension'] == 'tolerance':
                data['answers'][q['id']] = 2
        self.assertEqual('Moderado', suitability.evaluate(data)['profile'])
        for q in suitability.QUESTIONS:
            if q['dimension'] in ('knowledge', 'quiz'):
                data['answers'][q['id']] = 0
        self.assertEqual('Conservador', suitability.evaluate(data)['profile'])

    def test_financial_limits_override_appetite(self):
        for key, value in [('horizon', 0), ('liquidity', 1), ('reserve', 0), ('debt', 0), ('loss_capacity', 1), ('loss_tolerance', 0)]:
            with self.subTest(key=key):
                data = self.payload()
                data['answers'][key] = value
                self.assertEqual('Conservador', suitability.evaluate(data)['profile'])

    def test_reject_missing_extra_invalid_and_stale(self):
        for value in [True, -1, 4, '3', None]:
            data = self.payload()
            data['answers']['objective'] = value
            with self.assertRaises(ValueError):
                suitability.evaluate(data)
        data = self.payload()
        del data['answers']['reserve']
        with self.assertRaises(ValueError):
            suitability.evaluate(data)
        with self.assertRaises(ValueError):
            suitability.evaluate({**self.payload(), 'version': 0})

    def test_saved_result_recomputed_and_preferences_preserved(self):
        store = {'preferences': {'analytics_consent': False, 'salary_plan': {'enabled': True}}}
        with patch.object(trust.investments, 'mutate_store', side_effect=lambda callback, uid: callback(store)):
            data = {**self.payload(0), 'profile': 'Arrojado', 'scores': {'capacity': 100}}
            result = trust.preferences({'investor_profile': data}, 'user-a')
        self.assertEqual('Conservador', result['investor_profile']['profile'])
        self.assertTrue(result['salary_plan']['enabled'])
        self.assertIn('completed_at', result['investor_profile'])
        with self.assertRaises(ValueError):
            trust.preferences({'unexpected': True})
