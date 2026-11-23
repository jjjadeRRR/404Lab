"""Disable hooks: a mod may make a guarded factory service routine return at once, and nothing else in guarded code.

The maintainer decided on 2026-11-23 to allow this. The four service entry points can erase the loader (hw.service.loader-erase);
`movs r0,#0; bx lr` at their entry takes that way away. The private mod this follows has carried exactly these four patches
since 2026-11-11 and runs on the owner's unit. Each refusal here keeps the change from growing into an edit of guarded code.
"""
import json
import tempfile
import unittest
from pathlib import Path

from lab404.build import BuildError, build
from lab404.check import check_candidate
from lab404.hooks import check_disable_hook
from lab404.image import DISABLEABLE, Image, ImageError, file_offset
from helpers import DOOM73, DOOM74, ROOT, STOCK

STOCK_SHA = '4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80'
DOOM73_SHA = '6605af05e90578f179b5b528502aadef3b6b8497d87eaeecab6b9cf5185905aa'
DOOM74_SHA = 'aaec78ada566ba8aa59602694984ca6fbb229baa1dbcaefac813430da49bbada'


def mod_with(folder, hooks):
    folder = Path(folder)
    folder.mkdir()
    (folder/'empty.c').write_text('volatile unsigned disable_test_word;\n', encoding='utf-8')
    spec = dict(name='disable_test', version='0', bases=[STOCK_SHA, DOOM73_SHA, DOOM74_SHA], payload=dict(address='0x83FD0000', max_size='0x100'),
                sources=['empty.c'], hooks=hooks)
    (folder/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
    return folder


@unittest.skipUnless(STOCK.exists(), 'stock-5.52 input needed')
class DisableHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lab404-disable-')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_four_switched_off_on_every_base_and_check_passes(self):
        hooks = [dict(kind='disable', address=hex(a)) for a in DISABLEABLE]
        mod = mod_with(self.root/'mod', hooks)
        for name, base in (('stock', STOCK), ('doom73', DOOM73), ('doom74', DOOM74)):
            if not base.exists():
                continue
            out = self.root/name
            manifest = build(mod, base, out)
            raw = (out/'SP404MKII_APP1.bin').read_bytes()
            for address in DISABLEABLE:
                at = file_offset(raw, address, 4)
                self.assertEqual(raw[at:at+4].hex(), '00207047', (name, hex(address)))
                self.assertIn(dict(address=hex(address), before=base.read_bytes()[at:at+4].hex(), after='00207047'), manifest['hooks'])
            report = check_candidate(out, mod, base)
            got = {r['check']: r for r in report['results']}
            self.assertEqual((got['hooks']['state'], got['undeclared-changes']['state'], got['loader-code']['state']), ('pass', 'pass', 'pass'), name)

    def test_only_the_four_entries(self):
        image = Image(STOCK.read_bytes())
        for address in (0x8019D348, 0x8001ACB0, 0x800D5FD8, 0x8006583A, 0x80065840, 0x800A80A8):
            with self.assertRaises(ImageError, msg=hex(address)):
                check_disable_hook(image, address)

    def test_twice_is_refused(self):
        mod = mod_with(self.root/'mod', [dict(kind='disable', address='0x80065838'), dict(kind='disable', address='0x80065838')])
        with self.assertRaisesRegex(BuildError, 'twice'):
            build(mod, STOCK, self.root/'out')

    def test_an_image_without_the_guarded_bytes_is_refused(self):
        raw = bytearray(STOCK.read_bytes())
        at = file_offset(bytes(raw), 0x80065838, 8)
        raw[at] ^= 0xFF
        with self.assertRaisesRegex(ImageError, 'does not hold the guarded routine'):
            check_disable_hook(Image(bytes(raw)), 0x80065838)

    def test_an_entry_or_word_hook_there_is_still_refused(self):
        for hook in (dict(kind='entry', address='0x80065838', function='disable_test_word'),
                     dict(kind='word', address='0x80065838', expect='0x0', function='disable_test_word')):
            mod = mod_with(self.root/hook['kind'], [hook])
            with self.assertRaises((BuildError, ImageError)):
                build(mod, STOCK, self.root/(hook['kind']+'-out'))


if __name__ == '__main__':
    unittest.main()
