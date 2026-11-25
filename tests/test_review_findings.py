"""Each test reproduces a defect found in independent review (2026-11-09). They failed before the fixes."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from unicorn import arm_const as arm

from lab404.build import CFLAGS, SFLAGS, build, source_digest
from lab404.hooks import check_entry_hook, plan_patch, stub_source
from lab404.image import COPY, Image, ImageError, ZERO, extend
from lab404.link import LinkError, link
from lab404.stand import Machine
from helpers import ROOT, STOCK, rows_image, tiny_image

BASE = 0x83FD0000
CARRY = 1 << 29


def c_object(tmp, name, text):
    src, out = tmp/f'{name}.c', tmp/f'{name}.o'
    src.write_text(text, encoding='utf-8')
    subprocess.run(['clang', *CFLAGS, '-c', str(src), '-o', str(out)], check=True)
    return name, out.read_bytes()


def asm_object(tmp, name, text):
    src, out = tmp/f'{name}.S', tmp/f'{name}.o'
    src.write_text('.syntax unified\n.thumb\n.text\n'+text, encoding='utf-8')
    subprocess.run(['clang', *SFLAGS, '-c', str(src), '-o', str(out)], check=True)
    return name, out.read_bytes()


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tmp = Path(d.name)


class HookSafety(Base):
    def test_flags_survive_the_stub(self):
        # push {r4,lr}; three nops; adcs r0,r0; pop {r4,pc}. The result depends on the incoming carry.
        code = bytes.fromhex('10b5' '00bf' '00bf' '00bf' '4041' '10bd' '00bf00bf')
        raw = tiny_image(code)
        image = Image(raw)
        displaced, _ = check_entry_hook(image, 0x1000)
        clobber = c_object(self.tmp, 'c', 'void clobber(void) { __asm__ volatile("adds r0, r0, #0" : : : "r0", "cc"); }')
        stub = asm_object(self.tmp, 's', stub_source(0, 0x1000, 'clobber', displaced))
        payload, symbols = link([clobber, stub], BASE)
        out = extend(raw, BASE, payload, [plan_patch(image, 0x1000, symbols['lab404_stub_0'])])
        results = []
        for candidate in (raw, out):
            machine = Machine(candidate)
            machine.m.reg_write(arm.UC_ARM_REG_APSR_NZCV, CARRY)
            results.append(machine.call(0x1000, (3,)))
        self.assertEqual(results[0], 7)
        self.assertEqual(results[1], 7, 'the hook changed the flags the hooked function reads')

    def test_refuses_a_site_inside_an_it_block(self):
        # it eq, then push: the push only looks like a function entry
        code = bytes(0x12)+bytes.fromhex('08bf')+bytes.fromhex('2de9f043' '00bf00bf' '00bf00bf')
        image = Image(tiny_image(code+bytes(16)))
        with self.assertRaisesRegex(ImageError, 'IT block'):
            check_entry_hook(image, 0x1014)

    def test_refuses_a_far_branch_into_replaced_bytes(self):
        # A b.w 0x6000 bytes later lands at site+4, far outside any local window.
        code = bytearray(bytes.fromhex('2de9f043' '00bf00bf')+bytes(0x6000))
        at = 0x6000
        target = 0x1000+4
        pc = 0x1000+at+4
        offset = target-pc
        s = 1 if offset < 0 else 0
        i1, i2 = (offset >> 23) & 1, (offset >> 22) & 1
        j1, j2 = 1 ^ i1 ^ s, 1 ^ i2 ^ s
        hw1 = 0xF000 | (s << 10) | ((offset >> 12) & 0x3FF)
        hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | ((offset >> 1) & 0x7FF)
        code[at:at+4] = hw1.to_bytes(2, 'little')+hw2.to_bytes(2, 'little')
        with self.assertRaisesRegex(ImageError, 'inside the bytes'):
            check_entry_hook(Image(tiny_image(bytes(code))), 0x1000)

    def test_refuses_a_stored_pointer_into_replaced_bytes(self):
        code = bytes.fromhex('2de9f043' '00bf00bf')+bytes(8)+(0x1005).to_bytes(4, 'little')
        with self.assertRaisesRegex(ImageError, 'inside the bytes'):
            check_entry_hook(Image(tiny_image(code)), 0x1000)

    def test_a_word_can_be_declared_not_a_pointer_but_a_branch_cannot(self):
        code = bytes.fromhex('2de9f043' '00bf00bf')+bytes(8)+(0x1005).to_bytes(4, 'little')
        image = Image(tiny_image(code))
        # The word is visible twice: at its runtime address and in flash. Declaring only one still refuses.
        check_entry_hook(image, 0x1000, not_pointers=(0x1010, 0x60080110))
        with self.assertRaisesRegex(ImageError, 'inside the bytes'):
            check_entry_hook(image, 0x1000, not_pointers=(0x1010,))
        branch = bytes.fromhex('2de9f043' '00bf00bf' '00bf00bf')+bytes.fromhex('fff7fabf')  # b.w back into the span
        with self.assertRaisesRegex(ImageError, 'inside the bytes'):
            check_entry_hook(Image(tiny_image(branch)), 0x1000, not_pointers=(0x100C,))

    def test_site_at_the_start_of_memory_gives_a_refusal_not_a_crash(self):
        code = bytes.fromhex('2de9f043' '00bf00bf')
        image = Image(rows_image(code, [(0x7000, len(code), COPY, 0)]))
        check_entry_hook(image, 0x7000)


class Relocations(Base):
    def test_address_of_thumb_function_plus_one_keeps_one_thumb_bit(self):
        # ABI: (S + A) | T. entry is at BASE+4 after the table word order below, so entry+1 must stay odd by exactly one bit.
        obj = asm_object(self.tmp, 'a', """
    .global entry
    .type entry, %function
    .thumb_func
entry:
    bx lr
    nop
    .global table
table:
    .word entry
    .word entry+2
""")
        payload, symbols = link([obj], BASE)
        machine = Machine(extend(tiny_image(), BASE, payload))
        entry = symbols['entry'] & ~1
        self.assertEqual(machine.u32(symbols['table']), entry | 1)
        self.assertEqual(machine.u32(symbols['table']+4), (entry+2) | 1)

    def test_strong_definition_wins_in_either_order(self):
        weak = c_object(self.tmp, 'w', '__attribute__((weak)) int f(void) { return 2; }')
        strong = c_object(self.tmp, 's', 'int f(void) { return 3; }')
        user = c_object(self.tmp, 'u', 'extern int f(void); int entry(void) { return f(); }')
        for order in ([weak, strong, user], [strong, weak, user]):
            payload, symbols = link(order, BASE)
            self.assertEqual(Machine(extend(tiny_image(), BASE, payload)).call(symbols['entry']), 3)

    def test_two_strong_definitions_are_refused(self):
        a = c_object(self.tmp, 'a', 'int f(void) { return 1; }')
        b = c_object(self.tmp, 'b', 'int f(void) { return 2; }')
        with self.assertRaisesRegex(LinkError, 'defined twice'):
            link([a, b], BASE)

    def test_branch_to_firmware_function_plus_offset_is_refused(self):
        # A veneer holds one address, so an offset on the branch would land inside the veneer.
        obj = asm_object(self.tmp, 'a', '.global entry\n.thumb_func\nentry:\n    b.w fw+4\n')
        with self.assertRaisesRegex(LinkError, 'offset'):
            link([obj], BASE, {'fw': 0x1001})


class Layout(Base):
    def test_payload_may_not_land_on_flash(self):
        raw = tiny_image()
        with self.assertRaisesRegex(ImageError, 'flash'):
            extend(raw, 0x60080000+len(raw)+0x20, b'\xAA'*8)

    def test_later_row_wins_like_startup(self):
        raw = rows_image(b'ABCDEFGH', [(0x1000, 8, COPY, 0), (0x1000, 4, ZERO, 0)])
        self.assertEqual(Machine(raw).read(0x1000, 8), bytes(4)+b'EFGH')
        image = Image(raw)
        self.assertEqual(image.read(0x1000, 4), bytes(4))
        self.assertEqual(image.read(0x1004, 4), b'EFGH')
        with self.assertRaisesRegex(ImageError, 'overlap'):
            image.read(0x1000, 8)

    def test_real_images_have_no_overlapping_rows(self):
        if not STOCK.exists():
            self.skipTest('firmware inputs not present')
        rows = sorted(Image.load(STOCK).rows, key=lambda r: r[1])
        for a, b in zip(rows, rows[1:]):
            self.assertLessEqual(a[1]+a[2], b[1])


class Bindings(Base):
    def test_source_digest_follows_the_sources(self):
        mod = self.tmp/'mod'
        shutil.copytree(ROOT/'mods/demo_counter', mod)
        import json
        spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
        before = source_digest(mod, spec)
        (mod/'counter.c').write_text((mod/'counter.c').read_text(encoding='utf-8')+'\n/* changed */\n', encoding='utf-8')
        self.assertNotEqual(source_digest(mod, spec), before)

    def test_changed_code_changes_the_candidate(self):
        if not STOCK.exists():
            self.skipTest('firmware inputs not present')
        mod = self.tmp/'mod'
        shutil.copytree(ROOT/'mods/demo_counter', mod)
        first = build(mod, STOCK, self.tmp/'a')
        (mod/'counter.c').write_text((mod/'counter.c').read_text(encoding='utf-8').replace('calls++', 'calls += 2'), encoding='utf-8')
        second = build(mod, STOCK, self.tmp/'b')
        self.assertNotEqual(first['candidate_sha256'], second['candidate_sha256'])
        self.assertNotEqual(first['source_sha256'], second['source_sha256'])


if __name__ == '__main__':
    unittest.main()
