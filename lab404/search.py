"""Who uses this address, and where are these bytes. Answers come from bytes alone, at runtime addresses.

Seen: 32-bit Thumb BL and B, and aligned words holding the address with or without the Thumb bit.
Not seen: calls through a register, addresses built by movw/movt or computed at run time, and 16-bit branches. An empty answer is not proof that nothing uses an address.
A word that merely equals the address is reported too: it can be data. Look before relying on it.
"""
import struct

from .hooks import _wide_branch_target
from .image import COPY, DECOMPRESS, FLASH, decompress


def _regions(image):
    """(start, bytes) to search, each byte once. The file itself is searched only where startup does not load it elsewhere:
    a COPY row's bytes are reported at the address they run at, and compressed bytes mean nothing until unpacked."""
    loaded = []
    for load, _, size, handler in image.rows:
        if handler == COPY:
            loaded.append((load-FLASH, load-FLASH+size))
        elif handler == DECOMPRESS:
            loaded.append((load-FLASH, load-FLASH+decompress(image.raw[load-FLASH:], size)[1]))
    out, at = [], 0
    for lo, hi in sorted(loaded):
        if lo > at:
            out.append((FLASH+at, image.raw[at:lo]))
        at = max(at, hi)
    if at < len(image.raw):
        out.append((FLASH+at, image.raw[at:]))
    out += [(start, data) for start, data, label in image.segments if label in ('COPY', 'DECOMPRESS')]
    return out


def xrefs(image, address):
    """Sorted [(source address, 'call' | 'branch' | 'pointer')] for everything visible that leads to address."""
    target = address & ~1
    found = set()
    for start, data in _regions(image):
        skip = -start % 2
        halves = struct.unpack_from(f'<{(len(data)-skip)//2}H', data, skip)
        for i in range(len(halves)-1):
            if halves[i] >> 11 == 0b11110 and halves[i+1] & 0x8000:
                source = start+skip+2*i
                if _wide_branch_target(halves[i], halves[i+1], source) == target:
                    found.add((source, 'call' if halves[i+1] & 0x4000 else 'branch'))
        for value in (target, target | 1):
            needle = struct.pack('<I', value)
            at = data.find(needle)
            while at >= 0:
                if (start+at) % 4 == 0:
                    found.add((start+at, 'pointer'))
                at = data.find(needle, at+1)
    return sorted(found)


def find_bytes(image, needle):
    """Sorted runtime addresses where these bytes are."""
    found = set()
    for start, data in _regions(image):
        at = data.find(needle)
        while at >= 0:
            found.add(start+at)
            at = data.find(needle, at+1)
    return sorted(found)
