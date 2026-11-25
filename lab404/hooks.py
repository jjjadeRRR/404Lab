"""Check hook sites and produce their patches: function-entry hooks with a stub, and word hooks that repoint a code pointer.

An entry hook replaces the first instructions of a function with a jump to a generated stub. The stub saves the caller-saved
integer registers and the flags, calls the mod's function, restores them, runs the displaced instructions and jumps back.

Checked from bytes: the site looks like a function entry and is not inside an IT block, whole instructions are displaced, none of
them depends on where it runs, and no direct branch or stored pointer anywhere in the image lands inside the replaced bytes.
Not visible from bytes: jumps through addresses computed at run time. The mod's function runs in whatever context called the hooked
function, on that stack, at that interrupt level. Its own code is built without FPU use, but a firmware function it calls may use it.
"""
import struct

import capstone
from capstone import arm as cs_arm

from .image import DISABLEABLE, RETURN_ZERO, Image, ImageError, protected

BRANCH_PREFIXES = ('b.', 'bl', 'bx', 'cbz', 'cbnz', 'tbb', 'tbh', 'it', 'udf', 'svc', 'bkpt')
BRANCHES = {'b', 'beq', 'bne', 'bhs', 'blo', 'bmi', 'bpl', 'bvs', 'bvc', 'bhi', 'bls', 'bge', 'blt', 'bgt', 'ble', 'bl', 'cbz', 'cbnz'}
SHORT_RANGE = 0x1000  # 16-bit branches reach about 2 KB


def _disassembler():
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    md.detail = True
    return md


def jump_patch(address, target):
    """ldr.w pc,[pc,#imm] plus its literal. The literal must be word aligned, which costs 2 bytes at an unaligned site."""
    if address & 1:
        raise ImageError('a Thumb code address must be even')
    if address % 4 == 0:
        return bytes.fromhex('dff800f0')+struct.pack('<I', target | 1)
    return bytes.fromhex('dff804f0')+bytes.fromhex('00bf')+struct.pack('<I', target | 1)


def jump_size(address):
    return 8 if address % 4 == 0 else 10


def _is_control_flow(ins):
    name = ins.mnemonic.split('.')[0]
    return name in BRANCHES or ins.mnemonic.startswith(BRANCH_PREFIXES) or cs_arm.ARM_REG_PC in ins.regs_access()[1]


def _uses_pc(ins):
    return cs_arm.ARM_REG_PC in ins.regs_access()[0] or any(
        op.type == cs_arm.ARM_OP_MEM and op.mem.base == cs_arm.ARM_REG_PC for op in ins.operands)


def _wide_branch_target(hw1, hw2, pc):
    """Target of a 32-bit Thumb BL, B.W or B<c>.W, or None."""
    if hw1 >> 11 != 0b11110 or not hw2 & 0x8000:
        return None
    s, j1, j2 = (hw1 >> 10) & 1, (hw2 >> 13) & 1, (hw2 >> 11) & 1
    op = (hw2 >> 12) & 0b101
    if op in (0b101, 0b001):
        i1, i2 = 1 ^ j1 ^ s, 1 ^ j2 ^ s
        offset = (s << 24) | (i1 << 23) | (i2 << 22) | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1)
        return (pc+4+offset-((1 << 25) if s else 0)) & 0xFFFFFFFF
    if op == 0 and (hw1 >> 6) & 0xF < 0b1110:
        offset = (s << 20) | (j2 << 19) | (j1 << 18) | ((hw1 & 0x3F) << 12) | ((hw2 & 0x7FF) << 1)
        return (pc+4+offset-((1 << 21) if s else 0)) & 0xFFFFFFFF
    return None


def _references(image):
    """({target: source} for 32-bit branches, {target: [sources]} for aligned words that could be Thumb pointers), built once.

    Decodes at every halfword and reads every word, so data can look like a reference. A branch hit is always refused. A word hit
    can be data, such as a table of numbers: after looking at it, a mod may declare it in `not_pointers` with its reason.
    """
    if hasattr(image, '_reference_cache'):
        return image._reference_cache
    branches, words = {}, {}
    for start, data, label in image.segments:
        if label == 'ZERO':
            continue
        halves = struct.unpack_from(f'<{len(data)//2}H', data)
        for i in range(len(halves)-1):
            if halves[i] >> 11 == 0b11110:
                target = _wide_branch_target(halves[i], halves[i+1], start+2*i)
                if target is not None:
                    branches.setdefault(target, start+2*i)
        skip = -start % 4
        for i, word in enumerate(struct.unpack_from(f'<{(len(data)-skip)//4}I', data, skip)):
            if word & 1:
                words.setdefault(word & ~1, []).append(start+skip+4*i)
    image._reference_cache = branches, words
    return branches, words


def _short_branch_targets(data, base):
    """Targets of 16-bit branches in a nearby window."""
    for at in range(0, len(data)-1, 2):
        hw = data[at] | data[at+1] << 8
        pc = base+at+4
        if hw >> 12 == 0b1101 and (hw >> 8) & 0xF < 0xE:
            yield base+at, pc+(((hw & 0xFF) ^ 0x80)-0x80)*2
        elif hw >> 11 == 0b11100:
            yield base+at, pc+(((hw & 0x7FF) ^ 0x400)-0x400)*2
        elif hw & 0xF500 == 0xB100:
            yield base+at, pc+(((hw >> 9) & 1) << 6 | ((hw >> 3) & 0x1F) << 1)


def _readable(image, address, size):
    """As many bytes as exist from address, up to size."""
    while size > 0:
        try:
            return image.read(address, size)
        except ImageError:
            size -= 2
    return b''


def check_entry_hook(image, address, not_pointers=()):
    """Return (displaced_bytes, instructions) or raise ImageError saying why this site is refused."""
    need = jump_size(address)
    for at in (address, address+need-1):
        zone = protected(image, at)
        if zone:
            raise ImageError(f'0x{address:08X} is inside {zone}. This code can erase the loader and brick the unit: no hook goes here')
    code = _readable(image, address, 32)
    for back in range(2, 10, 2):
        before = _readable(image, address-back, 2) if address >= back else b''
        if len(before) == 2 and before[1] == 0xBF and before[0] & 0xF:
            raise ImageError(f'0x{address:08X}: an IT instruction at 0x{address-back:08X} may cover this site, so this is inside an IT block')
    picked = []
    size = 0
    for ins in _disassembler().disasm(code, address):
        if size >= need:
            break
        picked.append(ins)
        size += ins.size
    if size < need:
        raise ImageError(f'0x{address:08X}: could not decode {need} bytes of instructions')
    # The patch rewrites every displaced byte, which can be two more than the jump when the last instruction is 32-bit.
    # The check above only saw the jump's own span, so a site just before guarded code could still overwrite its first bytes.
    for at in range(address, address+size, 2):
        zone = protected(image, at)
        if zone:
            raise ImageError(f'0x{address:08X}: the displaced bytes reach 0x{at:08X}, inside {zone}. This code can erase the loader and brick the unit: no hook goes here')
    if picked[0].mnemonic.split('.')[0] != 'push':
        raise ImageError(f'0x{address:08X}: first instruction is {picked[0].mnemonic}, not push, so this does not look like a function entry')
    for ins in picked:
        if _is_control_flow(ins):
            raise ImageError(f'0x{ins.address:08X}: {ins.mnemonic} {ins.op_str} changes control flow and cannot be displaced')
        if _uses_pc(ins):
            raise ImageError(f'0x{ins.address:08X}: {ins.mnemonic} {ins.op_str} depends on its address and cannot be displaced')
    _nothing_lands_inside(image, address, size, not_pointers)
    return image.read(address, size), picked


def _nothing_lands_inside(image, address, size, not_pointers=()):
    """No direct branch or stored pointer anywhere in the image may land inside the replaced bytes, past their first."""
    lo, hi = address+1, address+size
    branches, words = _references(image)
    for target in range(lo+1 if lo % 2 else lo, hi, 2):
        if target in branches:
            raise ImageError(f'0x{branches[target]:08X} branches to 0x{target:08X}, inside the bytes this hook would replace')
        for source in words.get(target, ()):
            if source not in not_pointers:
                raise ImageError(f'the word at 0x{source:08X} could point to 0x{target:08X}, inside the bytes this hook would replace. '
                                 'If it is data, look at it and declare it in not_pointers with the reason')
    window = max(0, address-SHORT_RANGE)
    for source, target in _short_branch_targets(_readable(image, window, address+SHORT_RANGE-window), window):
        if lo <= target < hi:
            raise ImageError(f'0x{source:08X} branches to 0x{target:08X}, inside the bytes this hook would replace')


def _whole_instructions(image, address, need):
    """The instructions that cover at least `need` bytes from address, refusing a site inside an IT block or in guarded code."""
    for back in range(2, 10, 2):
        before = _readable(image, address-back, 2) if address >= back else b''
        if len(before) == 2 and before[1] == 0xBF and before[0] & 0xF:
            raise ImageError(f'0x{address:08X}: an IT instruction at 0x{address-back:08X} may cover this site, so this is inside an IT block')
    picked, size = [], 0
    for ins in _disassembler().disasm(_readable(image, address, 32), address):
        if size >= need:
            break
        picked.append(ins)
        size += ins.size
    if size < need:
        raise ImageError(f'0x{address:08X}: could not decode {need} bytes of instructions')
    for at in range(address, address+size, 2):
        zone = protected(image, at)
        if zone:
            raise ImageError(f'0x{address:08X}: the replaced bytes reach 0x{at:08X}, inside {zone}. This code can erase the loader and brick the unit: no hook goes here')
    return picked, size


def check_jump_hook(image, address, not_pointers=()):
    """A jump hook sends the firmware to a mod function at this address and never comes back by itself: the replaced
    instructions are not run again. The mod does their work, or jumps on to whatever comes next (`resume`).

    Checked from bytes as for an entry hook: whole instructions, not in an IT block, not in guarded code, and nothing branches
    or points into the replaced bytes past the first. Unlike an entry hook the site may be anywhere in a function, and the
    replaced instructions may branch or read relative to PC, since they no longer run. Returns the replaced bytes."""
    if address & 1:
        raise ImageError('a Thumb code address must be even')
    _, size = _whole_instructions(image, address, jump_size(address))
    _nothing_lands_inside(image, address, size, not_pointers)
    return image.read(address, size)


def jump_hook_patch(image, address, target, not_pointers=()):
    replaced = check_jump_hook(image, address, not_pointers)
    jump = jump_patch(address, target)
    return dict(address=address, before=replaced, after=jump+bytes.fromhex('00bf')*((len(replaced)-len(jump))//2))


def check_byte_patch(image, address, before, after, family=None):
    """A byte patch changes declared bytes into others of the same length: an immediate in an instruction, a limit, a table of
    pointers, a call made into NOPs. The author states both sides; the build checks the image holds `before`, that no byte is
    in guarded code, that `after` neither branches into guarded code nor holds a pointer to it, and on DOOM OS that it does
    not cover a veneer word DOOM rewrites while it starts. What the new bytes mean is the author's claim, to be tested."""
    if not before or len(before) != len(after):
        raise ImageError(f'0x{address:08X}: a byte patch keeps its size and needs both sides')
    if before == after:
        raise ImageError(f'0x{address:08X}: the patch changes nothing')
    for at in range(address, address+len(before)):
        zone = protected(image, at)
        if zone:
            raise ImageError(f'0x{address:08X}: the patch reaches 0x{at:08X}, inside {zone}. Only a disable hook may change that code')
    if image.read(address, len(before)) != before:
        raise ImageError(f'0x{address:08X} does not hold {before.hex()} on this base')
    if address % 2 == 0:
        for ins in _disassembler().disasm(after, address):
            if ins.mnemonic.split('.')[0] in BRANCHES and ins.operands and ins.operands[-1].type == cs_arm.ARM_OP_IMM:
                zone = protected(image, ins.operands[-1].imm & 0xFFFFFFFF)
                if zone:
                    raise ImageError(f'0x{ins.address:08X}: the new bytes branch into {zone}: refused')
    for at in range((-address) % 4, len(after)-3, 4):
        value = int.from_bytes(after[at:at+4], 'little')
        if value & 1 and protected(image, value):
            raise ImageError(f'0x{address+at:08X}: the new bytes hold a pointer to {protected(image, value)}: refused')
    if family == 'doom-os':
        for word in range(address & ~3, address+len(before), 4):
            try:
                if image.u32(word-4) == VENEER:
                    raise ImageError(f'0x{word:08X} is a DOOM OS veneer word, which DOOM rewrites while it starts: a patch in the file would not last')
            except ImageError as e:
                if 'veneer' in str(e):
                    raise


def check_disable_hook(image, address):
    """A disable hook makes one factory service routine that can erase the loader return at once: its first four bytes become
    movs r0,#0; bx lr. Allowed only at the entry of the routines in image.DISABLEABLE, and only where this image holds the
    guarded bytes there. Returns the four bytes it replaces or raises ImageError saying why it is refused.

    This takes a way to lose the loader away; it adds none. A caller that runs the routine gets 0 back and nothing is erased."""
    if address not in DISABLEABLE:
        listed = ', '.join(f'0x{a:08X}' for a in DISABLEABLE)
        raise ImageError(f'0x{address:08X}: a disable hook goes only at the entry of a guarded service routine ({listed})')
    zone = protected(image, address)
    if not zone or not zone.startswith(f'0x{address:08X}'):
        raise ImageError(f'0x{address:08X} does not hold the guarded routine on this image, so switching it off is not known to be safe here')
    return image.read(address, len(RETURN_ZERO))


VENEER = 0xF000F8DF  # ldr.w pc, [pc]: the word after it is where the veneer jumps


def check_word_hook(image, address, expect, family=None):
    """A word hook replaces one aligned word that holds a Thumb code pointer, such as a vector, a table entry or a vtable slot,
    with the address of a mod function. Returns the word's present value or raises ImageError saying why this word is refused.

    Checked from bytes: the word is aligned and mapped, holds exactly the value the mod's author saw there, and that value is a
    Thumb address of code that exists in this image and is not code that can erase the loader. Refused on DOOM OS: a word right
    after a DOOM veneer, which DOOM OS rewrites while it starts (hk.doom.veneers-rewritten), so a patch in the file would not last.
    Not visible from bytes: who else reads the word, and whether some code writes it at run time. The mod function is called
    exactly as the original would be, with its arguments, context and stack, and must keep the original's contract.
    """
    if address % 4:
        raise ImageError(f'0x{address:08X}: a word hook needs a word-aligned address')
    zone = protected(image, address)
    if zone:
        raise ImageError(f'0x{address:08X} is inside {zone}. This code can erase the loader and brick the unit: no hook goes here')
    value = image.u32(address)
    if value != expect:
        raise ImageError(f'0x{address:08X} holds 0x{value:08X}, not the 0x{expect:08X} the mod expects: this is not that word on this base')
    if not value & 1:
        raise ImageError(f'0x{address:08X} holds 0x{value:08X}, which is not a Thumb code address: a word hook replaces pointers to code only')
    zone = protected(image, value)
    if zone:
        raise ImageError(f'0x{address:08X} points to {zone}. Redirecting a pointer to code that can erase the loader is hooking it: refused')
    try:
        image.read(value & ~1, 2)
    except ImageError:
        raise ImageError(f'0x{address:08X} holds 0x{value:08X}, which is not inside this image, so it is not code the firmware carries') from None
    if family == 'doom-os':
        try:
            before = image.u32(address-4)
        except ImageError:
            before = None
        if before == VENEER:
            raise ImageError(f'0x{address:08X} is the word of a DOOM OS veneer at 0x{address-4:08X}. DOOM OS rewrites these words while it starts '
                             '(hk.doom.veneers-rewritten), so a patch in the file would not last: hook somewhere DOOM OS leaves alone')
    return value


def stub_source(index, address, function, displaced):
    """Assembly for one stub. The function sees the hooked function's r0 to r3 and whatever it does to its copies is undone. The displaced instructions are emitted as raw bytes, so they stay exactly as they were."""
    back = address+len(displaced)
    raw = ', '.join(f'0x{b:02x}' for b in displaced)
    return f"""
    .global lab404_stub_{index}
    .type lab404_stub_{index}, %function
    .thumb_func
lab404_stub_{index}:
    push {{r0, r1, r2, r3, ip, lr}}
    mrs r0, apsr
    push {{r0, r1}}
    ldr r0, [sp, #8]
    bl {function}
    pop {{r0, r1}}
    msr apsr_nzcvqg, r0
    pop {{r0, r1, r2, r3, ip, lr}}
    .byte {raw}
    ldr.w pc, .Lback_{index}
    .balign 4
.Lback_{index}:
    .word 0x{back | 1:08X}
"""


def plan_patch(image, address, stub, not_pointers=()):
    """The guarded patch for one site: replaces whole instructions, padding any spare bytes with NOPs."""
    displaced, _ = check_entry_hook(image, address, not_pointers)
    jump = jump_patch(address, stub)
    spare = len(displaced)-len(jump)
    if spare % 2:
        raise ImageError('odd padding')
    return dict(address=address, before=displaced, after=jump+bytes.fromhex('00bf')*(spare//2))


__all__ = ['Image', 'check_byte_patch', 'check_disable_hook', 'check_entry_hook', 'check_jump_hook', 'check_word_hook', 'jump_hook_patch', 'jump_patch', 'jump_size', 'plan_patch', 'stub_source']
