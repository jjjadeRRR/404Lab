"""The register of what a mod author must know before building. A gap is allowed; a gap nobody wrote down is not."""
import json
import unittest

from lab404.knowledge import Knowledge, ROOT, gaps

NEEDED = json.loads((ROOT/'required.json').read_text(encoding='utf-8'))['questions']
STATES = ('known', 'partly', 'open')


class Register(unittest.TestCase):
    def setUp(self):
        self.facts = {f['id']: f for f in Knowledge().facts}

    def test_every_question_is_complete_and_points_at_real_facts(self):
        self.assertGreaterEqual(len(NEEDED), 25)
        self.assertEqual(len({q['id'] for q in NEEDED}), len(NEEDED))
        for q in NEEDED:
            self.assertIn(q['state'], STATES, q['id'])
            self.assertTrue(q['ask'].endswith('?'), q['id'])
            self.assertTrue(q['why'].strip(), q['id'])
            for fact in q['facts']:
                self.assertIn(fact, self.facts, q['id'])

    def test_known_means_every_fact_behind_it_is_verified(self):
        for q in NEEDED:
            if q['state'] == 'known':
                self.assertTrue(q['facts'], q['id'])
                for fact in q['facts']:
                    self.assertEqual(self.facts[fact]['status'], 'verified', f'{q["id"]}: {fact}')

    def test_anything_not_known_says_how_to_find_out(self):
        for q in NEEDED:
            if q['state'] != 'known':
                self.assertTrue(q.get('find_out', '').strip(), q['id'])

    def test_the_size_of_app1_is_asked_and_known(self):
        size = next(q for q in NEEDED if 'hw.update.app1-range' in q['facts'])
        self.assertEqual(size['state'], 'known')

    def test_gaps_lists_what_is_not_known_and_nothing_else(self):
        listed = {q['id'] for q in gaps()}
        self.assertEqual(listed, {q['id'] for q in NEEDED if q['state'] != 'known'})
        self.assertTrue(listed)


if __name__ == '__main__':
    unittest.main()
