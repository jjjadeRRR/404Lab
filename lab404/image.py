"""Read an SP-404MKII APP1 image by runtime address, and extend it without moving anything.

APP1 layout [BYTES]: the file sits at FLASH. The 8 bytes at 0x80 hold the scatter table bounds, relative to 0x80. Each row is
(load, runtime, size, handler), and the handler says whether startup copies, decompresses or zeroes that region.
"""
import hashlib
import struct

FLASH = 0x60080000
COPY, ZERO, DECOMPRESS = 0x600800E4, 0x60080100, 0x60080088
FLASH_LIMIT = 0x603FF000
APP1_ROOM = FLASH_LIMIT-FLASH  # 0x37F000: what the loader erases for APP1 before writing it, with no check of the file's length (hw.update.app1-range)
# Factory service code and flash primitives inside APP1 that can erase the loader (hw.service.loader-erase).
# (address, how many of its first bytes are compared, SHA-256 of those bytes, size guarded, what it is). The hash
# stands for the bytes so the repository carries no firmware code; `lab404 read FILE ADDRESS 8 --sha256` recomputes it.
PROTECTED = ((0x80065838, 8, 'a1d67c24114605b938f05cae78f7f9082c1cf4e0bd06ebcbe8a01e05effc7259', 0x100, 'service command that erases the loader before writing a new one'),
             (0x80064E48, 8, '127b0503b4520162bb63b41fec1845fe03d5cfd5d8b4d0f25f133385fe4fb6fb', 0x22, 'service command that erases the whole flash chip'),
             (0x80064E70, 8, '7f603682e12aca6f5504b10f0f87350503a0dd4997a9c705cd68a3a6a92a4e5d', 0x100, 'service command that rewrites the flash from a factory file'),
             (0x8017D3C8, 8, '0d5341a464caf65d5dc98c3b98a69e111ef7206eaac0d4cb816d3e888e857afe', 0x100, 'whole-chip erase and write of a factory file'),
             (0x8019D348, 8, '5872028ffe00bbcfe49f3ef2bf9bad43f85c6c5697eb2b2a11db1ff1a29c4014', 0x80, 'flash chip erase'),
             (0x8001ACB0, 8, '0e1ad64b707954cadf0d74c9e449f8de063760f880409bcf27c2ac26d114eaf6', 0x80, 'flash sector erase'),
             (0x800D5FD8, 8, 'aa7c6802c6f35c2ffcfc0b76c820738a71e65f7b2b86aba346a2e62fb7371bbb', 0x80, 'flash page program'))
FLEXSPI = (0x60000000, 0x70000000)
HANDLER_NAMES = {COPY: 'COPY', ZERO: 'ZERO', DECOMPRESS: 'DECOMPRESS'}
MAX_DECOMPRESSED = 1024*1024


class ImageError(ValueError):
    """The bytes are not a usable APP1, or a request does not fit it."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def matches(image, address, expect):
    """Do the bytes at address match what a record expects? A record holds either 'hex' (the bytes themselves, for
    local use) or 'size' and 'sha256' (a fingerprint, so a shared record carries no firmware). Returns (same, sha256 of
    what is there). Raises ImageError when the address is not in the image."""
    if 'sha256' in expect:
        got = image.read(address, int(expect['size']))
        return sha256(got) == expect['sha256'].lower(), sha256(got)
    want = bytes.fromhex(expect['hex'])
    got = image.read(address, len(want))
    return got == want, sha256(got)


def table_bounds(raw):
    if len(raw) < 0x88:
        raise ImageError('too short to hold a scatter header')
    start, end = struct.unpack_from('<2I', raw, 0x80)
    start += 0x80
    end += 0x80
    if not 0x88 <= start < end <= len(raw) or (end-start) % 16 or start % 4:
        raise ImageError('invalid scatter table bounds')
    return start, end


def scatter(raw):
    start, end = table_bounds(raw)
    rows = []
    for at in range(start, end, 16):
        load, runtime, size, handler = struct.unpack_from('<4I', raw, at)
        if handler not in HANDLER_NAMES or not size or runtime+size > 0x100000000:
            raise ImageError(f'unknown scatter row at file offset 0x{at:X}')
        if handler == COPY and not FLASH <= load <= FLASH+len(raw)-size:
            raise ImageError(f'COPY row at 0x{at:X} points outside the file')
        if handler == DECOMPRESS and not FLASH <= load < FLASH+len(raw):
            raise ImageError(f'compressed row at 0x{at:X} points outside the file')
        rows.append((load, runtime, size, handler))
    return rows


def decompress(source, size):
    """The startup data format: literal runs, zero runs and back references. Refuses overruns."""
    if not 0 <= size <= MAX_DECOMPRESSED:
        raise ImageError('decompressed size out of bounds')
    source = memoryview(source).cast('B')
    out = bytearray()
    pos = 0

    def byte():
        nonlocal pos
        if pos >= len(source):
            raise ImageError('truncated compressed data')
        value = source[pos]
        pos += 1
        return value

    while len(out) < size:
        token = byte()
        literal = token & 7
        count = token >> 4
        if literal == 0:
            literal = byte()
        if count == 0:
            count = byte()
        if literal == 0:
            raise ImageError('zero literal count in compressed data')
        literal -= 1
        if pos+literal > len(source):
            raise ImageError('truncated literal in compressed data')
        copied = count+2 if token & 8 else count
        if len(out)+literal+copied > size:
            raise ImageError('compressed data overruns its region')
        out.extend(source[pos:pos+literal])
        pos += literal
        if token & 8:
            distance = byte()
            if not 1 <= distance <= len(out):
                raise ImageError('invalid back reference in compressed data')
            for _ in range(copied):
                out.append(out[-distance])
        else:
            out.extend(bytes(count))
    return bytes(out), pos


def file_offset(raw, address, size):
    """Where in the file these runtime bytes come from. Only flash and COPY regions map to one place."""
    if FLASH <= address and address+size <= FLASH+len(raw):
        return address-FLASH
    hits = [load-FLASH+address-runtime for load, runtime, n, handler in scatter(raw)
            if handler == COPY and runtime <= address and address+size <= runtime+n]
    if len(hits) != 1:
        raise ImageError(f'0x{address:08X}+{size} has no single COPY or flash mapping')
    return hits[0]


class Image:
    """An APP1 as it looks after startup has processed its scatter table."""

    def __init__(self, raw, name=''):
        self.raw = bytes(raw)
        self.name = name
        self.sha256 = sha256(self.raw)
        self.rows = scatter(self.raw)
        self.segments = [(FLASH, self.raw, 'FLASH')]  # (start, bytes, label) in startup order: a later row overwrites an earlier one
        for load, runtime, size, handler in self.rows:
            if handler == COPY:
                self.segments.append((runtime, self.raw[load-FLASH:load-FLASH+size], 'COPY'))
            elif handler == DECOMPRESS:
                self.segments.append((runtime, decompress(self.raw[load-FLASH:], size)[0], 'DECOMPRESS'))
            else:
                self.segments.append((runtime, bytes(size), 'ZERO'))

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            return cls(f.read(), str(path))

    def read(self, address, size):
        for start, data, _ in reversed(self.segments):
            if start <= address and address+size <= start+len(data):
                return data[address-start:address-start+size]
            if max(start, address) < min(start+len(data), address+size):
                raise ImageError(f'0x{address:08X}+{size} crosses an overlap or the end of a region at 0x{start:08X}')
        raise ImageError(f'0x{address:08X}+{size} is not inside one mapped region')

    def u32(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def find(self, needle):
        hits = []
        for start, data, label in self.segments:
            at = data.find(needle)
            while at >= 0:
                hits.append((start+at, label))
                at = data.find(needle, at+1)
        return hits


def room(raw):
    """Bytes an APP1 may still grow by before it no longer fits what the loader erases."""
    return APP1_ROOM-len(raw)


def protected(image, address):
    """What this address belongs to if it is inside code that can erase the loader on this image, else None.
    The bytes are compared, so on a firmware where these addresses hold something else nothing is claimed."""
    address &= ~1
    for start, length, digest, size, what in PROTECTED:
        if start <= address < start+size:
            try:
                same = matches(image, start, {'size': length, 'sha256': digest})[0]
            except ImageError:
                same = False
            if same:
                return f'0x{start:08X}, {what}'
    return None


def extend(raw, runtime, payload, patches=()):
    """Append a COPY row holding payload at runtime, plus equal-length guarded patches.

    Every existing file offset stays where it was. Only the table pointers at 0x80 and the declared patch bytes change, and the
    result is checked against that claim before it is returned.
    """
    if not payload or len(payload) % 4 or runtime % 4 or not 0 <= runtime < runtime+len(payload) <= 0x100000000:
        raise ImageError('invalid payload placement')
    if max(runtime, FLEXSPI[0]) < min(runtime+len(payload), FLEXSPI[1]):
        raise ImageError('the payload destination is in flash, which startup cannot write')
    rows = scatter(raw)
    old_table = table_bounds(raw)
    for _, start, size, _ in rows:
        if max(start, runtime) < min(start+size, runtime+len(payload)):
            raise ImageError(f'payload overlaps the region at 0x{start:08X}')
    out = bytearray(raw)
    allowed = [(0x80, 0x88)]
    for patch in patches:
        before, after = patch['before'], patch['after']
        if not before or len(before) != len(after):
            raise ImageError('a patch must keep its size')
        at = file_offset(raw, patch['address'], len(before))
        end = at+len(before)
        if max(at, old_table[0]) < min(end, old_table[1]) or max(at, 0x80) < min(end, 0x88):
            raise ImageError('a patch may not touch scatter metadata')
        if any(max(at, a) < min(end, b) for a, b in allowed):
            raise ImageError(f'overlapping patches at 0x{patch["address"]:08X}')
        if raw[at:end] != before:
            raise ImageError(f'original bytes differ at 0x{patch["address"]:08X}: wrong base image')
        out[at:end] = after
        allowed.append((at, end))
    payload_at = (len(out)+15) & ~15
    out += bytes(payload_at-len(out))+payload
    table_at = (len(out)+15) & ~15
    out += bytes(table_at-len(out))
    new_rows = rows+[(FLASH+payload_at, runtime, len(payload), COPY)]
    for row in new_rows:
        out += struct.pack('<4I', *row)
    struct.pack_into('<2I', out, 0x80, table_at-0x80, len(out)-0x80)
    if FLASH+len(out) > FLASH_LIMIT:
        raise ImageError(f'image exceeds the APP1 flash limit: {len(out)} bytes, and the loader erases only {APP1_ROOM} before it writes')
    result = bytes(out)
    if scatter(result) != new_rows:
        raise AssertionError('scatter table did not survive')
    for i, (a, b) in enumerate(zip(raw, result)):
        if a != b and not any(lo <= i < hi for lo, hi in allowed):
            raise AssertionError(f'undeclared change at file offset 0x{i:X}')
    return result
