"""The whole path on two different bases: check a hook, build, then compare base and candidate on the stand.

The oracle is the base image itself: the same native code with the same inputs, run unhooked.
RED: a corrupted displaced instruction, or a stub that skips them, must fail the comparison (test_comparison_catches_a_broken_stub).
"""
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from lab404.build import BuildError, build
from lab404.hooks import check_entry_hook, stub_source
from lab404.image import FLASH, Image, ImageError, scatter
from lab404.stand import Boundary, FIXTURE_BASE, Machine
from helpers import DOOM72, DOOM73, ROOT, STOCK

MOD = ROOT/'mods/demo_counter'
HELPER = 0x15FEE
STATE, SOURCE, DEST = FIXTURE_BASE, FIXTURE_BASE+0x2000, FIXTURE_BASE+0x4000
WORDS = 896


def run_helper(machine, mode, frame, route):
    """The stock stereo mix helper: state, destination, frame, source on registers, then 5 stacked arguments."""
    machine.write(STATE+0xEC, struct.pack('<I', mode))
    pcm = [v & 0xFFFFFFFF for f in range(64) for v in (1000+f*31, -2000-f*19)]
    machine.write(SOURCE, struct.pack('<128I', *pcm))
    machine.write(DEST, bytes(WORDS*4))
    machine.call(HELPER, (STATE, DEST, frame, SOURCE, 100, route, 10000, 10000, 1))
    return machine.read(DEST, WORDS*4)


CASES = [(mode, frame, route) for mode in (0, 0xD, 0x73) for frame in (0, 1, 31, 63) for route in (0, 1, 4, 6)]


@unittest.skipUnless(STOCK.exists() and DOOM73.exists(), 'firmware inputs not present')
class HookArguments(unittest.TestCase):
    def test_a_hook_sees_the_callers_arguments_and_they_reach_the_function_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d)/'mod'
            shutil.copytree(MOD, mod)
            (mod/'counter.c').write_text('volatile unsigned seen[4];\nvoid demo_counter_hook(unsigned a, unsigned b, unsigned c, unsigned e) { seen[0] = a; seen[1] = b; seen[2] = c; seen[3] = e; }\n', encoding='utf-8')
            manifest = build(mod, STOCK, Path(d)/'pkg')
            candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
        machine, plain = Machine(candidate), Machine(STOCK.read_bytes())
        out = run_helper(machine, 0, 1, 1)
        self.assertEqual(out, run_helper(plain, 0, 1, 1))
        seen = struct.unpack('<4I', machine.read(int(manifest['symbols']['seen'], 16), 16))
        self.assertEqual(seen, (STATE, DEST, 1, SOURCE))


@unittest.skipUnless(STOCK.exists() and DOOM73.exists(), 'firmware inputs not present')
class HooksPerBase(unittest.TestCase):
    def test_a_hook_applies_only_to_the_bases_it_names(self):
        with tempfile.TemporaryDirectory() as d:
            stock = build(ROOT/'mods/quick_system', STOCK, Path(d)/'stock')
            doom = build(ROOT/'mods/quick_system', DOOM73, Path(d)/'doom')
        self.assertEqual([h['address'] for h in stock['hooks']], ['0x800a80a8'])
        self.assertEqual([h['address'] for h in doom['hooks']], ['0x802097cc'])


@unittest.skipUnless(STOCK.exists() and DOOM73.exists(), 'firmware inputs not present')
class DemoMod(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='lab404-test-'))
        cls.built = {}
        for name, base in (('stock', STOCK), ('doom73', DOOM73)):
            manifest = build(MOD, base, cls.tmp/name)
            cls.built[name] = (base.read_bytes(), (cls.tmp/name/'SP404MKII_APP1.bin').read_bytes(), manifest)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_output_matches_base_and_counter_counts(self):
        for name, (base, candidate, manifest) in self.built.items():
            plain, modded = Machine(base), Machine(candidate)
            counter = int(manifest['symbols']['demo_counter_calls'], 16)
            self.assertEqual(modded.u32(counter), 0)
            nonzero = 0
            for mode, frame, route in CASES:
                a, b = run_helper(plain, mode, frame, route), run_helper(modded, mode, frame, route)
                self.assertEqual(a, b, (name, mode, frame, route))
                nonzero += any(a)
            self.assertEqual(nonzero, len(CASES), 'fixture produced silence: the comparison would be empty')
            self.assertEqual(modded.u32(counter), len(CASES), name)

    def test_comparison_catches_a_broken_stub(self):
        base, candidate, manifest = self.built['stock']
        # The second displaced instruction, ldr.w r0,[r0,#0xec], becomes nop.w inside the stub.
        displaced = bytes.fromhex(manifest['hooks'][0]['before'])
        at = candidate.index(displaced, len(base))
        broken = bytearray(candidate)
        broken[at+4:at+8] = bytes.fromhex('aff30080')
        plain, modded = Machine(base), Machine(bytes(broken))
        differs = False
        for mode, frame, route in CASES:
            good = run_helper(plain, mode, frame, route)  # the base itself must run clean
            try:
                differs |= good != run_helper(modded, mode, frame, route)
            except (Boundary, AssertionError):
                differs = True
        self.assertTrue(differs, 'a stub that skips an instruction went unnoticed')

    def test_only_declared_bytes_change(self):
        for base, candidate, manifest in self.built.values():
            changed = [i for i, (a, b) in enumerate(zip(base, candidate)) if a != b]
            hook = manifest['hooks'][0]
            where = next(load-FLASH+int(hook['address'], 16)-runtime for load, runtime, n, _ in scatter(base)
                         if runtime <= int(hook['address'], 16) < runtime+n)
            allowed = set(range(0x80, 0x88)) | set(range(where, where+len(bytes.fromhex(hook['before']))))
            self.assertTrue(set(changed) <= allowed, sorted(set(changed)-allowed)[:8])
            self.assertEqual(len(scatter(candidate)), len(scatter(base))+1)

    def test_build_is_reproducible(self):
        again = build(MOD, STOCK, self.tmp/'again')
        self.assertEqual(again['candidate_sha256'], self.built['stock'][2]['candidate_sha256'])

    def test_manifest_binds_candidate_to_its_parent_and_sources(self):
        base, candidate, manifest = self.built['doom73']
        from lab404.image import sha256
        self.assertEqual(manifest['candidate_sha256'], sha256(candidate))
        self.assertEqual(manifest['parent_sha256'], sha256(base))
        self.assertRegex(manifest['source_sha256'], r'^[0-9a-f]{64}$')
        self.assertIn('not proven on a unit', manifest['status'])


@unittest.skipUnless(STOCK.exists() and DOOM72.exists(), 'firmware inputs not present')
class Refusals(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='lab404-test-'))
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_refuses_a_base_the_mod_does_not_declare(self):
        with self.assertRaisesRegex(BuildError, 'no support'):
            build(MOD, DOOM72, self.tmp/'x')

    def test_refuses_an_unidentified_base(self):
        raw = bytearray(STOCK.read_bytes())
        raw[0x100000] ^= 1
        path = self.tmp/'changed.bin'
        path.write_bytes(raw)
        with self.assertRaisesRegex(BuildError, 'not identified'):
            build(MOD, path, self.tmp/'x')

    def test_refuses_to_replace_a_build(self):
        (self.tmp/'x').mkdir()
        with self.assertRaisesRegex(BuildError, 'new folder'):
            build(MOD, STOCK, self.tmp/'x')

    def test_refuses_an_oversized_payload(self):
        mod = self.tmp/'mod'
        shutil.copytree(MOD, mod)
        d = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
        d['payload']['max_size'] = '0x4'
        (mod/'mod.json').write_text(json.dumps(d), encoding='utf-8')
        with self.assertRaisesRegex(BuildError, 'limit'):
            build(mod, STOCK, self.tmp/'x')

    def test_refuses_a_payload_overlapping_firmware_memory(self):
        mod = self.tmp/'mod'
        shutil.copytree(MOD, mod)
        d = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
        d['payload']['address'] = '0x80000000'
        (mod/'mod.json').write_text(json.dumps(d), encoding='utf-8')
        with self.assertRaises(ValueError):
            build(mod, STOCK, self.tmp/'x')

    def test_compile_error_stops_the_build(self):
        mod = self.tmp/'mod'
        shutil.copytree(MOD, mod)
        (mod/'counter.c').write_text('this is not C', encoding='utf-8')
        with self.assertRaisesRegex(BuildError, 'compile failed'):
            build(mod, STOCK, self.tmp/'x')


@unittest.skipUnless(STOCK.exists(), 'firmware inputs not present')
class HookChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = Image.load(STOCK)

    def test_good_site(self):
        displaced, picked = check_entry_hook(self.image, HELPER)
        self.assertEqual(len(displaced), 12)
        self.assertEqual(len(picked), 3)

    def test_refuses_mid_function_site(self):
        with self.assertRaisesRegex(ImageError, 'function entry'):
            check_entry_hook(self.image, HELPER+4)

    def test_refuses_branch_into_replaced_bytes(self):
        # Synthetic function: push, then a target inside the span, reached by a later beq.
        code = bytes.fromhex('2de9f043')+bytes.fromhex('00bf00bf')+bytes.fromhex('00bf00bf')+bytes.fromhex('fad0')+bytes.fromhex('7047')
        raw = bytearray(STOCK.read_bytes())
        at = 0x15000-0x400+0xAF0  # file offset of runtime 0x15000 through the ITCM COPY row
        raw[at:at+len(code)] = code
        with self.assertRaisesRegex(ImageError, 'inside the bytes'):
            check_entry_hook(Image(bytes(raw)), 0x15000)

    def test_refuses_pc_relative_displacement(self):
        code = bytes.fromhex('2de9f043')+bytes.fromhex('dff80400')+bytes.fromhex('00bf00bf')
        raw = bytearray(STOCK.read_bytes())
        at = 0x15000-0x400+0xAF0
        raw[at:at+len(code)] = code
        with self.assertRaisesRegex(ImageError, 'depends on its address'):
            check_entry_hook(Image(bytes(raw)), 0x15000)

    def test_stub_keeps_displaced_bytes_verbatim(self):
        text = stub_source(0, 0x15FEE, 'f', b'\x01\x02')
        self.assertIn('.byte 0x01, 0x02', text)
        self.assertIn('0x00015FF1', text)


class Tools(unittest.TestCase):
    def test_compiler_present(self):
        self.assertEqual(subprocess.run(['clang', '--version'], capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
