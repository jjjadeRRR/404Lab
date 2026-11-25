"""The stand reports what it did not execute instead of passing silently."""
import unittest

from lab404.stand import Boundary, Machine
from helpers import STOCK, tiny_image


class Stand(unittest.TestCase):
    def test_unmodelled_memory_stops_the_run(self):
        # ldr r0,[r1] with r1 = 0x402E0000, a peripheral the stand does not model
        with self.assertRaisesRegex(Boundary, '0x402E0000'):
            Machine(tiny_image(bytes.fromhex('08687047'))).call(0x1000, (0, 0x402E0000))

    def test_endless_code_stops_at_the_budget(self):
        # b . : never returns
        with self.assertRaisesRegex(Boundary, 'did not return within 500'):
            Machine(tiny_image(bytes.fromhex('fee700bf'))).call(0x1000, budget=500)

    def test_clobbered_callee_saved_register_is_caught(self):
        # movs r4,#1 ; bx lr
        with self.assertRaisesRegex(AssertionError, 'callee-saved'):
            Machine(tiny_image(bytes.fromhex('01247047'))).call(0x1000)

    def test_arguments_and_return_value(self):
        # adds r0,r0,r1 ; bx lr
        self.assertEqual(Machine(tiny_image(bytes.fromhex('40187047'))).call(0x1000, (2, 3)), 5)

    def test_stub_replaces_a_call_and_is_logged(self):
        # at 0x1000: push {r4,lr}; bl 0x1010; pop {r4,pc}. At 0x1010: movs r0,#1; bx lr, which the stub must replace.
        code = bytes.fromhex('10b5' '00f005f8' '10bd' '00bf00bf00bf00bf' '01207047')
        machine = Machine(tiny_image(code))
        self.assertEqual(machine.call(0x1000, (9,)), 1)
        machine.stub(0x1010, lambda _m, r0, r1, r2, r3: r0+41, 'fake')
        self.assertEqual(machine.call(0x1000, (1,)), 42)
        self.assertEqual(machine.stub_calls, [('fake', (1, 0, 0, 0))])

    def test_zero_regions_start_as_zero_not_unmapped(self):
        self.assertEqual(Machine(tiny_image()).read(0x20000000, 4), bytes(4))

    @unittest.skipUnless(STOCK.exists(), 'firmware inputs not present')
    def test_memory_starts_as_the_scatter_table_leaves_it(self):
        machine = Machine(STOCK.read_bytes())
        self.assertEqual(machine.read(0x15FEE, 4), bytes.fromhex('2de9f043'))
        self.assertEqual(machine.read(0x80000000, 16), machine.image.read(0x80000000, 16))


if __name__ == '__main__':
    unittest.main()
