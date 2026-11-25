"""Word hooks: a mod repoints one code pointer (a vector, a table entry, a vtable slot) at its own function.

Real mods need this beside entry hooks (docs/STATUS.md, "What to do next" 2). The design follows a private mod that used such
words on a unit: fault vectors, a vtable slot of the panel tick, a table of packet handlers. Each refusal here protects one way
a wrong word would break a unit without any sign in the build.
"""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from lab404.build import BuildError, build
from lab404.check import check_candidate
from lab404.hooks import check_word_hook
from lab404.image import Image, ImageError
from helpers import DOOM73, DOOM74, STOCK

STOCK_SHA = '4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80'
DOOM73_SHA = '6605af05e90578f179b5b528502aadef3b6b8497d87eaeecab6b9cf5185905aa'
TICK_SLOT, TICK = 0x8021D018, 0x80072CF1  # [BYTES] a vtable word holding the panel tick handler, the same on stock and DOOM OS 0.7.2-0.7.4
SOURCE = """
typedef void (*tick_fn)(void *, int, int, int);
extern void stock_tick(void *, int, int, int);
volatile unsigned word_hook_calls;
volatile unsigned word_hook_data;
void counted_tick(void *self, int a, int b, int c) { word_hook_calls++; stock_tick(self, a, b, c); }
tick_fn word_hook_original(void) { return stock_tick; }
"""


def mod_with(folder, hook, bases=(STOCK_SHA,)):
    folder = Path(folder)
    folder.mkdir()
    (folder/'tick.c').write_text(SOURCE, encoding='utf-8')
    spec = dict(name='word_hook_test', version='0', bases=list(bases), payload=dict(address='0x83FD0000', max_size='0x1000'),
                sources=['tick.c'], hooks=[dict(kind='word', function='counted_tick', **{'original': 'stock_tick', **hook})])
    (folder/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
    return folder


@unittest.skipUnless(STOCK.exists(), 'needs stock 5.52')
class WordHooks(unittest.TestCase):
    def test_a_good_word_is_repointed_and_the_original_stays_callable(self):
        with tempfile.TemporaryDirectory() as d:
            mod = mod_with(Path(d)/'mod', dict(address=hex(TICK_SLOT), expect=hex(TICK), original='stock_tick'))
            manifest = build(mod, STOCK, Path(d)/'pkg')
            candidate = Image((Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes())
            function = int(manifest['symbols']['counted_tick'], 16)
            self.assertEqual(manifest['symbols']['stock_tick'], hex(TICK))
            self.assertEqual(candidate.u32(TICK_SLOT), function)
            self.assertEqual(manifest['hooks'], [dict(address=hex(TICK_SLOT), before=struct.pack('<I', TICK).hex(), after=struct.pack('<I', function).hex())])
            got = {r['check']: r['state'] for r in check_candidate(Path(d)/'pkg', mod, STOCK)['results']}
            self.assertEqual([got[name] for name in ('scatter', 'allocation', 'hooks', 'loader-code', 'flash-room', 'undeclared-changes')], ['pass']*6)

    def test_the_word_must_hold_what_the_author_saw(self):
        with tempfile.TemporaryDirectory() as d:
            mod = mod_with(Path(d)/'mod', dict(address=hex(TICK_SLOT), expect=hex(TICK+2)))
            with self.assertRaisesRegex(ImageError, 'not the 0x80072CF3 the mod expects'):
                build(mod, STOCK, Path(d)/'pkg')

    def test_expect_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            mod = mod_with(Path(d)/'mod', dict(address=hex(TICK_SLOT)))
            with self.assertRaisesRegex(BuildError, 'needs "expect"'):
                build(mod, STOCK, Path(d)/'pkg')

    def test_the_function_must_be_code(self):
        with tempfile.TemporaryDirectory() as d:
            mod = mod_with(Path(d)/'mod', dict(address=hex(TICK_SLOT), expect=hex(TICK)))
            spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
            spec['hooks'][0]['function'] = 'word_hook_data'
            (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
            with self.assertRaisesRegex(BuildError, 'not a Thumb function'):
                build(mod, STOCK, Path(d)/'pkg')

    def test_a_word_twice_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            mod = mod_with(Path(d)/'mod', dict(address=hex(TICK_SLOT), expect=hex(TICK)))
            spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
            spec['hooks'].append(dict(spec['hooks'][0]))
            (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
            with self.assertRaisesRegex(BuildError, 'same word'):
                build(mod, STOCK, Path(d)/'pkg')

    def test_data_and_unaligned_words_are_refused(self):
        image = Image(STOCK.read_bytes())
        with self.assertRaisesRegex(ImageError, 'word-aligned'):
            check_word_hook(image, TICK_SLOT+2, 0)
        even = 0x60080080  # the scatter table bound: an even number, not a pointer to code
        with self.assertRaisesRegex(ImageError, 'not a Thumb code address'):
            check_word_hook(image, even, image.u32(even))

    def test_a_pointer_to_loader_erase_code_is_not_repointed(self):
        # [BYTES] stock 5.52: the service command table word 0x802098F8 holds 0x80065839, the command that erases the loader.
        image = Image(STOCK.read_bytes())
        self.assertEqual(image.u32(0x802098F8), 0x80065839)
        with self.assertRaisesRegex(ImageError, 'loader'):
            check_word_hook(image, 0x802098F8, 0x80065839)


@unittest.skipUnless(DOOM73.exists(), 'needs DOOM OS 0.7.3')
class OnDoomOs(unittest.TestCase):
    def test_a_doom_veneer_word_is_refused(self):
        # hk.doom.veneers-rewritten: DOOM OS points these words into RAM while it starts. The LOAD veneer is 0x802098A0.
        image = Image(DOOM73.read_bytes())
        value = image.u32(0x802098A4)
        with self.assertRaisesRegex(ImageError, 'DOOM OS rewrites'):
            check_word_hook(image, 0x802098A4, value, 'doom-os')

    def test_the_same_tick_slot_builds_on_doom_os(self):
        bases = [(DOOM73, DOOM73_SHA)]+([(DOOM74, 'aaec78ada566ba8aa59602694984ca6fbb229baa1dbcaefac813430da49bbada')] if DOOM74.exists() else [])
        for path, sha in bases:
            with tempfile.TemporaryDirectory() as d:
                mod = mod_with(Path(d)/'mod', dict(address=hex(TICK_SLOT), expect=hex(TICK), original='stock_tick'), bases=(sha,))
                manifest = build(mod, path, Path(d)/'pkg')
                self.assertEqual(Image((Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()).u32(TICK_SLOT), int(manifest['symbols']['counted_tick'], 16))


if __name__ == '__main__':
    unittest.main()
