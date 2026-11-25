"""Fixed places and per-source options: what a mod written with literal addresses between its modules needs.

The maintainer's private mod lays out about twenty modules at fixed offsets in its payload, some with FPU code for audio, and
reaches several of them by literal address. These tests build such a layout with lab404 build.
"""
import json
import tempfile
import unittest
from pathlib import Path

from lab404.build import BuildError, build
from lab404.stand import Machine
from helpers import STOCK

STOCK_SHA = '4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80'
FIXED = """
int fixed_entry(int x) { return x*3; }
"""
FLOAT = """
float fpu_gain(float x) { return x*0.5f; }
int fpu_entry(int x) { return (int)fpu_gain((float)x); }
"""
CALLER = """
int caller(int x) { return ((int (*)(int))0x83FD1001)(x)+1; }  /* reaches fixed_entry by its literal address */
"""


def mod_with(folder, sources, data=None):
    folder = Path(folder)
    folder.mkdir()
    for name, text in (('fixed.c', FIXED), ('float.c', FLOAT), ('caller.c', CALLER)):
        (folder/name).write_text(text, encoding='utf-8')
    (folder/'table.bin').write_bytes(bytes(range(1, 17)))
    spec = dict(name='fixed_test', version='0', bases=[STOCK_SHA], payload=dict(address='0x83FD0000', max_size='0x3000'), sources=sources)
    if data:
        spec['data'] = data
    (folder/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
    return folder


@unittest.skipUnless(STOCK.exists(), 'stock-5.52 input needed')
class FixedPlaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lab404-fixed-')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_modules_at_fixed_places_with_their_own_options_run(self):
        sources = ['caller.c', dict(file='fixed.c', address='0x83FD1000', max_size='0x100'),
                   dict(file='float.c', address='0x83FD0000', flags=['-O3', '-mfpu=fpv5-sp-d16', '-mfloat-abi=softfp'])]
        data = [dict(file='table.bin', symbol='table', address='0x83FD2000')]
        manifest = build(mod_with(self.root/'mod', sources, data), STOCK, self.root/'out')
        symbols = {k: int(v, 16) for k, v in manifest['symbols'].items()}
        self.assertEqual(symbols['fixed_entry'], 0x83FD1001)
        self.assertEqual(symbols['fpu_entry'] & ~1 & ~0xFFF, 0x83FD0000)
        self.assertEqual(symbols['table'], 0x83FD2000)
        machine = Machine((self.root/'out/SP404MKII_APP1.bin').read_bytes())
        self.assertEqual(machine.call(symbols['caller'], (5,)), 16)
        self.assertEqual(machine.read(0x83FD2000, 16), bytes(range(1, 17)))
        machine.m.reg_write(__import__('unicorn').arm_const.UC_ARM_REG_FPEXC, 0x40000000)  # the firmware has the FPU on
        self.assertEqual(machine.call(symbols['fpu_entry'], (10,)), 5)

    def test_overlapping_fixed_places_and_too_big_modules_are_refused(self):
        sources = [dict(file='fixed.c', address='0x83FD1000'), dict(file='caller.c', address='0x83FD1004')]
        with self.assertRaisesRegex(BuildError, 'overlaps'):
            build(mod_with(self.root/'a', sources), STOCK, self.root/'a-out')
        sources = [dict(file='float.c', address='0x83FD0000', max_size='0x4', flags=['-mfpu=fpv5-sp-d16', '-mfloat-abi=softfp'])]
        with self.assertRaisesRegex(BuildError, 'more than its max_size'):
            build(mod_with(self.root/'b', sources), STOCK, self.root/'b-out')

    def test_only_known_compiler_options(self):
        with self.assertRaisesRegex(BuildError, 'not one a mod may set'):
            build(mod_with(self.root/'c', [dict(file='fixed.c', flags=['-fplugin=evil.so'])]), STOCK, self.root/'c-out')


if __name__ == '__main__':
    unittest.main()
