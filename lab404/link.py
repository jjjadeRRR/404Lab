"""A small static linker for mod payloads, so clang is the only external build tool.

Lays the allocatable sections of ELF32 ARM objects out at one base address, resolves symbols between them and applies the
relocations clang emits for Cortex-M7 Thumb code. An unknown relocation type stops the build: it is never skipped.

Payloads live far from firmware code, beyond the reach of a Thumb branch, so a call to a firmware function goes through a veneer
at the start of the payload. Veneers change no registers.
"""
import struct

SHF_ALLOC, SHF_EXECINSTR, SHF_WRITE = 2, 4, 1
SHT_PROGBITS, SHT_SYMTAB, SHT_NOBITS, SHT_REL = 1, 2, 8, 9
SHN_UNDEF, SHN_ABS, SHN_COMMON = 0, 0xFFF1, 0xFFF2
R_ABS32, R_REL32, R_THM_CALL, R_THM_JUMP24, R_TARGET1 = 2, 3, 10, 30, 38
R_THM_MOVW_ABS_NC, R_THM_MOVT_ABS, R_THM_JUMP19, R_THM_JUMP11, R_V4BX, R_NONE = 47, 48, 51, 102, 40, 0
STB_GLOBAL, STB_WEAK, STT_FUNC = 1, 2, 2
ORDER = ('text', 'rodata', 'data', 'bss')
BRANCH_KINDS = (R_THM_CALL, R_THM_JUMP24, R_THM_JUMP19, R_THM_JUMP11)


class LinkError(ValueError):
    pass


class Section:
    def __init__(self, obj, index, name, kind, flags, data, size, align):
        self.obj, self.index, self.name, self.kind, self.flags = obj, index, name, kind, flags
        self.data = bytearray(data)
        self.size, self.align = size, align
        self.address = None


class Obj:
    def __init__(self, path, blob):
        self.path = path
        if blob[:4] != b'\x7fELF' or blob[4] != 1 or blob[5] != 1 or struct.unpack_from('<H', blob, 18)[0] != 40:
            raise LinkError(f'{path}: not a little-endian ELF32 ARM object')
        shoff = struct.unpack_from('<I', blob, 32)[0]
        shentsize, shnum, shstrndx = struct.unpack_from('<3H', blob, 46)
        heads = [struct.unpack_from('<10I', blob, shoff+i*shentsize) for i in range(shnum)]
        strings = blob[heads[shstrndx][4]:heads[shstrndx][4]+heads[shstrndx][5]]

        def name_at(table, at):
            return table[at:table.index(b'\0', at)].decode()

        self.sections = {}
        self.symbols = []
        self.relocs = []
        for i, (name, kind, flags, _, offset, size, link, info, align, _) in enumerate(heads):
            label = name_at(strings, name)
            if kind in (SHT_PROGBITS, SHT_NOBITS) and flags & SHF_ALLOC:
                data = b'' if kind == SHT_NOBITS else blob[offset:offset+size]
                self.sections[i] = Section(self, i, label, kind, flags, data, size, max(align, 1))
            elif kind == SHT_SYMTAB:
                symstr = blob[heads[link][4]:heads[link][4]+heads[link][5]]
                for at in range(offset, offset+size, 16):
                    sym_name, value, sym_size, st_info, _, shndx = struct.unpack_from('<IIIBBH', blob, at)
                    self.symbols.append((name_at(symstr, sym_name), value, st_info, shndx))
            elif kind == SHT_REL:
                self.relocs.append((info, [struct.unpack_from('<2I', blob, at) for at in range(offset, offset+size, 8)]))


def _bucket(section):
    if section.kind == SHT_NOBITS:
        return 'bss'
    if section.flags & SHF_EXECINSTR:
        return 'text'
    return 'data' if section.flags & SHF_WRITE else 'rodata'


def _thumb_branch_addend(data, at, kind):
    if kind == R_THM_JUMP11:
        value = (struct.unpack_from('<H', data, at)[0] & 0x7FF) << 1
        return value-(1 << 12) if value & (1 << 11) else value
    hw1, hw2 = struct.unpack_from('<2H', data, at)
    sign, j1, j2 = (hw1 >> 10) & 1, (hw2 >> 13) & 1, (hw2 >> 11) & 1
    if kind == R_THM_JUMP19:
        value = (sign << 20) | (j2 << 19) | (j1 << 18) | ((hw1 & 0x3F) << 12) | ((hw2 & 0x7FF) << 1)
        return value-(1 << 21) if sign else value
    i1, i2 = 1 ^ j1 ^ sign, 1 ^ j2 ^ sign
    value = (sign << 24) | (i1 << 23) | (i2 << 22) | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1)
    return value-(1 << 25) if sign else value


def _put_thumb_branch(data, at, offset, kind):
    offset &= ~1
    if kind == R_THM_JUMP11:
        if not -2048 <= offset < 2048:
            raise LinkError('short branch out of range')
        old = struct.unpack_from('<H', data, at)[0]
        struct.pack_into('<H', data, at, (old & 0xF800) | ((offset >> 1) & 0x7FF))
        return
    hw1, hw2 = struct.unpack_from('<2H', data, at)
    sign = 1 if offset < 0 else 0
    if kind == R_THM_JUMP19:
        if not -(1 << 20) <= offset < (1 << 20):
            raise LinkError('conditional branch out of range')
        j1, j2 = (offset >> 18) & 1, (offset >> 19) & 1
        hw1 = (hw1 & 0xFBC0) | (sign << 10) | ((offset >> 12) & 0x3F)
        hw2 = (hw2 & 0xD000) | (j1 << 13) | (j2 << 11) | ((offset >> 1) & 0x7FF)
    else:
        if not -(1 << 24) <= offset < (1 << 24):
            raise LinkError('branch out of range')
        i1, i2 = (offset >> 23) & 1, (offset >> 22) & 1
        j1, j2 = 1 ^ i1 ^ sign, 1 ^ i2 ^ sign
        hw1 = (hw1 & 0xF800) | (sign << 10) | ((offset >> 12) & 0x3FF)
        hw2 = (hw2 & 0xD000) | (j1 << 13) | (j2 << 11) | ((offset >> 1) & 0x7FF)
    struct.pack_into('<2H', data, at, hw1, hw2)


def _put_movw_movt(data, at, value):
    hw1, hw2 = struct.unpack_from('<2H', data, at)
    hw1 = (hw1 & 0xFBF0) | ((value >> 12) & 0xF) | (((value >> 11) & 1) << 10)
    hw2 = (hw2 & 0x8F00) | (((value >> 8) & 7) << 12) | (value & 0xFF)
    struct.pack_into('<2H', data, at, hw1, hw2)


def _addend_movw(data, at):
    hw1, hw2 = struct.unpack_from('<2H', data, at)
    value = ((hw1 & 0xF) << 12) | (((hw1 >> 10) & 1) << 11) | (((hw2 >> 12) & 7) << 8) | (hw2 & 0xFF)
    return value-0x10000 if value & 0x8000 else value


def _defined(obj):
    return {name for name, _, info, shndx in obj.symbols if name and info >> 4 in (STB_GLOBAL, STB_WEAK) and shndx in obj.sections}


def _far_branches(objects, reachable_elsewhere):
    """Names that code in these objects branches to but that live outside them: firmware functions, or code in another region."""
    names = set()
    for obj in objects:
        for _, rows in obj.relocs:
            for _, info in rows:
                name, _, _, shndx = obj.symbols[info >> 8]
                if info & 0xFF in BRANCH_KINDS and shndx == SHN_UNDEF and name in reachable_elsewhere:
                    names.add(name)
    return sorted(names)


def link(object_blobs, base, externals=None):
    """Return (payload bytes, {symbol: address}). object_blobs is [(name, bytes)]; externals are firmware addresses."""
    blobs, symbols = link_regions([(base, object_blobs)], externals)
    return blobs[0], symbols


def link_regions(regions, externals=None, spans=None):
    """Link objects that live in several places at once, such as a payload in SDRAM and a block of code in flash.

    regions is [(base, [(name, bytes) or (name, bytes, fixed address)])]; returns ([bytes per region], {symbol: address}).
    Symbols are shared between regions. An object with a fixed address has all its sections laid out from there, in the order
    text, rodata, data, bss, for code that other code reaches by a literal address; everything else flows around it. A branch to
    anything outside its own region (firmware, or another region) goes through a veneer, since regions are far apart."""
    externals = dict(externals or {})
    for name, address in externals.items():
        if not address & 1:
            raise LinkError(f'firmware function {name} needs a Thumb address, with bit 0 set')
    groups = []
    for base, object_blobs in regions:
        if base % 4:
            raise LinkError('a region base must be word aligned')
        objects = []
        for entry in object_blobs:
            obj = Obj(entry[0], entry[1])
            obj.fixed = entry[2] if len(entry) > 2 else None
            objects.append(obj)
        groups.append((base, objects))
    defined = [set().union(*[_defined(obj) for obj in objects]) for _, objects in groups]
    layouts = []
    for index, (base, objects) in enumerate(groups):
        elsewhere = set(externals).union(*[names for i, names in enumerate(defined) if i != index])
        veneer_names = _far_branches(objects, elsewhere)
        taken = []

        def free_at(cursor, size, align):
            at = (cursor+align-1) & ~(align-1)
            while True:
                clash = next((hi for lo, hi in taken if lo < at+size and at < hi), None)
                if clash is None:
                    return at
                at = (clash+align-1) & ~(align-1)
        placed = {kind: [] for kind in ORDER}
        end = base
        for obj in objects:
            if obj.fixed is None:
                continue
            if obj.fixed < base or obj.fixed % 2:
                raise LinkError(f'{obj.path}: fixed address 0x{obj.fixed:08X} is not in its region from 0x{base:08X}')
            cursor = obj.fixed
            for kind in ORDER:
                for section in obj.sections.values():
                    if _bucket(section) == kind:
                        cursor = (cursor+section.align-1) & ~(section.align-1)
                        section.address = cursor
                        cursor += section.size
                        placed[kind].append(section)
            if any(lo < cursor and obj.fixed < hi for lo, hi in taken):
                raise LinkError(f'{obj.path}: its fixed place 0x{obj.fixed:08X}-0x{cursor:08X} overlaps another fixed object')
            taken.append((obj.fixed, cursor))
            if spans is not None:
                spans[obj.path] = (obj.fixed, cursor)
            end = max(end, cursor)
        veneer_at = free_at(base, 8*len(veneer_names), 4)
        taken.append((veneer_at, veneer_at+8*len(veneer_names)))
        veneers = {name: veneer_at+8*i for i, name in enumerate(veneer_names)}
        cursor = veneer_at+8*len(veneer_names)
        for kind in ORDER:
            for obj in objects:
                if obj.fixed is not None:
                    continue
                for section in obj.sections.values():
                    if _bucket(section) == kind:
                        section.address = free_at(cursor, section.size, section.align)
                        cursor = section.address+section.size
                        placed[kind].append(section)
        end = max(end, cursor, veneer_at+8*len(veneer_names))
        layouts.append((base, objects, veneer_names, veneers, placed, end))
    strong, weak, thumb = {}, {}, set(externals)
    tables = {}
    for _, objects, _, _, _, _ in layouts:
        for obj in objects:
            table = []
            for name, value, info, shndx in obj.symbols:
                if shndx == SHN_COMMON:
                    raise LinkError(f'{obj.path}: common symbol {name}: build with -fno-common')
                address = value if shndx == SHN_ABS else obj.sections[shndx].address+value if shndx in obj.sections else None
                table.append((name, address, info, shndx))
                if address is None or not name or info >> 4 not in (STB_GLOBAL, STB_WEAK):
                    continue
                if info & 0xF == STT_FUNC:
                    thumb.add(name)
                if info >> 4 == STB_WEAK:
                    weak.setdefault(name, address)
                elif name in strong or name in externals:
                    raise LinkError(f'symbol {name} is defined twice')
                else:
                    strong[name] = address
            tables[obj] = table
    symbols = {**weak, **externals, **strong}
    out_blobs = []
    for base, objects, veneer_names, veneers, placed, cursor in layouts:
        for obj in objects:
            _relocate(obj, tables[obj], symbols, thumb, veneers)
        out = bytearray(cursor-base)
        for name in veneer_names:
            target, at = symbols[name], veneers[name]-base
            if not target & 1:
                raise LinkError(f'a branch to {name}, which is not a Thumb function')
            out[at:at+8] = bytes.fromhex('dff800f0')+struct.pack('<I', target)
        for kind in ORDER[:3]:
            for section in placed[kind]:
                out[section.address-base:section.address-base+len(section.data)] = section.data
        out += bytes(-len(out) % 4)
        out_blobs.append(bytes(out))
    return out_blobs, symbols


def _relocate(obj, table, symbols, thumb, veneers):
    """Apply one object's relocations, branches to far names going through this region's veneers."""
    for target_index, rows in obj.relocs:
        section = obj.sections.get(target_index)
        if section is None:
            continue
        for at, info in rows:
            kind, sym = info & 0xFF, info >> 8
            if kind in (R_NONE, R_V4BX):
                continue
            name, address, st_info, shndx = table[sym]
            is_global = bool(name) and st_info >> 4 in (STB_GLOBAL, STB_WEAK)
            if is_global:
                if name not in symbols:
                    raise LinkError(f'{obj.path}: undefined symbol {name}')
                address = symbols[name]
                is_thumb = name in thumb
            else:
                is_thumb = st_info & 0xF == STT_FUNC
            # ABI: S is the symbol's address without its Thumb bit, T is that bit, and data relocations use (S + A) | T.
            symbol, t = (address & ~1, 1) if is_thumb else (address, 0)
            data = section.data
            pc = section.address+at
            if kind in BRANCH_KINDS:
                addend = _thumb_branch_addend(data, at, kind)
                if shndx == SHN_UNDEF and name in veneers:
                    if addend != -4:
                        raise LinkError(f'{obj.path}: branch to {name} with an offset: a veneer holds one address')
                    symbol = veneers[name]
                offset = symbol+addend-pc
                _put_thumb_branch(data, at, offset, kind)
            elif kind in (R_ABS32, R_TARGET1):
                value = (symbol+struct.unpack_from('<I', data, at)[0]) | t
                struct.pack_into('<I', data, at, value & 0xFFFFFFFF)
            elif kind == R_REL32:
                value = ((symbol+struct.unpack_from('<I', data, at)[0]) | t)-pc
                struct.pack_into('<I', data, at, value & 0xFFFFFFFF)
            elif kind == R_THM_MOVW_ABS_NC:
                _put_movw_movt(data, at, ((symbol+_addend_movw(data, at)) | t) & 0xFFFF)
            elif kind == R_THM_MOVT_ABS:
                _put_movw_movt(data, at, (((symbol+_addend_movw(data, at)) | t) >> 16) & 0xFFFF)
            else:
                raise LinkError(f'{obj.path}: relocation type {kind} against {name} is not supported')
