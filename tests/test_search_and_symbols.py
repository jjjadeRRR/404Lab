"""Finding who uses an address, finding bytes, and tying a firmware function's address to the bytes expected there.

Oracles: Capstone decodes each reported branch independently, and the count of handler pointers is the one recorded in the knowledge base.
"""
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import capstone

from lab404.build import BuildError, build
from lab404.image import Image
from lab404.search import find_bytes, xrefs
from helpers import COPY, DOOM73, FLASH, ROOT, STOCK, rows_image

MOD = ROOT/'mods/quick_system'
KEY_HANDLER = 0x800A80A8  # [BYTES] st.input.handler: 98 data words hold its address
REQUEST_PAGE = 0x800DA598


def bl(source, target):
    """Encode a Thumb BL from source to target."""
    offset = target-(source+4)
    s = (offset >> 24) & 1
    i1, i2 = (offset >> 23) & 1, (offset >> 22) & 1
    j1, j2 = (i1 ^ 1) ^ s, (i2 ^ 1) ^ s
    return struct.pack('<2H', 0xF000 | s << 10 | (offset >> 12) & 0x3FF, 0xD000 | j1 << 13 | j2 << 11 | (offset >> 1) & 0x7FF)


class OnASmallImage(unittest.TestCase):
    def setUp(self):
        code = bytearray(b'\x00\xbf'*32)
        code[8:12] = bl(0x1008, 0x1020)
        code[40:44] = struct.pack('<I', 0x1021)  # a Thumb pointer to the same place
        code[48:53] = b'HELLO'
        self.image = Image(rows_image(bytes(code), [(0x1000, len(code), COPY, 0)]))

    def test_a_call_and_a_pointer_are_both_found_once_at_their_runtime_address(self):
        self.assertEqual(xrefs(self.image, 0x1020), [(0x1008, 'call'), (0x1028, 'pointer')])

    def test_the_thumb_bit_does_not_matter(self):
        self.assertEqual(xrefs(self.image, 0x1021), xrefs(self.image, 0x1020))

    def test_nothing_refers_to_an_unused_address(self):
        self.assertEqual(xrefs(self.image, 0x1010), [])

    def test_bytes_are_found_at_their_runtime_address_and_not_twice(self):
        self.assertEqual(find_bytes(self.image, b'HELLO'), [0x1030])
        self.assertEqual(find_bytes(self.image, b'ABSENT'), [])


@unittest.skipUnless(STOCK.exists(), 'firmware inputs not present')
class OnStock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = Image.load(STOCK)

    def test_the_key_handler_has_the_pointers_the_knowledge_base_records(self):
        found = xrefs(self.image, KEY_HANDLER)
        self.assertEqual(len([source for source, kind in found if kind == 'pointer']), 98)

    def test_every_reported_branch_is_one_to_a_second_decoder(self):
        found = [(source, kind) for source, kind in xrefs(self.image, REQUEST_PAGE) if kind != 'pointer']
        self.assertGreater(len(found), 3, 'the function that opens screens is called from many places')
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
        for source, kind in found:
            ins = next(md.disasm(self.image.read(source, 4), source))
            self.assertEqual(ins.mnemonic.split('.')[0], 'bl' if kind == 'call' else 'b', hex(source))
            self.assertEqual(int(ins.op_str.lstrip('#'), 16), REQUEST_PAGE, hex(source))

    def test_the_commands_exist(self):
        for argv in (['xrefs', str(STOCK), hex(KEY_HANDLER)], ['find', str(STOCK), 'SYSTEM']):
            result = subprocess.run([sys.executable, '-m', 'lab404', *argv], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr[-300:])
            self.assertIn('0x', result.stdout)


@unittest.skipUnless(STOCK.exists() and DOOM73.exists(), 'firmware inputs not present')
class SymbolGuards(unittest.TestCase):
    """An address in firmware_symbols is only as good as the image it was read from. Each must say which bytes it expects, and the build looks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mod = Path(self.tmp.name)/'mod'
        shutil.copytree(MOD, self.mod)

    def edit(self, change):
        spec = json.loads((self.mod/'mod.json').read_text(encoding='utf-8'))
        change(spec)
        (self.mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')

    def test_the_example_mod_builds_on_both_bases(self):
        for name, base in (('stock', STOCK), ('doom', DOOM73)):
            build(self.mod, base, Path(self.tmp.name)/name)

    def test_a_bare_address_is_refused(self):
        self.edit(lambda spec: spec['firmware_symbols'].update(request_page='0x800DA599'))
        with self.assertRaisesRegex(BuildError, 'expect'):
            build(self.mod, STOCK, Path(self.tmp.name)/'pkg')

    def test_an_address_where_the_bytes_differ_is_refused(self):
        self.edit(lambda spec: spec['firmware_symbols'].update(request_page=dict(spec['firmware_symbols']['request_page'], address='0x800DA5A1')))
        with self.assertRaisesRegex(BuildError, 'request_page'):
            build(self.mod, STOCK, Path(self.tmp.name)/'pkg')
        self.assertFalse((Path(self.tmp.name)/'pkg').exists())

    def test_too_few_bytes_are_not_a_guard(self):
        for short in (dict(expect='10b5'), dict(size=2, sha256='00'*32)):
            self.edit(lambda spec: spec['firmware_symbols'].update(request_page=dict(address='0x800DA599', **short)))
            with self.assertRaisesRegex(BuildError, 'at least'):
                build(self.mod, STOCK, Path(self.tmp.name)/'pkg')

    def test_the_bytes_themselves_still_work_for_local_use(self):
        raw = Image.load(STOCK).read(0x800DA598, 16).hex()
        self.edit(lambda spec: spec['firmware_symbols'].update(request_page=dict(address='0x800DA599', expect=raw)))
        build(self.mod, STOCK, Path(self.tmp.name)/'pkg')


if __name__ == '__main__':
    unittest.main()
