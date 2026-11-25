"""`doctor` tells a newcomer, or their agent, what is missing on this computer and how to get it, on Linux, macOS and Windows."""
import unittest

from lab404.doctor import HINTS, report


class Doctor(unittest.TestCase):
    def test_on_a_working_setup_the_needed_parts_are_found(self):
        states = {name: state for name, state, _ in report()}
        for name in ('python', 'capstone', 'unicorn', 'clang', 'clang builds for the unit'):
            self.assertEqual(states[name], 'ok', name)
        self.assertIn(states['whole-firmware emulator'], ('ok', 'optional, not found'))

    def test_a_missing_compiler_is_named_with_the_way_to_get_it_on_each_system(self):
        for system, word in (('Linux', 'apt'), ('Darwin', 'brew'), ('Windows', 'winget')):
            rows = {name: (state, hint) for name, state, hint in report(system=system, which=lambda name: None)}
            self.assertEqual(rows['clang'][0], 'missing')
            self.assertIn(word, rows['clang'][1])
            self.assertEqual(rows['clang builds for the unit'][0], 'missing')

    def test_every_system_has_a_hint_for_every_tool(self):
        for system in ('Linux', 'Darwin', 'Windows'):
            self.assertEqual(set(HINTS[system]), {'clang', 'git', 'python'})

    def test_it_says_that_the_user_brings_the_firmware(self):
        rows = {name: hint for name, _, hint in report(inputs='/nowhere')}
        self.assertIn('your own', rows['firmware images'])


if __name__ == '__main__':
    unittest.main()
