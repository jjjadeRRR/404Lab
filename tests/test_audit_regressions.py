"""Regressions on public fixtures for the linker, evidence and candidate checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from helpers import ROOT, tiny_image
from lab404 import check, identify, pipeline
from lab404.__main__ import main
from lab404.build import BuildError, build, compile_regions
from lab404.image import sha256
from lab404.observe import classify, record_sweep

BASE = 0x83FD0000


class Audit(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.mod = self.root/'mod'
        self.mod.mkdir()

    def compile(self, sources, **options):
        return compile_regions(self.mod, dict(sources=sources), BASE, [], {}, **options)

    def test_float_calling_convention(self):
        (self.mod/'gain.c').write_text('float gain(float x){return x*0.5f;}', encoding='utf-8')
        with self.assertRaisesRegex(BuildError, 'hard'):
            self.compile([dict(file='gain.c', flags=['-mfpu=fpv5-sp-d16', '-mfloat-abi=hard'])])

    def test_flash_rejects_data_and_bss(self):
        for initializer in ('', '=1'):
            (self.mod/'count.c').write_text(f'volatile int counter{initializer};', encoding='utf-8')
            with self.subTest(initializer=initializer), self.assertRaisesRegex(BuildError, 'writable'):
                self.compile([], flash=dict(address=0x60081000, sources=['count.c']))

    def test_fixed_data_alignment(self):
        (self.mod/'table').write_bytes(b'1234')
        data = dict(file='table', symbol='table', address=BASE+2, align=16)
        with self.assertRaisesRegex(BuildError, 'align'):
            compile_regions(self.mod, dict(sources=[], data=[data]), BASE, [], {})

    def test_external_source_and_header(self):
        raw = tiny_image()
        base = self.root/'base.bin'
        base.write_bytes(raw)
        entry = dict(family='stock', version='5.52', source='public synthetic fixture', sha256=sha256(raw))
        header = self.root/'common.h'
        header.write_text('#define VALUE 17', encoding='utf-8')
        (self.root/'outer.c').write_text('#include "common.h"\nint value = VALUE;', encoding='utf-8')
        spec = dict(name='fixture', bases=[entry['sha256']], payload=dict(address=hex(BASE), max_size=256),
                    sources=['../outer.c'])
        (self.mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
        candidate = self.root/'candidate'
        with patch.object(identify, 'TABLE', [entry]), patch.object(check, 'TABLE', [entry]):
            manifest = build(self.mod, base, candidate)
            self.assertEqual(manifest['external_source_inputs'], ['../common.h', '../outer.c'])
            self.assertEqual(check.check_candidate(candidate, self.mod, base)['overall'], 'unknown')
            for edit in (lambda: header.write_text('#define VALUE 29', encoding='utf-8'), header.unlink):
                edit()
                result = check.check_candidate(candidate, self.mod, base)
                self.assertIn(('sources', 'fail'), [(r['check'], r['state']) for r in result['results']])

    def test_assembly_can_use_tracked_headers_and_plain_sources(self):
        (self.mod/'a header.h').write_text('#define VALUE 7\n', encoding='utf-8')
        (self.mod/'plain.s').write_text('.text\n.word 3\n', encoding='utf-8')
        (self.mod/'macro.S').write_text('#include "a header.h"\n.text\n.word VALUE\n', encoding='utf-8')
        (blobs, _), _ = self.compile(['plain.s', 'macro.S'])
        self.assertEqual(blobs, b'\x03\0\0\0\x07\0\0\0')

    def test_assembler_file_directives_report_the_supported_alternative(self):
        (self.mod/'file.s').write_text('.incbin "../outside"\n', encoding='utf-8')
        with self.assertRaisesRegex(BuildError, 'declare binary files in mod data'):
            self.compile(['file.s'])

    def test_payload_metadata(self):
        raw = tiny_image()
        base = self.root/'base.bin'
        base.write_bytes(raw)
        entry = dict(family='stock', version='5.52', source='public synthetic fixture', sha256=sha256(raw))
        spec = dict(name='fixture', bases=[entry['sha256']], payload=dict(address=hex(BASE), max_size=256),
                    sources=['entry.c'])
        (self.mod/'entry.c').write_text('int entry(void) { return 42; }', encoding='utf-8')
        (self.mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
        candidate = self.root/'candidate'
        with patch.object(identify, 'TABLE', [entry]), patch.object(check, 'TABLE', [entry]):
            manifest = build(self.mod, base, candidate)
            manifest_path = candidate/'manifest.json'
            original = check.check_candidate(candidate, self.mod, base)
            self.assertIn(('payload', 'pass'), [(r['check'], r['state']) for r in original['results']])
            payload = manifest['payload']
            for field, bad in [('sha256', '0'*64), ('address', hex(BASE+4)), ('bytes', payload['bytes']+4)]:
                with self.subTest(field=field):
                    changed = {**manifest, 'payload': {**payload, field: bad}}
                    manifest_path.write_text(json.dumps(changed), encoding='utf-8')
                    report = check.check_candidate(candidate, self.mod, base)
                    self.assertEqual(report['overall'], 'fail')
                    self.assertIn(('payload', 'fail'), [(r['check'], r['state']) for r in report['results']])

    def test_wrong_sweep_profile_preserves_knowledge(self):
        (self.root/'bindings').mkdir()
        path = self.root/'bindings/stock-5.52.json'
        path.write_text('{"bindings":[]}', encoding='utf-8')
        log = self.root/'log'
        log.write_text('{"experiment":{"firmware":"doom-os-0.7.3"}}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'firmware'):
            record_sweep('stock-5.52', [log], self.root)
        self.assertEqual(path.read_bytes(), b'{"bindings":[]}')

    def test_confirmation_requires_verified_start_and_control(self):
        good = dict(state='observed', arrived='arrived', settled=True, frame='same')
        for field in (dict(arrived='unknown'), dict(settled=False)):
            for record, control in (({**good, **field}, good), (good, {**good, **field})):
                self.assertEqual(classify(record, control, None)[0], 'unobserved')

    def test_optimized_scenarios_cannot_pass(self):
        (self.mod/'scenarios.py').write_text('def verify(a,b):\n assert False\n return 1\n', encoding='utf-8')
        script = """from lab404.check import check_scenarios
from helpers import tiny_image
import sys
print(check_scenarios(sys.argv[1], {'scenarios':['verify']}, tiny_image(), tiny_image())[0]['state'])"""
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (ROOT, ROOT/'tests'))))
        result = subprocess.run([sys.executable, '-O', '-c', script, str(self.mod)], env=env,
                                capture_output=True, encoding='utf-8', check=True)
        self.assertEqual(result.stdout.strip(), 'fail')

    def test_no_byte_checks_is_unknown(self):
        raw = tiny_image()
        base = self.root/'fixture'
        base.write_bytes(raw)
        entry = dict(family='stock', version='5.50', sha256=sha256(raw))
        with patch.object(identify, 'TABLE', [entry]):
            self.assertEqual(main(['verify-knowledge', str(base)]), 3)

    def test_sweep_refuses_an_image_for_another_profile_before_boot(self):
        raw = tiny_image()
        base = self.root/'fixture'
        base.write_bytes(raw)
        entry = dict(family='stock', version='5.50', sha256=sha256(raw))
        log = self.root/'log'
        with patch.object(identify, 'TABLE', [entry]):
            self.assertEqual(main(['sweep', 'stock-5.52', str(base), str(log)]), 2)
        self.assertFalse(log.exists())

    def test_unused_on_base_requires_expected_page(self):
        with patch.object(pipeline, 'Emulator'), patch.object(pipeline, 'Watcher') as watcher, patch.object(pipeline, 'do_step'):
            watcher.return_value.look.return_value.page = 1
            result = pipeline._unused_on_base(dict(screen='pitch-speed', keys=['ROLL']), b'', None, 'stock-5.52')
        self.assertEqual(result['state'], 'unknown')

    def test_package_matches_demonstrations_by_screen_keys_and_gesture(self):
        binding = dict(screen='pitch-speed', keys=['ROLL'], gesture='hold')
        for change in (dict(screen='sample'), dict(gesture='press')):
            with self.subTest(change=change):
                spec = dict(task=dict(unit_checks=['check result']),
                            adds=dict(bindings=[binding], demonstrate=[{**binding, **change, 'page': 53}]))
                (self.mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
                approval = dict(interface_sha256=pipeline.interface_digest(spec))
                (self.mod/'approval.json').write_text(json.dumps(approval), encoding='utf-8')
                with patch.object(pipeline, 'build') as build:
                    with self.assertRaisesRegex(pipeline.PackageRefused, 'screen, keys and gesture'):
                        pipeline.package(self.mod, self.root/'base', self.root/'out')
                    build.assert_not_called()
