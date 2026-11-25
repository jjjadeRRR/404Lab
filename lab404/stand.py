"""Run firmware code on the emulator from an image's real startup memory.

Memory starts as the scatter table leaves it, not as zeros. Runs are bounded by instruction count, never by wall-clock time, so
results do not depend on machine load. Touching memory the stand does not model stops the run with a `Boundary`: what was not
executed is reported, not assumed to be fine.

This models instructions and memory contents. It does not model timing, caches, peripherals, the RTOS or the second processor.
"""
import struct

import unicorn as uc
from unicorn import arm_const as arm

from .image import Image

PAGE = 0x1000
FIXTURE_BASE = 0x30000000
FIXTURE_SIZE = 0x40000
RETURN = FIXTURE_BASE+FIXTURE_SIZE-PAGE
STACK_TOP = RETURN-0x100
CALLEE_SAVED = [getattr(arm, f'UC_ARM_REG_R{i}') for i in range(4, 12)]


class Boundary(RuntimeError):
    """The run reached something the stand does not model."""


class Machine:
    def __init__(self, image):
        self.image = image if isinstance(image, Image) else Image(image)
        self.m = uc.Uc(uc.UC_ARCH_ARM, uc.UC_MODE_THUMB | uc.UC_MODE_MCLASS)
        self.m.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_M7)
        ranges = sorted((start & ~(PAGE-1), (start+len(data)+PAGE-1) & ~(PAGE-1)) for start, data, _ in self.image.segments)
        merged = []
        for lo, hi in ranges:
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
            else:
                merged.append((lo, hi))
        for lo, hi in merged:
            self.m.mem_map(lo, hi-lo)
        for start, data, _ in self.image.segments:  # startup order, zeroed rows included
            self.m.mem_write(start, data)
        self.m.mem_map(FIXTURE_BASE, FIXTURE_SIZE)
        self._problem = None
        self.stubs = {}
        self.stub_calls = []
        self.m.hook_add(uc.UC_HOOK_MEM_UNMAPPED, self._unmapped)
        self.m.hook_add(uc.UC_HOOK_INSN_INVALID, self._invalid)

    def _unmapped(self, _m, access, address, size, _value, _data):
        self._problem = f'access to unmodelled address 0x{address:08X} ({size} bytes), PC 0x{self.m.reg_read(arm.UC_ARM_REG_PC):08X}'
        return False

    def _invalid(self, _m, _data):
        self._problem = f'invalid instruction at PC 0x{self.m.reg_read(arm.UC_ARM_REG_PC):08X}'
        return False

    def stub(self, address, behaviour=None, name=None):
        """Replace a firmware function on purpose. behaviour(machine, r0, r1, r2, r3) returns r0 (None leaves it).

        Every call is logged in stub_calls: a report must list what was stubbed, because that code did not run.
        """
        address &= ~1
        self.stubs[address] = name or f'0x{address:08X}'

        def on_entry(_m, _address, _size, _data):
            args = [self.m.reg_read(getattr(arm, f'UC_ARM_REG_R{i}')) for i in range(4)]
            self.stub_calls.append((self.stubs[address], tuple(args)))
            result = behaviour(self, *args) if behaviour else None
            if result is not None:
                self.m.reg_write(arm.UC_ARM_REG_R0, result & 0xFFFFFFFF)
            self.m.reg_write(arm.UC_ARM_REG_PC, self.m.reg_read(arm.UC_ARM_REG_LR) | 1)

        self.m.hook_add(uc.UC_HOOK_CODE, on_entry, begin=address, end=address)

    def write(self, address, data):
        self.m.mem_write(address, bytes(data))

    def read(self, address, size):
        return bytes(self.m.mem_read(address, size))

    def u32(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def call(self, address, args=(), budget=200000):
        """Call a Thumb function under AAPCS. Checks it returned, and kept the stack and callee-saved registers."""
        registers, stacked = list(args[:4]), list(args[4:])
        sp = (STACK_TOP-4*len(stacked)) & ~7
        if stacked:
            self.write(sp, struct.pack(f'<{len(stacked)}I', *stacked))
        for i, value in enumerate(registers):
            self.m.reg_write(getattr(arm, f'UC_ARM_REG_R{i}'), value & 0xFFFFFFFF)
        saved = {reg: 0x12340000+i for i, reg in enumerate(CALLEE_SAVED)}
        for reg, value in saved.items():
            self.m.reg_write(reg, value)
        self.m.reg_write(arm.UC_ARM_REG_SP, sp)
        self.m.reg_write(arm.UC_ARM_REG_LR, RETURN | 1)
        self.m.ctl_flush_tb()  # Unicorn 2.1.4 can run a stale translation block after a run stopped inside one
        self._problem = None
        try:
            self.m.emu_start(address | 1, RETURN, timeout=0, count=budget)
        except uc.UcError as e:
            raise Boundary(self._problem or str(e)) from e
        if self.m.reg_read(arm.UC_ARM_REG_PC) != RETURN:
            raise Boundary(f'did not return within {budget} instructions, PC 0x{self.m.reg_read(arm.UC_ARM_REG_PC):08X}')
        if self.m.reg_read(arm.UC_ARM_REG_SP) != sp:
            raise AssertionError('stack pointer not restored')
        for reg, value in saved.items():
            if self.m.reg_read(reg) != value:
                raise AssertionError('a callee-saved register was not preserved')
        return self.m.reg_read(arm.UC_ARM_REG_R0)
