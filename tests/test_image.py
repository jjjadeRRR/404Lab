"""Container handling on a synthetic image, so these run without any firmware."""
import struct
import unittest

from lab404.image import COPY, FLASH, Image, ImageError, ZERO, decompress, extend, file_offset, scatter
from helpers import tiny_image


class Container(unittest.TestCase):
    def test_reads_by_runtime_address(self):
        image = Image(tiny_image(b'\x01\x02\x03\x04'))
        self.assertEqual(image.read(0x1000, 4), b'\x01\x02\x03\x04')
        self.assertEqual(image.read(0x20000000, 4), bytes(4))
        with self.assertRaises(ImageError):
            image.read(0x1002, 4)

    def test_refuses_broken_containers(self):
        good = tiny_image()
        for bad in (b'', good[:0x80], good[:-8]):
            with self.assertRaises(ImageError):
                Image(bad)
        wrong_handler = bytearray(good)
        wrong_handler[-4:] = struct.pack('<I', 0x12345678)
        with self.assertRaises(ImageError):
            scatter(bytes(wrong_handler))

    def test_extend_keeps_every_old_byte_outside_the_declared_changes(self):
        raw = tiny_image(b'\x70\x47\x00\xbf'*4)
        out = extend(raw, 0x83FD0000, b'\xAA'*8, [dict(address=0x1000, before=b'\x70\x47', after=b'\x00\xbf')])
        self.assertEqual(out[0x100:0x102], b'\x00\xbf')
        self.assertEqual(out[0x102:len(raw)], raw[0x102:])
        self.assertEqual(out[:0x80], raw[:0x80])
        rows = scatter(out)
        self.assertEqual(rows[:2], scatter(raw))
        self.assertEqual(rows[2][1:], (0x83FD0000, 8, COPY))
        self.assertEqual(Image(out).read(0x83FD0000, 8), b'\xAA'*8)

    def test_extend_refusals(self):
        raw = tiny_image()
        patch = dict(address=0x1000, before=b'\x00\x00', after=b'\x00\xbf')
        with self.assertRaisesRegex(ImageError, 'wrong base'):
            extend(raw, 0x83FD0000, b'\xAA'*4, [patch])
        with self.assertRaisesRegex(ImageError, 'overlaps'):
            extend(raw, 0x20000080, b'\xAA'*4)
        with self.assertRaises(ImageError):
            extend(raw, 0x83FD0000, b'\xAA'*3)
        good = dict(address=0x1000, before=b'\x70\x47', after=b'\x00\xbf')
        with self.assertRaisesRegex(ImageError, 'overlapping'):
            extend(raw, 0x83FD0000, b'\xAA'*4, [good, good])
        with self.assertRaises(ImageError):
            file_offset(raw, 0x20000000, 4)

    def test_flash_address_maps_to_the_file(self):
        self.assertEqual(file_offset(tiny_image(), FLASH+0x100, 4), 0x100)
        self.assertEqual(file_offset(tiny_image(), 0x1000, 4), 0x100)
        self.assertEqual(ZERO, 0x60080100)


class Decompress(unittest.TestCase):
    def test_literal_and_zero_run(self):
        # token 0x22: literal count byte 2 means 1 literal, count 2 means 2 zeros
        self.assertEqual(decompress(bytes([0x22, 0x41]), 3), (b'A\0\0', 2))

    def test_back_reference(self):
        # token 0x1A: literal 2 means 1 literal, bit 3 set, count 1 copies 3 bytes at distance 1
        self.assertEqual(decompress(bytes([0x1A, 0x41, 0x01]), 4), (b'AAAA', 3))

    def test_refuses_bad_data(self):
        for data, size in ((b'', 1), (bytes([0x22]), 3), (bytes([0x1A, 0x41, 0x05]), 4), (bytes([0x22, 0x41]), 2)):
            with self.assertRaises(ImageError):
                decompress(data, size)


if __name__ == '__main__':
    unittest.main()
