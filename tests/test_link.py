"""The linker on real clang output, executed on the stand. Needs clang, no firmware.

The expected values come from what the C source computes, so a wrong relocation shows up as a wrong number or a crash.
RED: with the addend ignored or the MOVW/MOVT halves swapped, this fails (checked by mutation on 2026-11-09).
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from lab404.build import CFLAGS
from lab404.image import extend
from lab404.link import LinkError, link
from lab404.stand import Machine
from helpers import tiny_image

A = """
extern int helper(int);
extern const unsigned table[4];
int initial = 40;
int zeroed;
static int (*volatile pointer)(int) = helper;
static int local(int x) { return x+initial; }
__attribute__((section(".text.far"), noinline)) int far(int x) { return x*2; }
int entry(int x)
{
    zeroed += 1;
    return pointer(local(x))+(int)table[x & 3]+far(zeroed);
}
"""
B = """
const unsigned table[4] = {100, 200, 300, 400};
int helper(int x) { return x+1000; }
"""
BASE = 0x83FD0000


def objects(tmp, *sources):
    out = []
    for i, text in enumerate(sources):
        c, o = tmp/f'{i}.c', tmp/f'{i}.o'
        c.write_text(text, encoding='utf-8')
        subprocess.run(['clang', *CFLAGS, '-O1', '-c', str(c), '-o', str(o)], check=True)
        out.append((c.name, o.read_bytes()))
    return out


class Link(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tmp = Path(self.dir.name)

    def run_entry(self, payload, symbols):
        machine = Machine(extend(tiny_image(), BASE, payload))
        return machine, symbols['entry']

    def test_program_across_objects_and_sections(self):
        payload, symbols = link(objects(self.tmp, A, B), BASE)
        machine, entry = self.run_entry(payload, symbols)
        # local(1)=41, helper=1041, table[1]=200, far(1)=2
        self.assertEqual(machine.call(entry, (1,)), 1243)
        # second call: zeroed is now 2, so far(2)=4; table[2]=300; local(2)=42, helper=1042
        self.assertEqual(machine.call(entry, (2,)), 1346)
        self.assertEqual(machine.u32(symbols['zeroed']), 2)

    def test_undefined_symbol_stops_the_link(self):
        with self.assertRaisesRegex(LinkError, 'undefined symbol helper'):
            link(objects(self.tmp, A, 'const unsigned table[4] = {0};'), BASE)

    def test_firmware_symbols_resolve(self):
        text = 'extern int fw(int); int entry(int x) { return fw(x)+1; }'
        payload, symbols = link(objects(self.tmp, text), BASE, {'fw': 0x1001})
        machine, entry = self.run_entry(payload, symbols)
        # tiny_image holds bx lr at 0x1000, so fw returns its argument
        self.assertEqual(machine.call(entry, (5,)), 6)

    def test_firmware_function_needs_thumb_address(self):
        text = 'extern int fw(int); int entry(int x) { return fw(x)+1; }'
        with self.assertRaisesRegex(LinkError, 'Thumb address'):
            link(objects(self.tmp, text), BASE, {'fw': 0x1000})

    def test_bad_object_refused(self):
        with self.assertRaisesRegex(LinkError, 'not a little-endian'):
            link([('x', b'not an object')], BASE)


if __name__ == '__main__':
    unittest.main()
