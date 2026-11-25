"""The knowledge tools on fixtures, and the real knowledge base as data: it must always load and its byte checks must pass."""
import json
import tempfile
import unittest
from pathlib import Path

from lab404.identify import TABLE, identify
from lab404.knowledge import Knowledge, KnowledgeError, ROOT, firmware_id_of
from lab404.observe import evidence_for
from helpers import DOOM72, DOOM73, STOCK, tiny_image

EVIDENCE = [{'label': 'DOC', 'source': 'test'}]


def tree(tmp, facts=(), bindings=None):
    (tmp/'facts').mkdir()
    (tmp/'bindings').mkdir()
    (tmp/'controls.json').write_text(json.dumps({'controls': [{'name': n} for n in ('SHIFT', 'VALUE', 'PAD1', 'PAD2')]}), encoding='utf-8')
    (tmp/'facts/t.json').write_text(json.dumps({'facts': list(facts)}), encoding='utf-8')
    for name, data in (bindings or {}).items():
        (tmp/f'bindings/{name}.json').write_text(json.dumps(data), encoding='utf-8')
    return Knowledge(tmp)


def fact(**over):
    base = dict(id='f1', claim='a claim', topic='t', firmware='stock-5.52', status='verified', evidence=EVIDENCE)
    base.update(over)
    return base


def binding(**over):
    base = dict(id='b1', screen='main', keys=['SHIFT', 'PAD1'], gesture='press', action='does a thing', status='verified', evidence=EVIDENCE)
    base.update(over)
    return base


class Fixtures(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tmp = Path(d.name)

    def test_bad_records_are_refused(self):
        for bad in (fact(evidence=[]), fact(status='sure'), fact(firmware='stock-9.99'), fact(evidence=[{'label': 'VIBES', 'source': 'x'}]),
                    fact(status='verified', evidence=[{'label': 'HYPOTHESIS', 'source': 'x'}])):
            with tempfile.TemporaryDirectory() as d, self.assertRaises(KnowledgeError):
                tree(Path(d), [bad])

    def test_duplicate_ids_refused(self):
        with self.assertRaisesRegex(KnowledgeError, 'duplicate'):
            tree(self.tmp, [fact(), fact()])

    def test_unknown_control_refused(self):
        data = dict(firmware='stock-5.52', coverage={}, bindings=[binding(keys=['ANYKEY'])])
        with self.assertRaisesRegex(KnowledgeError, 'unknown control'):
            tree(self.tmp, bindings={'stock': data})

    def test_query_respects_firmware(self):
        k = tree(self.tmp, [fact(claim='voice table')])
        self.assertEqual(len(k.query('VOICE')), 1)
        self.assertEqual(k.query('voice', 'doom-os-0.7.3'), [])
        self.assertEqual(k.query('nothing'), [])

    def test_words_are_found_in_any_order_and_the_exact_phrase_comes_first(self):
        k = tree(self.tmp, [fact(id='a', claim='the limit on the size of a file'), fact(id='b', claim='size limit'), fact(id='c', claim='size only')])
        self.assertEqual([f['id'] for f in k.query('size limit')], ['b', 'a'])

    def test_topics_are_listed_with_their_counts(self):
        k = tree(self.tmp, [fact(id='a'), fact(id='b')])
        self.assertEqual(k.topics(), {fact()['topic']: 2})

    def test_keys_occupied_free_and_unknown(self):
        stock = dict(firmware='stock-5.52', coverage={'main': 'complete', 'menu': 'partial'}, bindings=[binding()])
        k = tree(self.tmp, bindings={'stock': stock})
        self.assertEqual(k.check_keys('stock-5.52', 'main', ['PAD1', 'SHIFT'])[0], 'occupied')
        self.assertEqual(k.check_keys('stock-5.52', 'main', ['SHIFT', 'PAD2']), ('free', None))
        self.assertEqual(k.check_keys('stock-5.52', 'main', ['SHIFT', 'PAD1'], 'hold')[0], 'occupied')
        self.assertEqual(k.check_keys('stock-5.52', 'menu', ['SHIFT', 'PAD2'])[0], 'unknown')
        self.assertEqual(k.check_keys('stock-5.52', 'never-seen', ['SHIFT', 'PAD2'])[0], 'unknown')
        self.assertEqual(k.check_keys('doom-os-0.7.3', 'main', ['SHIFT', 'PAD2'])[0], 'unknown')

    def test_mod_inherits_base_bindings_and_cannot_claim_free_past_them(self):
        stock = dict(firmware='stock-5.52', coverage={'main': 'complete'}, bindings=[binding()])
        doom = dict(firmware='doom-os-0.7.3', inherits='stock-5.52', coverage={'main': 'partial'},
                    bindings=[binding(id='b2', keys=['SHIFT', 'VALUE'])])
        k = tree(self.tmp, bindings={'stock': stock, 'doom': doom})
        self.assertEqual(k.check_keys('doom-os-0.7.3', 'main', ['SHIFT', 'PAD1'])[1]['id'], 'b1')
        self.assertEqual(k.check_keys('doom-os-0.7.3', 'main', ['SHIFT', 'VALUE'])[1]['id'], 'b2')
        self.assertEqual(k.check_keys('doom-os-0.7.3', 'main', ['SHIFT', 'PAD2'])[0], 'unknown')

    def test_byte_checks(self):
        checks = [dict(firmware='stock-5.52', address='0x1000', hex='7047'), dict(firmware='stock-5.52', address='0x1000', hex='0000'),
                  dict(firmware='stock-5.52', address='0x900000', hex='00'), dict(firmware='doom-os-0.7.3', address='0x1000', hex='0000')]
        k = tree(self.tmp, [fact(checks=checks)])
        results = k.verify(tiny_image(), 'stock-5.52')
        self.assertEqual([r[1] for r in results], ['pass', 'fail', 'fail'])

    def test_a_fingerprint_check_passes_and_fails_like_the_bytes(self):
        import hashlib
        right, wrong = hashlib.sha256(bytes.fromhex('7047')).hexdigest(), hashlib.sha256(b'\0\0').hexdigest()
        checks = [dict(firmware='stock-5.52', address='0x1000', size=2, sha256=right),
                  dict(firmware='stock-5.52', address='0x1000', size=2, sha256=wrong)]
        k = tree(self.tmp, [fact(checks=checks)])
        self.assertEqual([r[1] for r in k.verify(tiny_image(), 'stock-5.52')], ['pass', 'fail'])

    def test_a_check_without_bytes_or_fingerprint_is_refused(self):
        with self.assertRaises(KnowledgeError):
            tree(self.tmp, [fact(checks=[dict(firmware='stock-5.52', address='0x1000')])])


class RealKnowledge(unittest.TestCase):
    def test_loads(self):
        self.assertGreaterEqual(len(Knowledge(ROOT).facts), 0)

    def test_byte_checks_pass_on_real_images(self):
        k = Knowledge(ROOT)
        for path in (STOCK, DOOM73, DOOM72):
            if not path.exists():
                continue
            raw = path.read_bytes()
            entry = next(e for e in TABLE if e['sha256'] == identify(raw)['sha256'])
            failed = [r for r in k.verify(raw, firmware_id_of(entry)) if r[1] != 'pass']
            self.assertEqual(failed, [], path)


class Observations(unittest.TestCase):
    """[EMULATOR] evidence on a binding must stand on a recorded observation, and every binding must be accounted for."""

    def setUp(self):
        self.record = json.loads((ROOT/'observations/stock-5.52.json').read_text(encoding='utf-8'))
        self.bindings = Knowledge().bindings['stock-5.52']['bindings']

    def test_every_binding_is_observed_or_says_why_not(self):
        self.assertEqual(set(self.record['verdicts']) | set(self.record['not_tried']), {b['id'] for b in self.bindings})
        self.assertFalse(set(self.record['verdicts']) & set(self.record['not_tried']))

    def test_emulator_evidence_matches_the_record(self):
        for binding in self.bindings:
            seen = [e for e in binding['evidence'] if e['label'] == 'EMULATOR']
            wanted = evidence_for(binding['id'], self.record)
            self.assertEqual(seen, [wanted] if wanted else [], binding['id'])

    def test_a_contradiction_is_not_left_lying_around(self):
        self.assertEqual([k for k, v in self.record['verdicts'].items() if v['verdict'] == 'contradicted'], [])

    def test_the_record_names_its_experiments(self):
        self.assertTrue(self.record['experiments'])
        for experiment in self.record['experiments']:
            self.assertEqual(experiment['image_sha256'], next(e['sha256'] for e in TABLE if e['family'] == 'stock' and e['version'].startswith('5.52')))


class WhatAModNeeds(unittest.TestCase):
    """The clean-agent exam had to work these out with a probe. They belong in the knowledge base."""

    def test_key_codes_and_the_event_format_can_be_asked_for(self):
        k = Knowledge()
        codes = k.query('key code')
        self.assertTrue(any('HOLD 0x11' in fact['claim'] and 'LOOP 0x1F' in fact['claim'] for fact in codes))
        self.assertTrue(any('type' in fact['claim'] and 'press' in fact['claim'] for fact in k.query('key event')))

    def test_opening_a_screen_can_be_asked_for(self):
        self.assertTrue(any('0x800DA598' in fact['claim'] for fact in Knowledge().query('open a screen')))


class TheLoader(unittest.TestCase):
    """What a dump of the main processor's loader showed. A mod author must be able to ask what can brick a unit."""

    def setUp(self):
        self.facts = {f['id']: f for f in Knowledge().facts}

    def test_it_says_the_loader_checks_nothing_in_app1(self):
        fact = self.facts['hw.boot.no-app1-check']
        self.assertEqual(fact['status'], 'verified')
        self.assertIn('0x60080001', fact['claim'])
        self.assertIn('one unit', ' '.join(e['source'] for e in fact['evidence']))

    def test_the_size_limit_can_be_asked_for(self):
        self.assertTrue(any('0x37F000' in f['claim'] for f in Knowledge().query('size limit')))

    def test_the_files_that_rewrite_the_loader_can_be_asked_for(self):
        found = ' '.join(f['claim'] for f in Knowledge().query('brick'))
        for name in ('SP404MKII_APP1W.bin', 'MIRXRT1060-EVK.bin', 'SP404MKII_APP1U.bin'):
            self.assertIn(name, found)

    def test_who_drives_the_select_pin_stays_unknown(self):
        self.assertEqual(self.facts['hw.boot.select-pin-driver']['status'], 'unknown')

    def test_what_the_registers_of_a_unit_showed_is_recorded_without_its_serial_number(self):
        mode, dog, back = self.facts['hw.boot.mode'], self.facts['hw.watchdogs.runtime'], self.facts['hw.boot.recovery-usb']
        self.assertIn('HARDWARE', {e['label'] for e in mode['evidence']})
        self.assertIn('0x02000009', mode['claim'])
        self.assertEqual(dog['status'], 'verified')
        self.assertEqual(back['status'], 'hypothesis')
        self.assertIn('never erase', back['claim'])
        for fact in (mode, dog, back):
            self.assertNotIn('0x410', fact['claim'])

    def test_the_older_boot_fact_points_to_the_new_ones(self):
        self.assertIn('hw.boot.loader-image', self.facts['hw.boot.rom']['claim'])


class InterruptedUpdates(unittest.TestCase):
    """The owner's own experience of stalled updates, recorded as a report and not as a promise."""

    def test_the_report_is_there_as_hardware_evidence_and_says_it_was_not_bricked(self):
        facts = {f['id']: f for f in Knowledge().facts}
        report = facts['hw.update.stalled']
        self.assertIn('HARDWARE', {e['label'] for e in report['evidence']})
        self.assertIn('not bricked', report['claim'])
        self.assertIn('not a guarantee', report['claim'])

    def test_the_cause_is_backed_by_the_swap_to_a_good_card(self):
        cause = {f['id']: f for f in Knowledge().facts}['hw.update.stalled-cause']
        self.assertEqual(cause['status'], 'verified')
        self.assertIn('first attempt', cause['claim'])
        self.assertIn('one card swap on one unit', cause['claim'])
        self.assertEqual({e['label'] for e in cause['evidence']}, {'HARDWARE'})

    def test_what_is_not_known_is_written_down(self):
        claim = {f['id']: f for f in Knowledge().facts}['hw.update.stalled']['claim']
        for gap in ('date', 'firmware version', 'which card'):
            self.assertIn(gap, claim)

    def test_the_older_app0_note_points_to_it(self):
        self.assertIn('hw.update.stalled', {f['id']: f for f in Knowledge().facts}['app0.recovery']['claim'])


class KeyConflicts(unittest.TestCase):
    """An input is taken if any step on the way to it already does something. Hotkey contract, docs/PLAN.md."""

    def knowledge(self, *bindings):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        records = [dict(id=f'b{i}', screen=screen, keys=keys, gesture=gesture, action=f'action {i}', status='verified', evidence=EVIDENCE) for i, (screen, keys, gesture) in enumerate(bindings)]
        tree(root, bindings={'fw': dict(firmware='stock-5.52', coverage={'s': 'complete'}, bindings=records)})
        return Knowledge(root)

    def test_a_longer_chord_cannot_start_with_an_occupied_one(self):
        k = self.knowledge(('s', ['SHIFT', 'PAD1'], 'press'))
        state, binding = k.check_keys('stock-5.52', 's', ['SHIFT', 'PAD1', 'PAD2'])
        self.assertEqual(state, 'occupied')
        self.assertEqual(binding['conflict'], 'starts with SHIFT+PAD1')

    def test_a_modifier_with_its_own_press_is_a_conflict(self):
        state, _ = self.knowledge(('s', ['PAD1'], 'press')).check_keys('stock-5.52', 's', ['PAD1', 'PAD2'])
        self.assertEqual(state, 'occupied')

    def test_the_prefix_follows_the_order_of_the_keys(self):
        self.assertEqual(self.knowledge(('s', ['PAD1'], 'press')).check_keys('stock-5.52', 's', ['PAD2', 'PAD1'])[0], 'free')

    def test_holding_keys_that_a_press_uses_is_occupied_both_ways(self):
        k = self.knowledge(('s', ['PAD1'], 'press'), ('s', ['PAD2'], 'hold'))
        self.assertEqual(k.check_keys('stock-5.52', 's', ['PAD1'], 'hold')[0], 'occupied')
        self.assertEqual(k.check_keys('stock-5.52', 's', ['PAD2'], 'press')[0], 'occupied')

    def test_a_turn_and_a_press_of_the_same_control_are_different_inputs(self):
        k = self.knowledge(('s', ['VALUE'], 'press'))
        self.assertEqual(k.check_keys('stock-5.52', 's', ['VALUE'], 'turn')[0], 'free')

    def test_press_and_turn_together_collides_with_either(self):
        k = self.knowledge(('s', ['VALUE'], 'turn'))
        self.assertEqual(k.check_keys('stock-5.52', 's', ['VALUE'], 'press_turn')[0], 'occupied')

    def test_a_longer_chord_that_only_shares_keys_out_of_order_is_free(self):
        self.assertEqual(self.knowledge(('s', ['SHIFT', 'PAD1'], 'press')).check_keys('stock-5.52', 's', ['PAD1', 'PAD2'])[0], 'free')


class IrakliyMod(unittest.TestCase):
    def test_it_is_found_and_its_own_keys_are_occupied(self):
        k = Knowledge()
        self.assertTrue(k.query('IrakliyMOD'))
        state, binding = k.check_keys('irakliymod', 'sample', ['RECORD SETTING', 'DELAY'])
        self.assertEqual(state, 'occupied')
        self.assertIn('FX MOD', binding['action'])

    def test_keys_it_does_not_list_stay_unknown_not_free(self):
        self.assertEqual(Knowledge().check_keys('irakliymod', 'sample', ['CTRL1', 'PAD1'])[0], 'unknown')

    def test_stock_keys_are_inherited(self):
        self.assertEqual(Knowledge().check_keys('irakliymod', 'sample', ['LOOP'])[0], 'occupied')


if __name__ == '__main__':
    unittest.main()
