"""Shared test inputs. Firmware is never in the repository: tests needing an image skip without it."""
import os
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = Path(os.environ.get('LAB404_INPUTS', ROOT/'inputs'))
STOCK = INPUTS/'stock-5.52/SP404MKII_APP1.bin'
DOOM73 = INPUTS/'doom-0.7.3/SP404MKII_APP1.bin'
DOOM72 = INPUTS/'doom-0.7.2/SP404MKII_APP1.bin'
DOOM74 = INPUTS/'doom-0.7.4/SP404MKII_APP1.bin'
PROJECT_DRIVE = INPUTS/'project-drive.img'  # optional: an internal drive image holding one of the user's projects
FLASH, COPY, ZERO = 0x60080000, 0x600800E4, 0x60080100


def tiny_image(code=b'\x70\x47\x00\xbf'*4):
    """A minimal valid container: one COPY row at 0x1000 and one ZERO row. Not firmware."""
    head = bytearray(0x100)
    payload_at = len(head)
    body = bytes(code)
    table_at = payload_at+len(body)
    rows = struct.pack('<4I', FLASH+payload_at, 0x1000, len(body), COPY)+struct.pack('<4I', 0, 0x20000000, 0x100, ZERO)
    struct.pack_into('<2I', head, 0x80, table_at-0x80, table_at+len(rows)-0x80)
    return bytes(head)+body+rows


def rows_image(body, rows):
    """A container whose rows are given as (runtime, size, handler, offset_in_body)."""
    head = bytearray(0x100)
    table_at = 0x100+len(body)
    table = b''.join(struct.pack('<4I', FLASH+0x100+off if handler == COPY else 0, runtime, size, handler)
                     for runtime, size, handler, off in rows)
    struct.pack_into('<2I', head, 0x80, table_at-0x80, table_at+len(table)-0x80)
    return bytes(head)+body+table
