"""The fault screen example (mods/fault_screen): four word hooks on the fault vectors and a screen drawn by polling the display port.

The display's SPI port and data/command pin are plain memory on the stand: every write is recorded with the pin's state, and what
the controller would show is rebuilt from those bytes and compared with the same text drawn here from the example's own font.
Whether a real controller accepts the bytes is for a unit; the private mod this follows showed three real faults that way
(hk.fault-screen).
"""
import json
import re
import struct
import tempfile
import unittest
from pathlib import Path

import unicorn as uc
from unicorn import arm_const as arm

from lab404.build import build
from lab404.stand import STACK_TOP, Machine
from helpers import DOOM73, DOOM74, ROOT, STOCK

MOD = ROOT/'mods/fault_screen'
SPI, GPIO2, SCB = 0x403A0000, 0x401BC000, 0xE000E000
TDR, TCR, DER, FSR = SPI+0x64, SPI+0x60, SPI+0x1C, SPI+0x5C
VECTORS = {0xC: 0x8003C921, 0x10: 0x800406A9, 0x14: 0x80036119, 0x18: 0x800437D1}  # [BYTES] the same on every declared base


def font():
    text = (MOD/'fault_screen.c').read_text(encoding='utf-8')
    body = text[text.index('FONT[] = {'):text.index('};', text.index('FONT[] = {'))]
    values = [int(v, 16) for v in re.findall(r'0x([0-9A-F]{2})', body)]
    return {chr(0x20+i): values[7*i:7*i+7] for i in range(len(values)//7)}


def expected(lines):
    """The 128 x 64 picture the example should draw: text at x = 1 in 6-pixel cells, one 8-row line each, a rule under line 0."""
    glyphs, px = font(), [[False]*128 for _ in range(64)]
    for x in range(128):
        px[8][x] = True
    for line, parts in lines.items():
        x = 1
        for part in parts:
            for ch in part:
                for row, bits in enumerate(glyphs[ch]):
                    for col in range(5):
                        if bits & (0x10 >> col) and x+col < 128:
                            px[8*line+row][x+col] = True
                x += 6
            x += 6
    return px


class Port:
    """A stand machine of the candidate with the display port and the system control block as recorded memory."""
    def __init__(self, raw, full=False):
        self.machine = Machine(raw)
        m = self.machine.m
        for page in (SPI, GPIO2, SCB):
            m.mem_map(page, 0x1000)
        m.mem_write(TCR, struct.pack('<I', 0xC1000007 | 1 << 21))  # as a DMA transfer might leave it (made up)
        m.mem_write(DER, struct.pack('<I', 1))
        if full:
            m.mem_write(FSR, struct.pack('<I', 0x1F))  # a transmitter that never drains
        self.sent, self.dc, self.writes = [], None, []

        def write(_m, _access, address, _size, value, _data):
            if address == TDR:
                self.sent.append((self.dc, value & 0xFF))
            elif address == GPIO2+0x84 and value & 2:
                self.dc = 1
            elif address == GPIO2+0x88 and value & 2:
                self.dc = 0
            if SPI <= address < SPI+0x100:
                self.writes.append((address-SPI, value))
        m.hook_add(uc.UC_HOOK_MEM_WRITE, write)

    def screen(self):
        data = [b for dc, b in self.sent if dc == 1]
        assert len(data) == 1024, len(data)
        return [[bool(data[(y//8)*128+x] & (1 << (y % 8))) for x in range(128)] for y in range(64)]


@unittest.skipUnless(STOCK.exists(), 'stock-5.52 input needed')
class FaultScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='lab404-fault-')
        cls.packages = {}
        for name, base in (('stock', STOCK), ('doom73', DOOM73), ('doom74', DOOM74)):
            if base.exists():
                out = Path(cls.tmp.name)/name
                cls.packages[name] = (build(MOD, base, out), (out/'SP404MKII_APP1.bin').read_bytes())
        cls.manifest, cls.raw = cls.packages['stock']
        cls.symbol = {k: int(v, 16) for k, v in cls.manifest['symbols'].items()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def same(self, got, want):
        for y in range(64):
            self.assertEqual(''.join('#' if v else '.' for v in got[y]), ''.join('#' if v else '.' for v in want[y]), f'row {y}')

    def test_every_base_sends_all_four_fault_vectors_to_the_handler(self):
        for name, (manifest, _) in self.packages.items():
            hooks = {int(h['address'], 16): (h['before'], h['after']) for h in manifest['hooks']}
            handler = int(manifest['symbols']['fault_screen_fault'], 16)
            for vector, stock in VECTORS.items():
                self.assertEqual(hooks[vector], (struct.pack('<I', stock).hex(), struct.pack('<I', handler | 1).hex()), (name, hex(vector)))

    def test_a_fault_is_drawn_as_the_controller_expects_it(self):
        p = Port(self.raw)
        p.machine.write(0xE000ED28, struct.pack('<I', 0x00008200))  # BFARVALID: the address is in BFAR
        p.machine.write(0xE000ED38, struct.pack('<I', 0xDEADBEEF))
        p.machine.call(self.symbol['fault_screen_report'], (5, 0x8006A11A, 0x8006A0E1), budget=2000000)
        self.assertEqual(p.sent[:6], [(0, 0x21), (0, 0), (0, 127), (0, 0x22), (0, 0), (0, 7)])  # columns 0-127, pages 0-7, as commands
        self.assertEqual({dc for dc, _ in p.sent[6:]}, {1})
        self.assertEqual(len(p.sent), 6+1024)
        self.same(p.screen(), expected({0: ['404LAB FAULT SCREEN'], 2: ['BUS FAULT'], 3: ['PC', '8006A11A'], 4: ['LR', '8006A0E1'],
                                        5: ['CFSR', '00008200'], 6: ['BFAR', 'DEADBEEF'], 7: ['PHOTO THIS, POWER OFF']}))

    def test_each_kind_has_its_name_and_the_right_address_register(self):
        for kind, name in ((3, 'HARD FAULT'), (4, 'MEMORY FAULT'), (6, 'USAGE FAULT')):
            p = Port(self.raw)
            p.machine.call(self.symbol['fault_screen_report'], (kind, 1, 2), budget=2000000)
            want = expected({2: [name]})
            for y in range(16, 24):
                self.assertEqual(p.screen()[y], want[y], (kind, y))
        p = Port(self.raw)
        p.machine.write(0xE000ED28, struct.pack('<I', 0x82))  # MMARVALID
        p.machine.write(0xE000ED34, struct.pack('<I', 0x12345678))
        p.machine.call(self.symbol['fault_screen_report'], (4, 1, 2), budget=2000000)
        want = expected({6: ['MMFAR', '12345678']})
        for y in range(48, 56):
            self.assertEqual(p.screen()[y], want[y], y)

    def test_the_port_is_left_as_it_was_found(self):
        p = Port(self.raw)
        p.machine.call(self.symbol['fault_screen_report'], (5, 1, 2), budget=2000000)
        last = {}
        for register, value in p.writes:
            last[register] = value
        self.assertEqual((last[0x60], last[0x1C]), (0xC1000007 | 1 << 21, 1))
        self.assertEqual([v for r, v in p.writes if r == 0x1C][0], 0)  # DMA requests off first
        self.assertEqual([v for r, v in p.writes if r == 0x60][0], 0xC1000000 | 1 << 19 | 7)  # 8-bit frames, receive masked

    def test_a_port_that_never_drains_cannot_hold_the_processor_for_ever(self):
        p = Port(self.raw, full=True)
        p.machine.call(self.symbol['fault_screen_report'], (3, 1, 2), budget=5000000)  # one bounded wait, then it gives up

    def test_the_handler_reads_the_frame_moves_to_its_own_stack_and_stands(self):
        p = Port(self.raw)
        m = p.machine.m
        frame = STACK_TOP-0x100
        m.mem_write(frame, struct.pack('<8I', 0, 1, 2, 3, 12, 0x800406A9, 0x8003C920, 0x01000000))
        seen = []
        report, handler = self.symbol['fault_screen_report'] & ~1, self.symbol['fault_screen_fault'] & ~1

        def hook(cpu, pc, _size, _data):
            if pc == report:
                seen.append((cpu.reg_read(arm.UC_ARM_REG_R1), cpu.reg_read(arm.UC_ARM_REG_R2), cpu.reg_read(arm.UC_ARM_REG_SP)))
                cpu.reg_write(arm.UC_ARM_REG_PC, cpu.reg_read(arm.UC_ARM_REG_LR))
        m.hook_add(uc.UC_HOOK_CODE, hook)
        m.reg_write(arm.UC_ARM_REG_MSP, frame)
        m.reg_write(arm.UC_ARM_REG_SP, frame)
        m.reg_write(arm.UC_ARM_REG_LR, 0xFFFFFFF9)  # returning to thread mode on MSP
        m.emu_start(handler | 1, 0, count=2000)
        self.assertEqual(seen, [(0x8003C920, 0x800406A9, self.symbol['fault_screen_stack']+1024)])
        pc = m.reg_read(arm.UC_ARM_REG_PC)
        self.assertTrue(handler <= pc < handler+0x30, hex(pc))
        self.assertEqual(bytes(m.mem_read(pc, 2)), bytes.fromhex('fee7'))  # b . : it never returns

    def test_the_payload_fits_and_the_stack_is_inside_it(self):
        size = int(json.loads((MOD/'mod.json').read_text(encoding='utf-8'))['payload']['max_size'], 16)
        self.assertLessEqual(self.manifest['payload']['bytes'], size)
        top = self.symbol['fault_screen_stack']+1024
        self.assertLessEqual(top, 0x83FD0000+self.manifest['payload']['bytes'])


if __name__ == '__main__':
    unittest.main()
