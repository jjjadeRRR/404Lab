"""Copies of stock functions: a mod takes a piece of the firmware's own machine code into its payload and changes a few bytes.

This is how the maintainer's private mod got 32 AUTO MARK marks out of the stock analysis instead of writing it again
(hk.recipe.automark-32). The bytes come from the user's image at build time and must match a SHA-256 the mod declares, so no
firmware is kept in the mod and a different base is refused rather than copied blindly.

The copy keeps its address mod 4, so PC-relative literal loads inside it still line up. A branch that leaves the copy is aimed
again at a veneer placed after it (ldr.w pc,[pc] and the old target), or at a mod function the mod names in `redirect`.
Branches inside the copy stay as they are. Refused: a PC-relative load of anything outside the copy, a cbz/cbnz or short
branch that leaves the copy and cannot reach the veneers, and edits that do not match the bytes.
"""
import hashlib
import struct

import capstone
from capstone import arm as cs_arm

from .image import ImageError, protected

CONDITIONAL = {'beq', 'bne', 'bhs', 'bcs', 'blo', 'bcc', 'bmi', 'bpl', 'bvs', 'bvc', 'bhi', 'bls', 'bge', 'blt', 'bgt', 'ble'}


def _int(value):
    return value if isinstance(value, int) else int(value, 0)


def _disassembler():
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    md.detail = True
    return md


def _sweep(code, start):
    """Decode the copy one instruction at a time, skipping the literal words its PC-relative loads read, so data in a
    literal pool is never taken for a branch. Returns [(instruction, literal_target or None)]."""
    md, out, literals, at = _disassembler(), [], set(), 0
    while at < len(code):
        if start+at in literals:
            at += 2
            continue
        ins = next(md.disasm(code[at:at+4], start+at, count=1), None)
        if ins is None:
            raise ImageError(f'0x{start+at:08X}: cannot decode the copy here; is the range one function?')
        target = None
        for op in ins.operands:
            if op.type == cs_arm.ARM_OP_MEM and op.mem.base == cs_arm.ARM_REG_PC:
                target = ((ins.address+4) & ~3)+op.mem.disp
                width = 8 if ins.mnemonic.startswith(('ldrd', 'vldr')) and 'd' in ins.op_str.split(',')[0] else 4
                literals.update(range(target, target+width, 2))
        if ins.mnemonic.startswith('adr'):
            target = ((ins.address+4) & ~3)+(ins.operands[-1].imm if ins.operands[-1].type == cs_arm.ARM_OP_IMM else 0)
        out.append((ins, target))
        at += ins.size
        if ins.mnemonic in ('tbb', 'tbh') and 'pc' in ins.op_str.split(',')[0]:
            # The table of offsets follows the instruction. It ends where the nearest of its own targets begins.
            width, table, first = (1 if ins.mnemonic == 'tbb' else 2), at, None
            while first is None or table < first:
                if table+width > len(code):
                    raise ImageError(f'0x{ins.address:08X}: its branch table runs past the end of the copy')
                entry = code[table] if width == 1 else struct.unpack_from('<H', code, table)[0]
                goes = at+2*entry
                first = goes if first is None else min(first, goes)
                table += width
            literals.update(range(start+at, start+first, 2))
    return out


def _branch(source, target, original):
    """Encode a Thumb branch at source to target in the same encoding as the original bytes. The form is read from the bytes,
    not the mnemonic: inside an IT block a branch prints with a condition but is encoded without one."""
    off = target-(source+4)
    if off & 1:
        raise ImageError('odd branch offset')
    if len(original) == 2:
        hw = struct.unpack('<H', original)[0]
        if hw >> 11 == 0b11100:                                   # T2: b
            if not -2048 <= off < 2048:
                raise ImageError(f'0x{source:08X}: a short branch out of the copy cannot reach its veneer')
            return struct.pack('<H', 0xE000 | ((off >> 1) & 0x7FF))
        if hw >> 12 == 0b1101:                                    # T1: b<cond>
            if not -256 <= off < 256:
                raise ImageError(f'0x{source:08X}: a short conditional branch out of the copy cannot reach its veneer')
            return struct.pack('<H', (hw & 0xFF00) | ((off >> 1) & 0xFF))
        raise ImageError(f'0x{source:08X}: this branch leaves the copy and cannot be aimed again')
    hw1, hw2 = struct.unpack('<2H', original)
    if hw2 & 0x5000 in (0x5000, 0x1000):                          # T1 bl, T4 b.w: 24-bit range
        if not -(1 << 24) <= off < (1 << 24):
            raise ImageError(f'0x{source:08X}: branch out of reach')
        s, i1, i2 = (off >> 24) & 1, (off >> 23) & 1, (off >> 22) & 1
        j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
        return struct.pack('<2H', 0xF000 | (s << 10) | ((off >> 12) & 0x3FF), (hw2 & 0xD000) | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF))
    if hw2 & 0x5000 == 0:                                         # T3 b<cond>.w: 20-bit range
        if not -(1 << 20) <= off < (1 << 20):
            raise ImageError(f'0x{source:08X}: conditional branch out of reach of its veneer')
        s, j1, j2 = (off >> 20) & 1, (off >> 18) & 1, (off >> 19) & 1
        return struct.pack('<2H', 0xF000 | (s << 10) | (hw1 & 0x03C0) | ((off >> 12) & 0x3F), 0x8000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF))
    raise ImageError(f'0x{source:08X}: this branch leaves the copy and cannot be aimed again')


def plan_copy(image, spec):
    """Read and check one declared copy. spec: name, from, to, sha256, optional edits [{address, before, after}] and redirect
    {old target: mod function}. Returns the plan used by placeholder() and place()."""
    start, end = _int(spec['from']), _int(spec['to'])
    if start & 1 or end <= start or end-start > 0x10000:
        raise ImageError(f'copy {spec["name"]}: give an even start and an end after it, at most 64 KB')
    for at in range(start, end, 2):
        zone = protected(image, at)
        if zone:
            raise ImageError(f'copy {spec["name"]}: 0x{at:08X} is inside {zone}; code that can erase the loader is never copied')
    code = bytearray(image.read(start, end-start))
    if hashlib.sha256(code).hexdigest() != spec['sha256'].lower():
        raise ImageError(f'copy {spec["name"]}: the bytes at 0x{start:08X}-0x{end:08X} are not the ones declared (sha256): another base?')
    late = []
    for edit in spec.get('edits', []):
        at, before = _int(edit['address']), bytes.fromhex(edit['before'])
        if not start <= at < at+len(before) <= end:
            raise ImageError(f'copy {spec["name"]}: the edit at 0x{at:08X} must stay inside the copy')
        if bytes(code[at-start:at-start+len(before)]) != before:
            raise ImageError(f'copy {spec["name"]}: 0x{at:08X} does not hold {before.hex()}')
        if 'after' in edit:
            after = bytes.fromhex(edit['after'])
            if len(after) != len(before):
                raise ImageError(f'copy {spec["name"]}: the edit at 0x{at:08X} must keep its size')
            code[at-start:at-start+len(after)] = after
            continue
        half = 'movw' if 'movw' in edit else 'movt' if 'movt' in edit else None
        hw1 = struct.unpack_from('<H', before)[0] if len(before) == 4 else 0
        if half is None or len(before) != 4 or hw1 & 0xFBF0 != (0xF240 if half == 'movw' else 0xF2C0):
            raise ImageError(f'copy {spec["name"]}: the edit at 0x{at:08X} needs "after", or "movw"/"movt" naming a symbol over a {half or "movw or movt"} instruction')
        late.append((at-start, half, edit[half], (struct.unpack_from('<H', before, 2)[0] >> 8) & 0xF))
    redirect = {_int(k): v for k, v in spec.get('redirect', {}).items()}
    leaving, targets = [], []
    for ins, literal in _sweep(bytes(code), start):
        if literal is not None and not start <= literal < end:
            raise ImageError(f'copy {spec["name"]}: 0x{ins.address:08X} {ins.mnemonic} reads 0x{literal:08X}, outside the copy')
        base = ins.mnemonic.split('.')[0]
        if base in ('b', 'bl', 'cbz', 'cbnz') or base in CONDITIONAL:
            target = ins.operands[-1].imm & 0xFFFFFFFF
            if start <= target < end:
                continue
            if base in ('cbz', 'cbnz'):
                raise ImageError(f'copy {spec["name"]}: 0x{ins.address:08X} {ins.mnemonic} leaves the copy and cannot be aimed again')
            if protected(image, target) and target not in redirect:
                raise ImageError(f'copy {spec["name"]}: 0x{ins.address:08X} branches into {protected(image, target)}')
            if target not in targets:
                targets.append(target)
            leaving.append((ins.address-start, ins.size, target))
        elif base in ('blx', 'bx') and ins.operands and ins.operands[0].type == cs_arm.ARM_OP_IMM:
            raise ImageError(f'copy {spec["name"]}: 0x{ins.address:08X} {ins.mnemonic} to an immediate is not supported')
    unknown = [hex(t) for t in redirect if t not in targets]
    if unknown:
        raise ImageError(f'copy {spec["name"]}: nothing in the copy branches to {", ".join(unknown)}')
    return dict(name=spec['name'], start=start, end=end, code=bytes(code), leaving=leaving, targets=targets, redirect=redirect, late=late)


def placeholder(plan):
    """Assembly that reserves the copy's room in the payload at the right address mod 4, with its veneers after it."""
    return f"""
    .section .text.lab404_copy_{plan['name']},"ax",%progbits
    .balign 4
    .space {plan['start'] % 4}
    .global {plan['name']}
    .type {plan['name']}, %function
    .thumb_func
{plan['name']}:
    .space {len(plan['code'])}
    .balign 4
    .space {8*len(plan['targets'])}
"""


def place(plan, address, symbols):
    """The copy's bytes and veneers for its final address. address is where the code starts (the symbol without bit 0)."""
    if (address-plan['start']) % 4:
        raise ImageError(f'copy {plan["name"]}: placed at 0x{address:08X}, which does not keep its address mod 4')
    code = bytearray(plan['code'])
    for offset, half, name, register in plan['late']:  # movw/movt aimed at a symbol of the mod, known only now
        if name not in symbols:
            raise ImageError(f'copy {plan["name"]}: {name} is not a symbol of the mod')
        value = symbols[name] & 0xFFFF if half == 'movw' else symbols[name] >> 16
        hw1 = (0xF240 if half == 'movw' else 0xF2C0) | (((value >> 11) & 1) << 10) | ((value >> 12) & 0xF)
        code[offset:offset+4] = struct.pack('<2H', hw1, (((value >> 8) & 7) << 12) | (register << 8) | (value & 0xFF))
    tail = (address+len(code)+3) & ~3
    veneer = {target: tail+8*i for i, target in enumerate(plan['targets'])}
    for offset, size, target in plan['leaving']:
        code[offset:offset+size] = _branch(address+offset, veneer[target], bytes(code[offset:offset+size]))
    out = bytes(code)+bytes(tail-address-len(code))
    for target in plan['targets']:
        goes = target | 1
        if target in plan['redirect']:
            name = plan['redirect'][target]
            if name not in symbols or not symbols[name] & 1:
                raise ImageError(f'copy {plan["name"]}: redirect to {name}, which is not a Thumb function of the mod')
            goes = symbols[name]
        out += bytes.fromhex('dff800f0')+struct.pack('<I', goes)
    return out


__all__ = ['place', 'placeholder', 'plan_copy']
