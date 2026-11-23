"""Jump hooks and byte patches: the two kinds a larger mod needs beside entry and word hooks.

The maintainer's private mod uses both on a unit: jumps where its code takes over a piece of a stock function (the mute group
screen, the audio voice site), and byte patches for limits and immediates (the mute group limit of 16 raised to 32,
hk.recipe.mute-32). Each refusal here keeps a patch from reaching guarded code or a word DOOM OS rewrites.
"""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from lab404.build import BuildError, build
from lab404.check import check_candidate
from lab404.hooks import check_byte_patch, check_jump_hook
from lab404.image import Image, ImageError, file_offset
from helpers import DOOM73, DOOM74, STOCK

STOCK_SHA = '4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80'
DOOM73_SHA = '6605af05e90578f179b5b528502aadef3b6b8497d87eaeecab6b9cf5185905aa'
DOOM74_SHA = 'aaec78ada566ba8aa59602694984ca6fbb229baa1dbcaefac813430da49bbada'
MUTE_LIMIT = 0x80115666     # [BYTES] cmp r6,#16 in the MUTE GROUP add handler (st.mute.groups), the same on every base
MUTE_DRAW = 0x80115334      # [BYTES] inside the member draw loop of the MUTE GROUP screen (st.mute.screen)
SOURCE = """
extern void after_draw(void);
volatile unsigned jump_test_word;
__attribute__((naked)) void draw_page(void) { __asm__ volatile("b after_draw"); }
"""


def mod_with(folder, hooks, source=SOURCE):
    folder = Path(folder)
    folder.mkdir()
    (folder/'mod.c').write_text(source, encoding='utf-8')
    spec = dict(name='jump_patch_test', version='0', bases=[STOCK_SHA, DOOM73_SHA, DOOM74_SHA], payload=dict(address='0x83FD0000', max_size='0x400'),
                sources=['mod.c'], hooks=hooks)
    (folder/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
    return folder


@unittest.skipUnless(STOCK.exists(), 'stock-5.52 input needed')
class ByteAndJump(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lab404-jump-')
        self.root = Path(self.tmp.name)
        self.image = Image(STOCK.read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def hooks(self):
        return [dict(kind='patch', address=hex(MUTE_LIMIT), before='102e', after='202e', about='cmp r6,#16 -> #32'),
                dict(kind='jump', address=hex(MUTE_DRAW), function='draw_page', resume='after_draw')]

    def test_the_private_mods_mute_patches_build_and_check_on_every_base(self):
        mod = mod_with(self.root/'mod', self.hooks())
        for name, base in (('stock', STOCK), ('doom73', DOOM73), ('doom74', DOOM74)):
            if not base.exists():
                continue
            out = self.root/name
            manifest = build(mod, base, out)
            raw = (out/'SP404MKII_APP1.bin').read_bytes()
            at = file_offset(raw, MUTE_LIMIT, 2)
            self.assertEqual(raw[at:at+2].hex(), '202e', name)
            hooks = {int(h['address'], 16): h for h in manifest['hooks']}
            jump = hooks[MUTE_DRAW]
            draw = int(manifest['symbols']['draw_page'], 16)
            self.assertEqual(bytes.fromhex(jump['after'])[:8], bytes.fromhex('dff800f0')+struct.pack('<I', draw | 1))
            self.assertEqual(len(jump['before']), len(jump['after']))
            self.assertEqual(int(manifest['symbols']['after_draw'], 16), (MUTE_DRAW+len(bytes.fromhex(jump['before']))) | 1)
            got = {r['check']: r['state'] for r in check_candidate(out, mod, base)['results']}
            self.assertEqual((got['hooks'], got['undeclared-changes'], got['loader-code']), ('pass', 'pass', 'pass'), name)

    def test_a_patch_must_match_the_image(self):
        with self.assertRaisesRegex(ImageError, 'does not hold'):
            check_byte_patch(self.image, MUTE_LIMIT, bytes.fromhex('112e'), bytes.fromhex('202e'))
        with self.assertRaisesRegex(ImageError, 'keeps its size'):
            check_byte_patch(self.image, MUTE_LIMIT, bytes.fromhex('102e'), bytes.fromhex('202e00'))
        with self.assertRaisesRegex(ImageError, 'changes nothing'):
            check_byte_patch(self.image, MUTE_LIMIT, bytes.fromhex('102e'), bytes.fromhex('102e'))

    def test_a_patch_may_not_touch_or_reach_guarded_code(self):
        guarded = self.image.read(0x80065838, 4)
        with self.assertRaisesRegex(ImageError, 'disable hook'):
            check_byte_patch(self.image, 0x80065838, guarded, bytes.fromhex('fee7fee7'))
        # A call into guarded code written over the first instructions of the key handler.
        at, target = 0x800A80A8, 0x80065838
        off = target-(at+4)
        s, i1, i2 = (off >> 24) & 1, (off >> 23) & 1, (off >> 22) & 1
        bl = struct.pack('<2H', 0xF000 | (s << 10) | ((off >> 12) & 0x3FF), 0xD000 | ((~(i1 ^ s) & 1) << 13) | ((~(i2 ^ s) & 1) << 11) | ((off >> 1) & 0x7FF))
        with self.assertRaisesRegex(ImageError, 'branch into'):
            check_byte_patch(self.image, at, self.image.read(at, 4), bl)
        word = 0x8021D018  # a vtable word (hk.site.tick)
        with self.assertRaisesRegex(ImageError, 'pointer to'):
            check_byte_patch(self.image, word, self.image.read(word, 4), struct.pack('<I', 0x80065839))

    @unittest.skipUnless(DOOM73.exists(), 'DOOM OS 0.7.3 input needed')
    def test_a_doom_veneer_word_is_refused(self):
        image = Image(DOOM73.read_bytes())
        word = 0x802098A4  # the LOAD veneer word, rewritten by DOOM OS while it starts (hk.doom.veneers-rewritten)
        with self.assertRaisesRegex(ImageError, 'veneer word'):
            check_byte_patch(image, word, image.read(word, 4), struct.pack('<I', 0x83FD0001), 'doom-os')

    def test_a_jump_may_not_be_placed_where_code_lands_inside_it_or_in_guarded_code(self):
        with self.assertRaises(ImageError):
            check_jump_hook(self.image, 0x80065838)
        with self.assertRaises(ImageError):
            check_jump_hook(self.image, 0x8006583C)
        with self.assertRaisesRegex(ImageError, 'even'):
            check_jump_hook(self.image, MUTE_DRAW+1)

    def test_a_jump_to_something_the_mod_does_not_define_is_refused(self):
        hooks = [dict(kind='jump', address=hex(MUTE_DRAW), function='jump_test_word', resume='after_draw')]
        mod = mod_with(self.root/'data', hooks)
        with self.assertRaisesRegex(BuildError, 'not a Thumb function'):
            build(mod, STOCK, self.root/'out')


if __name__ == '__main__':
    unittest.main()
