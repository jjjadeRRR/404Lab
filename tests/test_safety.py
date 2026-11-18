"""Things that can brick a unit are refused by the tools, not left to the care of whoever writes a mod.

What the loader does is in the knowledge base: hw.update.app1-range, hw.update.whole-files, hw.service.loader-erase.
"""
import tempfile
import unittest
from pathlib import Path

from lab404.build import BuildError, firmware_symbols
from lab404.hooks import check_entry_hook
from lab404.image import APP1_ROOM, Image, ImageError, extend, protected, room
from lab404.knowledge import Knowledge
from lab404.pipeline import PackageRefused, refuse_dangerous_files
from helpers import DOOM73, STOCK, tiny_image


class Size(unittest.TestCase):
    def test_the_room_is_what_the_loader_erases(self):
        self.assertEqual(APP1_ROOM, 0x37F000)
        self.assertEqual(room(bytes(0x1000)), 0x37F000-0x1000)

    def test_an_image_past_the_erased_area_is_refused(self):
        raw = tiny_image()
        extend(raw, 0x83000000, bytes(APP1_ROOM-len(raw)-0x100))
        with self.assertRaisesRegex(ImageError, 'flash limit'):
            extend(raw, 0x83000000, bytes(APP1_ROOM))

    def test_the_knowledge_base_gives_the_same_number(self):
        claim = {f['id']: f for f in Knowledge().facts}['hw.update.app1-range']['claim']
        self.assertIn(f'0x{APP1_ROOM:X}', claim)


@unittest.skipUnless(STOCK.exists() and DOOM73.exists(), 'needs stock 5.52 and DOOM OS 0.7.3')
class LoaderEraseCode(unittest.TestCase):
    def test_every_address_the_knowledge_base_names_is_protected(self):
        image = Image(STOCK.read_bytes())
        for address in (0x80065838, 0x80064E48, 0x80064E70, 0x8017D3C8, 0x8019D348, 0x8001ACB0, 0x800D5FD8):
            self.assertTrue(protected(image, address), hex(address))
            self.assertTrue(protected(image, address+6), hex(address))
        self.assertIsNone(protected(image, 0x800DA598))

    def test_a_hook_there_is_refused_on_both_bases(self):
        for path in (STOCK, DOOM73):
            with self.assertRaisesRegex(ImageError, 'loader'):
                check_entry_hook(Image(path.read_bytes()), 0x80065838)

    def test_a_mod_may_not_call_it(self):
        image = Image(STOCK.read_bytes())
        mod = {'firmware_symbols': {'wipe': {'address': '0x80064E49', 'expect': image.read(0x80064E48, 8).hex()}}}
        with self.assertRaisesRegex(BuildError, 'loader'):
            firmware_symbols(mod, image)


class Names(unittest.TestCase):
    def test_files_the_loader_or_service_code_would_act_on_are_refused(self):
        for name in ('SP404MKII_APP1W.bin', 'sp404mkii_app0w.BIN', 'SP404MKII_APP1U.bin', 'MIRXRT1060-EVK.bin', 'TD003_ROM.bin', 'SP404MKII_APP0.bin'):
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp)/'sub').mkdir()
                (Path(tmp)/'sub'/name).write_bytes(b'x')
                with self.assertRaisesRegex(PackageRefused, 'brick'):
                    refuse_dangerous_files(tmp)

    def test_the_candidate_itself_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'SP404MKII_APP1.bin').write_bytes(b'x')
            refuse_dangerous_files(tmp)


if __name__ == '__main__':
    unittest.main()
