"""The repository stays public-ready: the tool needs nothing private and carries nothing it must not.

Checks every file git would take: tracked ones and new ones not yet added, so a new file cannot slip past until after it is committed. Words are assembled at run time so this file does not trip its own check.
"""
import ast
import subprocess
import unittest

from helpers import ROOT

ALLOWED_THIRD_PARTY = {'capstone', 'unicorn'}
# Why these words: all but three are names of files, folders and builds from the maintainer's private mod work, so
# their appearance means private code was copied in by accident. The three about keys and ciphers
# come from APP0 encryption work that the maintainer keeps out of the public project. This is a tripwire for leaks,
# not a ban on a topic: if a word blocks honest text, narrow the list here and say why in the commit.
FORBIDDEN_WORDS = ['pad'+'filter', 'sp404'+'-cleanup', 'sp404'+'-lab', 'build'+'_d72', 'native'+'_mix_probe', 'target'+'_payload',
                   'key'+' search', 'brute'+' force', 'blow'+'fish', 'led'+'_anim']


def tracked():
    out = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT, capture_output=True, text=True, check=True, encoding='utf-8').stdout
    return [ROOT/name for name in out.split('\0') if name]


class Boundary(unittest.TestCase):
    def test_no_firmware_or_audio_tracked(self):
        bad = [p.name for p in tracked() if p.suffix.lower() in ('.bin', '.patch', '.wav', '.aif', '.aiff', '.pdf', '.elf')]
        self.assertEqual(bad, [])

    def test_no_large_binary_files(self):
        for path in tracked():
            data = path.read_bytes()
            self.assertLess(len(data), 512*1024, path.name)
            self.assertNotIn(b'\0', data, f'{path.name} looks binary')

    def test_private_words_absent(self):
        for path in tracked():
            text = path.read_text(encoding='utf-8').lower()
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, text, f'{word!r} in {path.relative_to(ROOT)}')

    def test_shared_checks_carry_fingerprints_not_firmware_bytes(self):
        # Why: byte checks used to store the firmware's own bytes (Roland's and DOOM OS's). A size and SHA-256 checks the
        # same thing on the user's image without copying code into the repository. 'hex' and 'expect' still work for a
        # private, local mod; they do not belong in what is shared here.
        import json
        from lab404.image import PROTECTED
        for path in tracked():
            if path.suffix != '.json' or not ({'knowledge', 'mods'} & set(path.relative_to(ROOT).parts)):
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
            for fact in data.get('facts', []):
                for check in fact.get('checks', []):
                    self.assertNotIn('hex', check, f'{fact["id"]} in {path.name}')
            for name, entry in data.get('firmware_symbols', {}).items():
                self.assertNotIn('expect', entry, f'{name} in {path.parent.name}')
        for entry in PROTECTED:
            self.assertEqual(len(entry[2]), 64, hex(entry[0]))

    def test_text_files_are_read_and_written_as_utf8(self):
        # Why: without an encoding Python uses the system's code page. On Windows that is not UTF-8, and reading a note
        # with a dash or Russian text fails there while it passes on Linux and macOS.
        for path in tracked():
            if path.suffix != '.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(node, ast.Call):
                    continue
                func, keywords = node.func, {k.arg for k in node.keywords}
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None)
                if 'encoding' in keywords or None in keywords:
                    continue
                if name in ('read_text', 'write_text') and isinstance(func, ast.Attribute):
                    text = True
                elif name == 'open':
                    at = 1 if isinstance(func, ast.Name) else 0     # open(path, mode) or path.open(mode)
                    mode = node.args[at].value if len(node.args) > at and isinstance(node.args[at], ast.Constant) else \
                        next((k.value.value for k in node.keywords if k.arg == 'mode' and isinstance(k.value, ast.Constant)), 'r')
                    text = 'b' not in mode
                elif name in ('run', 'Popen', 'check_output') and isinstance(func, ast.Attribute):
                    text = bool({'text', 'universal_newlines'} & keywords)
                else:
                    text = False
                self.assertFalse(text, f'{path.relative_to(ROOT)}:{node.lineno} {name}() without encoding')

    def test_tool_imports_only_stdlib_and_declared_dependencies(self):
        import sys
        for path in tracked():
            if path.suffix != '.py' or 'tests' in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module]
                for name in names:
                    top = name.split('.')[0]
                    self.assertTrue(top in sys.stdlib_module_names or top in ALLOWED_THIRD_PARTY, f'{top} in {path.name}')

    def test_no_dynamic_imports_and_only_known_programs_as_subprocesses(self):
        for path in tracked():
            # emulator.py also starts the separately built DM-404 program.
            if path.suffix != '.py' or 'tests' in path.parts or path.name == 'emulator.py':
                continue
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('__import__', text, path.name)
            self.assertNotIn('importlib', text, path.name)
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('run', 'Popen', 'check_output', 'system'):
                    if getattr(node.func.value, 'id', '') in ('subprocess', 'os'):
                        first = node.args[0].elts[0]
                        if path.name == 'run_tests.py':  # the test runner starts this same Python on the tests, and nothing else
                            self.assertEqual(ast.unparse(first), 'sys.executable', path.name)
                            continue
                        program = first.value
                        # build.py reads the source revision for reports, and nothing else.
                        self.assertIn(program, ('clang', 'git') if path.name == 'build.py' else ('clang',), path.name)


if __name__ == '__main__':
    unittest.main()
