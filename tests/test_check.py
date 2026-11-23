"""A candidate is refused for each thing that can go wrong. Each case below must fail or report unknown, never pass."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from lab404.build import build
from lab404.check import check_candidate
from lab404.knowledge import Knowledge
from helpers import DOOM73, ROOT, STOCK

MOD = ROOT/'mods/demo_counter'


def states(report):
    return {r['check']: r['state'] for r in report['results']}


def keys_tree(tmp):
    root = tmp/'knowledge'
    (root/'bindings').mkdir(parents=True)
    (root/'controls.json').write_text(json.dumps({'controls': [{'name': n} for n in ('SHIFT', 'PAD1', 'PAD2')]}), encoding='utf-8')
    (root/'bindings/stock.json').write_text(json.dumps(dict(firmware='stock-5.52', coverage={'main': 'complete', 'menu': 'partial'}, bindings=[
        dict(id='b1', screen='main', keys=['SHIFT', 'PAD1'], gesture='press', action='taken', status='verified', evidence=[dict(label='DOC', source='t')])])), encoding='utf-8')
    return Knowledge(root)


@unittest.skipUnless(STOCK.exists() and DOOM73.exists(), 'firmware inputs not present')
class Candidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='lab404-check-'))
        cls.package = cls.tmp/'good'
        build(MOD, STOCK, cls.package)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def copy_package(self, name):
        target = self.tmp/name
        shutil.copytree(self.package, target)
        return target

    def copy_mod(self, name):
        target = self.tmp/name
        shutil.copytree(MOD, target)
        return target

    def test_good_candidate_passes_and_says_what_a_pass_means(self):
        report = check_candidate(self.package, MOD, STOCK)
        self.assertEqual(report['overall'], 'pass', report['results'])
        self.assertIn('does not show', report['meaning'])
        self.assertEqual(states(report)['compatibility: mixer_output_unchanged'], 'pass')

    def test_also_passes_on_the_second_base(self):
        package = self.tmp/'doom'
        build(MOD, DOOM73, package)
        self.assertEqual(check_candidate(package, MOD, DOOM73)['overall'], 'pass')

    def test_swapped_file_is_caught(self):
        package = self.copy_package('stale')
        raw = bytearray((package/'SP404MKII_APP1.bin').read_bytes())
        raw[-1] ^= 1
        (package/'SP404MKII_APP1.bin').write_bytes(raw)
        report = check_candidate(package, MOD, STOCK)
        self.assertEqual(states(report)['candidate-file'], 'fail')
        self.assertEqual(report['overall'], 'fail')

    def test_wrong_base_is_caught(self):
        report = check_candidate(self.package, MOD, DOOM73)
        self.assertEqual(states(report)['parent'], 'fail')
        self.assertEqual(report['overall'], 'fail')

    def test_changed_sources_are_caught(self):
        mod = self.copy_mod('changed')
        (mod/'counter.c').write_text((mod/'counter.c').read_text(encoding='utf-8')+'\n', encoding='utf-8')
        self.assertEqual(states(check_candidate(self.package, mod, STOCK))['sources'], 'fail')

    def test_damaged_hook_is_caught(self):
        package = self.copy_package('damaged')
        manifest = json.loads((package/'manifest.json').read_text(encoding='utf-8'))
        raw = bytearray((package/'SP404MKII_APP1.bin').read_bytes())
        offset = STOCK.read_bytes().index(bytes.fromhex(manifest['hooks'][0]['before']))
        raw[offset] ^= 0xFF
        (package/'SP404MKII_APP1.bin').write_bytes(raw)
        manifest['candidate_sha256'] = __import__('hashlib').sha256(bytes(raw)).hexdigest()
        (package/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.assertEqual(states(check_candidate(package, MOD, STOCK))['hooks'], 'fail')

    def test_undeclared_change_is_caught(self):
        package = self.copy_package('undeclared')
        manifest = json.loads((package/'manifest.json').read_text(encoding='utf-8'))
        raw = bytearray((package/'SP404MKII_APP1.bin').read_bytes())
        raw[0x100000] ^= 1
        (package/'SP404MKII_APP1.bin').write_bytes(raw)
        manifest['candidate_sha256'] = __import__('hashlib').sha256(bytes(raw)).hexdigest()
        (package/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.assertEqual(states(check_candidate(package, MOD, STOCK))['undeclared-changes'], 'fail')

    def resign(self, package, manifest, raw):
        (package/'SP404MKII_APP1.bin').write_bytes(raw)
        manifest['candidate_sha256'] = __import__('hashlib').sha256(bytes(raw)).hexdigest()
        (package/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_a_declared_patch_over_loader_erase_code_is_caught(self):
        # Consistent with its own manifest, so only an independent look at the addresses can catch it (added 2026-11-23).
        from lab404.image import file_offset
        # Anything but the one allowed change: here a return of 1 at the entry, and a return of 0 one instruction in.
        for address, after in ((0x80065838, '01207047'), (0x8006583A, '00207047'), (0x8019D348, '00207047')):
            package = self.copy_package(f'loader-{address:X}-{after}')
            manifest = json.loads((package/'manifest.json').read_text(encoding='utf-8'))
            raw = bytearray((package/'SP404MKII_APP1.bin').read_bytes())
            at = file_offset(STOCK.read_bytes(), address, 4)
            before = bytes(raw[at:at+4])
            raw[at:at+4] = bytes.fromhex(after)
            manifest['hooks'].append(dict(address=hex(address), before=before.hex(), after=after))
            self.resign(package, manifest, raw)
            got = states(check_candidate(package, MOD, STOCK))
            self.assertEqual((got['hooks'], got['undeclared-changes'], got['loader-code']), ('pass', 'pass', 'fail'), hex(address))

    def test_a_guarded_service_routine_switched_off_is_allowed(self):
        # The maintainer's decision of 2026-11-23: movs r0,#0; bx lr at the entry of a guarded service routine takes a way to
        # lose the loader away (hw.service.loader-erase), so check accepts exactly that and reports it.
        from lab404.image import file_offset
        package = self.copy_package('switched-off')
        manifest = json.loads((package/'manifest.json').read_text(encoding='utf-8'))
        raw = bytearray((package/'SP404MKII_APP1.bin').read_bytes())
        at = file_offset(STOCK.read_bytes(), 0x80065838, 4)
        before = bytes(raw[at:at+4])
        raw[at:at+4] = bytes.fromhex('00207047')
        manifest['hooks'].append(dict(address='0x80065838', before=before.hex(), after='00207047'))
        self.resign(package, manifest, raw)
        report = check_candidate(package, MOD, STOCK)
        result = next(r for r in report['results'] if r['check'] == 'loader-code')
        self.assertEqual(result['state'], 'pass')
        self.assertIn('0x80065838', result['detail'])

    def test_a_candidate_past_the_app1_room_is_caught(self):
        package = self.copy_package('big')
        manifest = json.loads((package/'manifest.json').read_text(encoding='utf-8'))
        raw = (package/'SP404MKII_APP1.bin').read_bytes()
        self.resign(package, manifest, raw+bytes(0x37F000-len(raw)+4))
        self.assertEqual(states(check_candidate(package, MOD, STOCK))['flash-room'], 'fail')

    def test_occupied_free_and_unknown_keys(self):
        knowledge = keys_tree(self.tmp/'k1') if (self.tmp/'k1').mkdir() is None else None
        cases = [(dict(screen='main', keys=['SHIFT', 'PAD1']), 'fail'), (dict(screen='main', keys=['SHIFT', 'PAD2']), 'pass'),
                 (dict(screen='menu', keys=['SHIFT', 'PAD2']), 'unknown')]
        for i, (binding, want) in enumerate(cases):
            mod = self.copy_mod(f'keys{i}')
            spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
            spec['adds'] = dict(bindings=[binding])
            (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
            package = self.tmp/f'keys-package{i}'
            build(mod, STOCK, package)
            report = check_candidate(package, mod, STOCK, knowledge)
            label = f'keys: SHIFT+{binding["keys"][1]} press on {binding["screen"]}'
            self.assertEqual(states(report)[label], want, report['results'])
            self.assertEqual(report['overall'], want)

    def test_a_scenario_that_compared_nothing_is_unknown_not_pass(self):
        mod = self.copy_mod('empty-scenario')
        (mod/'scenarios.py').write_text('def mixer_output_unchanged(base, candidate):\n    pass\n', encoding='utf-8')
        package = self.tmp/'empty-pkg'
        build(mod, STOCK, package)
        got = states(check_candidate(package, mod, STOCK))
        self.assertEqual(got['compatibility: mixer_output_unchanged'], 'unknown')

    def test_the_report_names_the_revision_and_the_profile(self):
        report = check_candidate(self.package, MOD, STOCK)
        self.assertTrue(report['source_revision'])
        self.assertEqual(report['profile']['firmware'], 'stock-5.52')

    def test_no_scenarios_is_unknown_not_pass(self):
        mod = self.copy_mod('noscenario')
        spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
        del spec['scenarios']
        (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
        package = self.tmp/'noscenario-package'
        build(mod, STOCK, package)
        self.assertEqual(check_candidate(package, mod, STOCK)['overall'], 'unknown')

    def test_failing_scenario_is_a_failure(self):
        mod = self.copy_mod('breaks')
        (mod/'counter.c').write_text('volatile unsigned demo_counter_calls;\nvoid demo_counter_hook(void)\n{\n    demo_counter_calls++;\n'
                                     '    *(volatile int *)0x30004000 = 12345;\n}\n', encoding='utf-8')
        (mod/'scenarios.py').write_text((mod/'scenarios.py').read_text(encoding='utf-8').replace('return machine.read(DEST, WORDS*4)', 'return machine.read(DEST, WORDS*4)'), encoding='utf-8')
        (mod/'scenarios.py').write_text(
            'from pathlib import Path\nimport struct\n'
            'def mixer_output_unchanged(base, candidate):\n'
            '    base.write(0x30004000, bytes(4)); candidate.write(0x30004000, bytes(4))\n'
            '    for m in (base, candidate):\n'
            '        m.write(0x30000000+0xEC, struct.pack("<I", 0))\n'
            '        m.call(0x15FEE, (0x30000000, 0x30006000, 0, 0x30002000, 100, 0, 10000, 10000, 1))\n'
            '    assert base.read(0x30004000, 4) == candidate.read(0x30004000, 4), "the hook wrote outside its own memory"\n', encoding='utf-8')
        package = self.tmp/'breaks-package'
        build(mod, STOCK, package)
        report = check_candidate(package, mod, STOCK)
        self.assertEqual(states(report)['compatibility: mixer_output_unchanged'], 'fail', report['results'])


if __name__ == '__main__':
    unittest.main()
