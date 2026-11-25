"""Only an exact hash makes an image known. Everything damaged or changed must come out unknown or invalid."""
import json
import unittest

from lab404.identify import TABLE, explain, identify
from lab404.image import extend
from helpers import DOOM72, DOOM73, ROOT, STOCK, tiny_image


class Synthetic(unittest.TestCase):
    def test_table_is_sane(self):
        hashes = [e['sha256'] for e in TABLE]
        self.assertEqual(len(hashes), len(set(hashes)))
        for entry in TABLE:
            self.assertRegex(entry['sha256'], r'^[0-9a-f]{64}$')
            self.assertRegex(entry['source'], r'^\[(DOC|BYTES)\] ')

    def test_unknown_container(self):
        result = identify(tiny_image())
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('Ask the user', explain(result))

    def test_garbage_is_invalid(self):
        for raw in (b'', b'not firmware', bytes(0x1000)):
            self.assertEqual(identify(raw)['status'], 'invalid', raw[:8])

    def test_a_label_inside_the_image_never_makes_it_known(self):
        result = identify(tiny_image(b'DOOM OS 0.7.3-733D\0\0'))
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('DOOM OS 0.7.3-733D', result['hints'])
        self.assertIsNone(result['version'])


@unittest.skipUnless(STOCK.exists() and DOOM73.exists() and DOOM72.exists(), 'firmware inputs not present')
class RealImages(unittest.TestCase):
    def test_known_images(self):
        self.assertEqual((identify(STOCK.read_bytes())['family'], identify(STOCK.read_bytes())['version']), ('stock', '5.52'))
        self.assertEqual(identify(DOOM73.read_bytes())['version'], '0.7.3')
        self.assertEqual(identify(DOOM72.read_bytes())['version'], '0.7.2')

    def test_one_changed_byte_is_not_known(self):
        raw = bytearray(STOCK.read_bytes())
        raw[0x100000] ^= 1
        self.assertEqual(identify(bytes(raw))['status'], 'unknown')

    def test_truncated_image_is_not_known(self):
        raw = STOCK.read_bytes()
        for size in (len(raw)-1, len(raw)//2, 0x87):
            self.assertNotEqual(identify(raw[:size])['status'], 'known', size)

    def test_doom_with_extra_row_keeps_only_hints(self):
        out = extend(DOOM73.read_bytes(), 0x83FD0000, b'\0'*16)
        result = identify(out)
        self.assertEqual(result['status'], 'unknown')
        self.assertTrue(any('13 scatter rows' in h for h in result['hints']), result['hints'])
        self.assertTrue(any('0.7.3' in h for h in result['hints']), result['hints'])

    def test_tool_table_is_valid_json_on_disk(self):
        json.loads((ROOT/'lab404/known_images.json').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
