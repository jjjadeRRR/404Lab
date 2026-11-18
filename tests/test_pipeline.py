"""From a mod folder to a package, and every way it must refuse. The emulator comparison is faked here for speed: tests/test_emulator.py runs it for real."""
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from lab404.build import BuildError, build, source_digest
from lab404.check import check_structure
from lab404.image import sha256, table_bounds
from lab404.knowledge import Knowledge
from lab404.pipeline import PackageRefused, approve, interface_digest, package, preview, replay_verdicts
from helpers import DOOM72, DOOM73, ROOT, STOCK

MOD = ROOT/'mods/quick_system'
SAYS = 'Yes, go ahead.'


def fine(*_):
    return [dict(check='replay', state='pass', detail='fake')]


@unittest.skipUnless(STOCK.exists() and DOOM73.exists(), 'firmware inputs not present')
class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mod = self.root/'mod'
        shutil.copytree(MOD, self.mod)

    def edit(self, change):
        path = self.mod/'mod.json'
        spec = json.loads(path.read_text(encoding='utf-8'))
        change(spec)
        path.write_text(json.dumps(spec), encoding='utf-8')

    def unknowns(self):
        """What must be accepted for this mod, as the refusal lists it."""
        approve(self.mod, SAYS)
        with self.assertRaises(PackageRefused) as caught:
            package(self.mod, STOCK, self.root/'first', replay=fine)
        self.assertFalse((self.root/'first').exists())
        return caught.exception.unknown

    def ready(self, base=STOCK, out='pkg', **kwargs):
        accepted = {name: SAYS for name in self.unknowns()}
        return package(self.mod, base, self.root/out, accepted=accepted, replay=fine, **kwargs)

    def test_a_good_task_gives_a_package_bound_to_everything(self):
        report = self.ready()
        out = self.root/'pkg'
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['SP404MKII_APP1.bin', 'UNIT_CHECKS.md', 'manifest.json', 'report.json'])
        saved = json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, report)
        for field in ('candidate_sha256', 'parent_sha256', 'source_sha256', 'source_revision', 'profile', 'test_inputs', 'interface_sha256', 'approval', 'accepted_unknowns'):
            self.assertTrue(saved.get(field), field)
        self.assertEqual(saved['profile']['firmware'], 'stock-5.52')
        self.assertIn('candidate', saved['status'])
        checks = (out/'UNIT_CHECKS.md').read_text(encoding='utf-8')
        self.assertIn('HOLD', checks)
        for step in ('SP404MKII_APP1.bin', 'SD card', 'SHIFT', 'VALUE', 'back up', 'card you trust', 'stalls', 'first attempt'):
            self.assertIn(step, checks, 'it must say how to install and how to go back')

    def test_it_works_on_the_second_base(self):
        self.assertEqual(self.ready(DOOM73)['profile']['firmware'], 'doom-os-0.7.3')

    def test_wrong_app1_is_refused(self):
        approve(self.mod, SAYS)
        for wrong in (DOOM72, ROOT/'README.md'):
            with self.assertRaises((PackageRefused, BuildError)):
                package(self.mod, wrong, self.root/'x', replay=fine)
            self.assertFalse((self.root/'x').exists())

    def test_no_approval_is_refused(self):
        with self.assertRaisesRegex(PackageRefused, 'not been approved'):
            package(self.mod, STOCK, self.root/'x', replay=fine)

    def test_an_approval_does_not_survive_a_change_to_the_interface(self):
        approve(self.mod, SAYS)
        self.edit(lambda spec: spec['adds']['bindings'][0].update(keys=['HOLD', 'REVERSE']))
        with self.assertRaisesRegex(PackageRefused, 'changed since'):
            package(self.mod, STOCK, self.root/'x', replay=fine)

    def test_an_occupied_hotkey_is_refused_and_acceptance_cannot_overrule_it(self):
        self.edit(lambda spec: (spec['adds']['bindings'][0].update(keys=['SHIFT', 'LOOP']), spec['adds']['demonstrate'][0].update(keys=['SHIFT', 'LOOP'])))
        approve(self.mod, SAYS)
        with self.assertRaises(PackageRefused) as caught:
            package(self.mod, STOCK, self.root/'x', accepted={'keys: SHIFT+LOOP press on sample': SAYS}, replay=fine)
        self.assertTrue(any('SHIFT+LOOP' in name for name in caught.exception.failed))

    def test_a_chord_starting_with_an_occupied_input_is_refused(self):
        self.edit(lambda spec: (spec['adds']['bindings'][0].update(keys=['SHIFT', 'LOOP', 'PAD1']), spec['adds']['demonstrate'][0].update(keys=['SHIFT', 'LOOP', 'PAD1'])))
        approve(self.mod, SAYS)
        with self.assertRaises(PackageRefused) as caught:
            package(self.mod, STOCK, self.root/'x', replay=fine)
        self.assertTrue(caught.exception.failed)

    def test_a_damaged_hook_is_refused(self):
        # A hook on a site that is not a function entry on this base.
        self.edit(lambda spec: spec['hooks'][0].update(address='0x800A80AA'))
        approve(self.mod, SAYS)
        with self.assertRaises((PackageRefused, BuildError, ValueError)):
            package(self.mod, STOCK, self.root/'x', replay=fine)
        self.assertFalse((self.root/'x').exists())

    def test_an_overlapping_allocation_is_refused(self):
        self.edit(lambda spec: spec['payload'].update(address='0x1000'))
        approve(self.mod, SAYS)
        with self.assertRaises((PackageRefused, BuildError, ValueError)):
            package(self.mod, STOCK, self.root/'x', replay=fine)
        self.assertFalse((self.root/'x').exists())

    def test_a_failed_comparison_is_refused_whatever_was_accepted(self):
        def bad(*_):
            return [dict(check='replay', state='fail', detail='a screen differs')]
        approve(self.mod, SAYS)
        with self.assertRaises(PackageRefused) as caught:
            package(self.mod, STOCK, self.root/'x', accepted={'replay': SAYS}, replay=bad)
        self.assertIn('replay', caught.exception.failed)
        self.assertFalse((self.root/'x').exists())

    def test_every_unknown_must_be_accepted_by_name_and_a_stray_acceptance_is_refused(self):
        names = self.unknowns()
        self.assertTrue(names)
        self.assertTrue(any(name.startswith('contract:') for name in names), names)
        partly = {name: SAYS for name in names[1:]}
        with self.assertRaises(PackageRefused) as caught:
            package(self.mod, STOCK, self.root/'x', accepted=partly, replay=fine)
        self.assertEqual(caught.exception.unknown, names[:1])
        with self.assertRaisesRegex(PackageRefused, 'nothing by that name'):
            package(self.mod, STOCK, self.root/'x', accepted={**partly, names[0]: SAYS, 'made up': SAYS}, replay=fine)

    def test_an_empty_acceptance_is_not_an_acceptance(self):
        names = self.unknowns()
        with self.assertRaises(PackageRefused):
            package(self.mod, STOCK, self.root/'x', accepted={name: ' ' for name in names}, replay=fine)

    def test_unknown_reasons_are_shown_before_acceptance_and_kept_with_the_package(self):
        def incomplete(*_):
            return [dict(check='sample check', state='unknown', detail='PAD3 had no sample to play')]
        approve(self.mod, SAYS)
        with self.assertRaises(PackageRefused) as caught:
            package(self.mod, STOCK, self.root/'first', replay=incomplete)
        self.assertIn('PAD3 had no sample to play', str(caught.exception))
        self.assertIn('Listen', str(caught.exception))
        names = caught.exception.unknown
        self.assertIn('sample check', names)
        package(self.mod, STOCK, self.root/'pkg', accepted={name: SAYS for name in names}, replay=incomplete)
        checks = (self.root/'pkg/UNIT_CHECKS.md').read_text(encoding='utf-8')
        self.assertIn('PAD3 had no sample to play', checks)
        self.assertIn('second processor', checks)

    def test_a_failed_comparison_explains_what_differed(self):
        def bad(*_):
            return [dict(check='replay', state='fail', detail='page differs after EXIT')]
        approve(self.mod, SAYS)
        with self.assertRaises(PackageRefused) as caught:
            package(self.mod, STOCK, self.root/'x', replay=bad)
        self.assertIn('page differs after EXIT', str(caught.exception))

    def test_declared_keys_and_demonstrated_keys_must_be_the_same(self):
        self.edit(lambda spec: spec['adds']['demonstrate'][0].update(keys=['HOLD', 'REVERSE']))
        approve(self.mod, SAYS)
        with self.assertRaisesRegex(PackageRefused, 'demonstrate'):
            package(self.mod, STOCK, self.root/'x', replay=fine)

    def test_two_packages_at_once_do_not_share_a_staging_folder(self):
        names = self.unknowns()
        def sneaky(*_):
            leftovers = list(self.root.glob('*.building*'))
            self.assertEqual(len(leftovers), 1)
            (self.root/'other.building').mkdir()
            return fine()
        report = package(self.mod, STOCK, self.root/'pkg', accepted={name: SAYS for name in names}, replay=sneaky)
        self.assertEqual(sha256((self.root/'pkg/SP404MKII_APP1.bin').read_bytes()), report['candidate_sha256'])
        self.assertFalse([p for p in self.root.glob('pkg.building*')])

    def test_changed_bytes_after_checking_are_not_published(self):
        names = self.unknowns()
        def tamper(_base, _candidate, *_):
            for path in self.root.glob('*.building*/SP404MKII_APP1.bin'):
                path.write_bytes(b'not what was checked')
            return fine()
        with self.assertRaisesRegex(PackageRefused, 'changed after'):
            package(self.mod, STOCK, self.root/'x', accepted={name: SAYS for name in names}, replay=tamper)
        self.assertFalse((self.root/'x').exists())

    def test_sources_changed_during_the_comparison_cannot_label_an_old_candidate(self):
        names = self.unknowns()
        def edit_during_replay(*_):
            source = self.mod/'quick_system.c'
            source.write_text(source.read_text(encoding='utf-8')+'\n/* edited during the emulator run */\n', encoding='utf-8')
            return fine()
        with self.assertRaisesRegex(PackageRefused, 'sources changed'):
            package(self.mod, STOCK, self.root/'x', accepted={name: SAYS for name in names}, replay=edit_during_replay)
        self.assertFalse((self.root/'x').exists())
        self.assertFalse(list(self.root.glob('x.building-*')))

    def test_the_source_digest_covers_every_file_in_the_mod(self):
        before = source_digest(self.mod, json.loads((self.mod/'mod.json').read_text(encoding='utf-8')))
        (self.mod/'helper.h').write_text('#define X 1\n', encoding='utf-8')
        self.assertNotEqual(before, source_digest(self.mod, json.loads((self.mod/'mod.json').read_text(encoding='utf-8'))))

    def test_approval_is_not_part_of_the_source_digest(self):
        before = source_digest(self.mod, json.loads((self.mod/'mod.json').read_text(encoding='utf-8')))
        approve(self.mod, SAYS)
        self.assertEqual(before, source_digest(self.mod, json.loads((self.mod/'mod.json').read_text(encoding='utf-8'))))

    def test_a_package_is_never_written_over(self):
        self.ready()
        with self.assertRaisesRegex(PackageRefused, 'exists'):
            self.ready()

    def test_a_mod_with_nothing_to_check_on_the_unit_is_refused(self):
        self.edit(lambda spec: spec['task'].update(unit_checks=[]))
        approve(self.mod, SAYS)
        with self.assertRaisesRegex(PackageRefused, 'what to check on the unit'):
            package(self.mod, STOCK, self.root/'x', replay=fine)

    def test_the_preview_shows_keys_with_their_answers_and_binds_to_the_interface(self):
        text = preview(self.mod, STOCK)
        self.assertIn('HOLD+ROLL', text)
        self.assertIn('unknown', text)
        self.assertIn(interface_digest(json.loads((self.mod/'mod.json').read_text(encoding='utf-8'))), text)

    def test_the_preview_draws_a_new_screen_and_refuses_one_that_cannot_fit(self):
        self.edit(lambda spec: spec['adds'].update(screens=[dict(name='My page', lines=['LEVEL 12', 'MODE A'])]))
        text = preview(self.mod, STOCK)
        self.assertIn('| LEVEL 12', text)
        self.edit(lambda spec: spec['adds'].update(screens=[dict(name='Too wide', lines=['X'*30])]))
        with self.assertRaisesRegex(PackageRefused, 'does not fit'):
            preview(self.mod, STOCK)


@unittest.skipUnless(STOCK.exists(), 'firmware inputs not present')
class Allocation(unittest.TestCase):
    def test_the_final_check_itself_rejects_a_row_that_overwrites_existing_memory(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = build(ROOT/'mods/demo_counter', STOCK, Path(d)/'pkg')
            candidate = bytearray((Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes())
        start, end = table_bounds(bytes(candidate))
        base_raw = STOCK.read_bytes()
        first_runtime = struct.unpack_from('<I', candidate, start+4)[0]
        struct.pack_into('<I', candidate, end-12, first_runtime)
        results = {r['check']: r['state'] for r in check_structure(base_raw, bytes(candidate), manifest)}
        self.assertEqual(results['allocation'], 'fail')


class ReplayVerdicts(unittest.TestCase):
    """base, a second boot of the base, and the candidate, one state per step."""

    STEPS = ['A', 'B', 'C', 'D']

    def states(self, *frames):
        return [dict(step=s, frame=f, page=1, lights={}) for s, f in zip(self.STEPS, frames)]

    def test_matching_passes(self):
        a = self.states('1', '2', '3', '1')
        self.assertEqual(replay_verdicts(a, a, a)['state'], 'pass')

    def test_an_unsettled_candidate_is_not_a_pass_even_if_one_frame_matches(self):
        a = self.states('1', '2', '3', '1')
        candidate = self.states('1', '2', '3', '1')
        candidate[1]['settled'] = False
        got = replay_verdicts(a, a, candidate)
        self.assertEqual(got['state'], 'unknown')
        self.assertIn('B', got['detail'])
        self.assertIn('candidate', got['detail'])

    def test_an_unsettled_step_does_not_hide_a_difference_at_a_settled_step(self):
        a = self.states('1', '2', '3', '1')
        candidate = self.states('1', '2', 'x', '1')
        candidate[1]['settled'] = False
        self.assertEqual(replay_verdicts(a, a, candidate)['state'], 'fail')

    def test_different_step_sequences_cannot_be_compared_as_if_they_were_the_same(self):
        a = self.states('1', '2', '3', '1')
        changed = self.states('1', '2', '3', '1')
        changed[1]['step'] = 'OTHER KEY'
        for base, again, candidate in ((a, a, changed), (a, changed, a)):
            self.assertEqual(replay_verdicts(base, again, candidate)['state'], 'fail')

    def test_a_difference_fails_and_names_the_step(self):
        a = self.states('1', '2', '3', '1')
        got = replay_verdicts(a, a, self.states('1', '2', 'x', '1'))
        self.assertEqual(got['state'], 'fail')
        self.assertIn('C', got['detail'])

    def test_what_differs_between_two_boots_of_the_base_is_not_held_against_the_candidate_but_stays_visible(self):
        a, b = self.states('1', '2', '3', '1'), self.states('1', 'n', '3', '1')
        got = replay_verdicts(a, b, self.states('1', 'x', '3', '1'))
        self.assertEqual(got['state'], 'unknown', 'an ignored step must be accepted, not silently passed')
        self.assertIn('B', got['detail'])

    def test_a_noisy_picture_does_not_hide_a_wrong_page(self):
        a, b = self.states('1', '2', '3', '1'), self.states('1', 'n', '3', '1')
        candidate = self.states('1', 'x', '3', '1')
        candidate[1]['page'] = 99
        self.assertEqual(replay_verdicts(a, b, candidate)['state'], 'fail')

    def test_a_real_difference_fails_even_when_the_walk_says_little_otherwise(self):
        still = self.states('1', '1', '1', '1')
        self.assertEqual(replay_verdicts(still, still, self.states('1', 'x', '1', '1'))['state'], 'fail')
        noisy = self.states('n', 'm', '3', '1')
        self.assertEqual(replay_verdicts(self.states('1', '2', '3', '1'), noisy, self.states('1', '2', 'x', '1'))['state'], 'fail')

    def test_an_unread_page_is_not_a_match(self):
        a = self.states('1', '2', '3', '1')
        for state in a:
            state['page'] = None
        self.assertEqual(replay_verdicts(a, a, a)['state'], 'unknown')

    def test_a_walk_where_nothing_happened_cannot_pass(self):
        a = self.states('1', '1', '1', '1')
        self.assertEqual(replay_verdicts(a, a, a)['state'], 'unknown')

    def test_a_walk_with_too_much_noise_cannot_pass(self):
        a, b = self.states('1', '2', '3', '1'), self.states('n', 'm', '3', '1')
        self.assertEqual(replay_verdicts(a, b, a)['state'], 'unknown')

    def test_a_lost_step_fails(self):
        a = self.states('1', '2', '3', '1')
        self.assertEqual(replay_verdicts(a, a, a[:2])['state'], 'fail')


if __name__ == '__main__':
    unittest.main()
