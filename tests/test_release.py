"""Publication checks: local paths, personal addresses and private inputs stay out.

Public licence contacts are allowed only in their source document. The README
examples run on local inputs; installing dependencies and publishing stay manual.
"""
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, STOCK
from test_boundary import tracked


def exposure_issues(name, text):
    issues = []
    if Path(name).parts[0] in ('inputs', 'private', 'out'):
        issues.append('private directory')
    home = r'(?:/(?:home|Users)/[^\s/]+|[A-Za-z]:[\\/]+Users[\\/]+[^\s\\/]+)'
    if re.search(home, text):
        issues.append('absolute home path')
    emails = set(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text))
    # This public licensing contact is provenance, not the owner's address.
    sources = ('docs/LEGAL_NOTES.md', 'knowledge/facts/mods.json')
    allowed = {'lab'+'@klangfeldlabs.com'} if name in sources else set()
    if emails - allowed:
        issues.append('unreviewed email')
    return issues


class ExposureChecks(unittest.TestCase):
    def test_detects_home_paths_on_linux_mac_and_windows(self):
        for path in ('/ho'+'me/example/work', '/Us'+'ers/example/work',
                     'C:\\Us'+'ers\\example\\work', 'D:/Us'+'ers/example/work'):
            with self.subTest(path=path):
                self.assertIn('absolute home path', exposure_issues('notes.md', path))

    def test_detects_personal_email_but_keeps_the_documented_licence_contact(self):
        self.assertIn('unreviewed email', exposure_issues('notes.md', 'owner'+'@example.org'))
        public_contact = 'lab'+'@klangfeldlabs.com'
        self.assertEqual(exposure_issues('docs/LEGAL_NOTES.md', public_contact), [])
        self.assertEqual(exposure_issues('knowledge/facts/mods.json', public_contact), [])
        self.assertIn('unreviewed email', exposure_issues('notes.md', public_contact))

    def test_rejects_private_directories_even_for_plain_text(self):
        for name in ('inputs/readme.md', 'private/notes.md', 'out/report.json'):
            self.assertIn('private directory', exposure_issues(name, 'plain text'))
        self.assertEqual(exposure_issues('docs/STAND.md', 'Keep inputs/ local.'), [])

    def test_repository_has_no_exposures(self):
        problems = []
        for path in tracked():
            name = path.relative_to(ROOT).as_posix()
            problems.extend(f'{name}: {issue}' for issue in
                            exposure_issues(name, path.read_text(encoding='utf-8')))
        self.assertEqual(problems, [])


@unittest.skipUnless(STOCK.exists(), 'stock-5.52 input needed for README examples')
class ReadmeExamples(unittest.TestCase):
    def test_readme_examples_run_and_approval_commands_have_help(self):
        readme = (ROOT/'README.md').read_text(encoding='utf-8')
        commands = [shlex.split(line) for block in re.findall(r'```bash\n(.*?)```', readme, re.S)
                    for line in block.splitlines() if line.startswith('python -m lab404 ')]
        self.assertTrue(commands, 'No CLI examples found')
        allowed = {'doctor', 'identify', 'ask', 'topics', 'gaps', 'check-keys',
                   'verify-knowledge', 'build', 'check', 'preview'}
        gated = {'approve', 'package'}
        with tempfile.TemporaryDirectory(prefix='lab404-readme-') as directory:
            paths = {'SP404MKII_APP1.bin': str(STOCK),
                     'out/demo-1': str(Path(directory)/'demo-1')}
            for command in commands:
                # New operations need review before this test executes them.
                self.assertIn(command[3], allowed | gated, command)
                if command[3] in gated:
                    # Never turn example wording into a real user decision.
                    # Full packaging behaviour has its own pipeline tests.
                    argv = [sys.executable, '-m', 'lab404', command[3], '--help']
                else:
                    argv = [sys.executable, *[paths.get(arg, arg) for arg in command[1:]]]
                result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120, encoding='utf-8')
                self.assertEqual(result.returncode, 0,
                                 f'{command}:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}')
                self.assertTrue(result.stdout.strip(), command)


if __name__ == '__main__':
    unittest.main()
