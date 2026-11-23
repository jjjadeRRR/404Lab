"""Copies of stock functions and a block in flash: the last two things the private mod's own builder did that these tools did not.

The copy follows the private mod's AUTO MARK work (hk.recipe.automark-32): the stock TRANSIENT analysis is taken from the image,
checked by SHA-256, and changed only where it stops at 16 marks. The flash block follows its screensaver, which runs in place in
flash after the image (hk.region.flash).
"""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

import capstone

from lab404.build import BuildError, build
from lab404.check import check_candidate
from lab404.copy import plan_copy
from lab404.image import Image, ImageError, file_offset
from lab404.stand import Machine
from helpers import DOOM74, STOCK

STOCK_SHA = '4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80'
DOOM74_SHA = 'aaec78ada566ba8aa59602694984ca6fbb229baa1dbcaefac813430da49bbada'
TRANSIENT = (0x8017C138, 0x8017C768, 'f51213adc4705fe610265b7f7aa89aecb3e7919461e5f0b5968711c9b49648ac')  # [BYTES] the same on stock and DOOM OS 0.7.4
LEVEL = (0x8017BC48, 0x8017BF06, 'a51594cdffa6ec32cb8639417a3c20b845e503323d6804df49dbe7f54029e75d')
EDITS = [dict(address='0x8017C186', before='4021', after='8021', about='the 0xFF fill of the list: 0x40 -> 0x80 bytes'),
         dict(address='0x8017C368', before='b9f10f0f', after='b9f11f0f', about='cmp.w sb,#0xf -> #0x1f'),
         dict(address='0x8017C500', before='b9f10f0f', after='b9f11f0f', about='cmp.w sb,#0xf -> #0x1f'),
         dict(address='0x8017C17C', before='48f6e018', movw='am_list', about='movw r8: the list, now the mod\'s'),
         dict(address='0x8017C182', before='c8f20038', movt='am_list', about='movt r8')]
SOURCE = """
unsigned am_list[32];
void level_block(void) {}
extern int flash_answer(void);
extern const unsigned char art[];
int payload_calls(void) { return flash_answer()+art[1]; }
"""
FLASH_SOURCE = """
extern unsigned am_list[32];
int flash_answer(void) { return 40+(am_list[0] == 0); }
"""


def mod_with(folder, copies=(), flash=False, flash_address='0x603C0000'):
    folder = Path(folder)
    folder.mkdir()
    (folder/'mod.c').write_text(SOURCE if flash else SOURCE.split('extern int flash_answer')[0], encoding='utf-8')
    spec = dict(name='copy_test', version='0', bases=[STOCK_SHA, DOOM74_SHA], payload=dict(address='0x83FD0000', max_size='0x2000'),
                sources=['mod.c'], copies=list(copies))
    if flash:
        (folder/'flash.c').write_text(FLASH_SOURCE, encoding='utf-8')
        (folder/'art.bin').write_bytes(bytes([0, 2, 3, 4]))
        spec['flash'] = dict(address=flash_address, max_size='0x1000', sources=['flash.c'], data=[dict(file='art.bin', symbol='art')])
    (folder/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
    return folder


def transient(**more):
    return {'name': 'transient32', 'from': hex(TRANSIENT[0]), 'to': hex(TRANSIENT[1]), 'sha256': TRANSIENT[2], 'edits': EDITS, **more}


def level():
    return dict(name='level32', **{'from': hex(LEVEL[0]), 'to': hex(LEVEL[1])}, sha256=LEVEL[2], redirect={'0x8017BA38': 'level_block'})


@unittest.skipUnless(STOCK.exists(), 'stock-5.52 input needed')
class Copies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lab404-copy-')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def built(self, base=STOCK):
        mod = mod_with(self.root/'mod', [transient(), level()])
        manifest = build(mod, base, self.root/'out')
        return mod, manifest, (self.root/'out/SP404MKII_APP1.bin').read_bytes()

    def test_a_copy_is_the_stock_code_with_only_its_edits_and_its_branches_out_aimed_again(self):
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
        md.detail = True
        for base in (STOCK, DOOM74):
            if not base.exists():
                continue
            mod, manifest, raw = self.built(base)
            symbols = {k: int(v, 16) for k, v in manifest['symbols'].items()}
            image, original = Image(raw), Image(base.read_bytes())
            for name, (start, end, _), redirect in (('transient32', TRANSIENT, {}), ('level32', LEVEL, {0x8017BA38: symbols['level_block']})):
                placed = symbols[name] & ~1
                self.assertEqual((placed-start) % 4, 0, name)
                old, new = original.read(start, end-start), image.read(placed, end-start)
                edited = {int(e['address'], 16)-start+k for e in (EDITS if name == 'transient32' else []) for k in range(len(bytes.fromhex(e['before'])))}
                plan = plan_copy(original, transient() if name == 'transient32' else level())
                aimed = {offset+k: target for offset, size, target in plan['leaving'] for k in range(size)}
                for k in range(len(old)):
                    if k not in edited and k not in aimed:
                        self.assertEqual(old[k], new[k], f'{name} +0x{k:X}')
                for offset, size, target in plan['leaving']:
                    ins = next(md.disasm(new[offset:offset+size], placed+offset))
                    veneer = ins.operands[-1].imm & 0xFFFFFFFF
                    self.assertGreaterEqual(veneer, placed+len(old), name)
                    self.assertEqual(image.read(veneer, 4).hex(), 'dff800f0')
                    self.assertEqual(image.u32(veneer+4), redirect.get(target, target | 1), (name, hex(target)))
            t = symbols['transient32'] & ~1
            self.assertEqual(image.read(t+0x8017C368-TRANSIENT[0], 4).hex(), 'b9f11f0f')
            movw, movt = (struct.unpack('<2H', image.read(t+a-TRANSIENT[0], 4)) for a in (0x8017C17C, 0x8017C182))
            def imm(hw1, hw2):
                return (((hw1 & 0xF) << 12) | (((hw1 >> 10) & 1) << 11) | (((hw2 >> 12) & 7) << 8) | (hw2 & 0xFF), (hw2 >> 8) & 0xF)
            self.assertEqual((imm(*movw)[0] | imm(*movt)[0] << 16, imm(*movw)[1], imm(*movt)[1]), (symbols['am_list'], 8, 8))
            got = {r['check']: r['state'] for r in check_candidate(self.root/'out', mod, base)['results']}
            self.assertEqual((got['hooks'], got['undeclared-changes'], got['loader-code']), ('pass', 'pass', 'pass'))
            self.tmp.cleanup()
            self.tmp = tempfile.TemporaryDirectory(prefix='lab404-copy-')
            self.root = Path(self.tmp.name)

    def test_a_copy_is_refused_when_the_bytes_or_its_shape_are_not_as_declared(self):
        image = Image(STOCK.read_bytes())
        with self.assertRaisesRegex(ImageError, 'not the ones declared'):
            plan_copy(image, transient(sha256='0'*64))
        with self.assertRaisesRegex(ImageError, 'does not hold'):
            plan_copy(image, dict(transient(), edits=[dict(address='0x8017C368', before='00000000', after='11111111')]))
        with self.assertRaisesRegex(ImageError, 'nothing in the copy branches'):
            plan_copy(image, dict(transient(), redirect={'0x80000000': 'level_block'}))
        guarded = image.read(0x80065838, 0x20)
        with self.assertRaisesRegex(ImageError, 'erase the loader'):
            plan_copy(image, dict(name='bad', **{'from': '0x80065838', 'to': '0x80065858'}, sha256=hashlib.sha256(guarded).hexdigest()))

    def test_a_literal_outside_the_copy_is_refused(self):
        image = Image(STOCK.read_bytes())
        # The first half of TRANSIENT alone: whatever it loads relative to PC from the second half is outside.
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
        cut = None
        for ins in md.disasm(image.read(TRANSIENT[0], TRANSIENT[1]-TRANSIENT[0]), TRANSIENT[0]):
            if '[pc' in ins.op_str:
                cut = ins.address+ins.size
                break
        if cut is None:
            self.skipTest('no PC-relative load in this function')
        code = image.read(TRANSIENT[0], cut-TRANSIENT[0])
        with self.assertRaisesRegex(ImageError, 'outside the copy'):
            plan_copy(image, dict(name='half', **{'from': hex(TRANSIENT[0]), 'to': hex(cut)}, sha256=hashlib.sha256(code).hexdigest()))


@unittest.skipUnless(STOCK.exists(), 'stock-5.52 input needed')
class FlashBlock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lab404-flash-')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_code_and_data_in_flash_run_in_place_and_reach_the_payload_both_ways(self):
        mod = mod_with(self.root/'mod', flash=True)
        manifest = build(mod, STOCK, self.root/'out')
        raw = (self.root/'out/SP404MKII_APP1.bin').read_bytes()
        symbols = {k: int(v, 16) for k, v in manifest['symbols'].items()}
        self.assertEqual(manifest['flash']['address'], '0x603c0000')
        self.assertTrue(0x603C0000 <= symbols['flash_answer'] < 0x603C1000 and 0x603C0000 <= symbols['art'] < 0x603C1000)
        at = file_offset(raw, 0x603C0000, manifest['flash']['bytes'])
        self.assertEqual(hashlib.sha256(raw[at:at+manifest['flash']['bytes']]).hexdigest(), manifest['flash']['sha256'])
        machine = Machine(raw)
        self.assertEqual(machine.call(symbols['payload_calls']), 41+2)  # payload -> flash -> payload data, and flash data
        report = check_candidate(self.root/'out', mod, STOCK)
        got = {r['check']: r['state'] for r in report['results']}
        self.assertEqual((got['flash-block'], got['undeclared-changes'], got['flash-room']), ('pass', 'pass', 'pass'))

    def test_a_flash_block_must_lie_after_the_image(self):
        mod = mod_with(self.root/'mod', flash=True, flash_address='0x60200000')
        with self.assertRaisesRegex(ImageError, 'after the image'):
            build(mod, STOCK, self.root/'out')

    def test_a_changed_flash_block_is_caught(self):
        mod = mod_with(self.root/'mod', flash=True)
        manifest = build(mod, STOCK, self.root/'out')
        path = self.root/'out/SP404MKII_APP1.bin'
        raw = bytearray(path.read_bytes())
        raw[0x603C0000-0x60080000] ^= 1
        path.write_bytes(raw)
        manifest['candidate_sha256'] = hashlib.sha256(bytes(raw)).hexdigest()
        (self.root/'out/manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        got = {r['check']: r['state'] for r in check_candidate(self.root/'out', mod, STOCK)['results']}
        self.assertEqual(got['flash-block'], 'fail')


if __name__ == '__main__':
    unittest.main()
