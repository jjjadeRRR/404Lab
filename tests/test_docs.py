"""The README is checked like code: its commands exist, its links lead somewhere, and it keeps the promises that matter."""
import json
import re
import subprocess
import sys
import unittest

from helpers import ROOT

README = (ROOT/'README.md').read_text(encoding='utf-8')


class Exam(unittest.TestCase):
    def test_every_task_says_what_it_requires(self):
        tasks = json.loads((ROOT/'exam/tasks.json').read_text(encoding='utf-8'))['tasks']
        self.assertGreaterEqual(len(tasks), 5)
        self.assertEqual(len({task['id'] for task in tasks}), len(tasks))
        for task in tasks:
            self.assertTrue(task['says'].strip())
            self.assertTrue(task['must'], task['id'])
            self.assertEqual('then' in task, 'then_must' in task, task['id'])


class Readme(unittest.TestCase):
    def test_every_command_it_names_exists(self):
        commands = set(re.findall(r'python -m lab404 ([a-z-]+)', README))
        self.assertGreaterEqual(len(commands), 5, 'the README should show how to use the tools')
        for command in commands:
            result = subprocess.run([sys.executable, '-m', 'lab404', command, '--help'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, f'{command}: {result.stderr[-200:]}')

    def test_every_local_link_leads_to_a_file(self):
        for target in re.findall(r'\]\((?!https?://)([^)#]+)', README):
            self.assertTrue((ROOT/target).exists(), target)

    def test_it_keeps_its_promises(self):
        for promise in ('ships no firmware', 'not affiliated', 'candidate', 'never proof', 'unit', 'Licence'):
            self.assertIn(promise, README)

    def test_the_licence_is_the_one_it_says(self):
        self.assertIn('[MIT](LICENSE)', README)
        self.assertTrue((ROOT/'LICENSE').read_text(encoding='utf-8').startswith('MIT License'))

    def test_the_public_name_is_there(self):
        self.assertIn('404Lab', README)


if __name__ == '__main__':
    unittest.main()
