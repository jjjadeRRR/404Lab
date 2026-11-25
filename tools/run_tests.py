#!/usr/bin/env python3
"""Run the tests faster than one after another, without changing what any of them checks.

    python tools/run_tests.py --quick     everything that needs no emulator, about a minute
    python tools/run_tests.py             all of it

Test files run side by side. Each emulator test runs in its own process, and as many run together as the emulated units they start fit
into a budget, so the computer is not loaded past what the timing of a unit can stand. A test says how many units it starts at once with
`@units(n)` in tests/test_emulator.py.

Nothing is rerun: a failure is reported with its full output. The whole output goes to the log file as well.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMULATOR_MODULE = 'test_emulator'
DEFAULT_UNITS = 2


def emulator_tests():
    """[(test id, units it starts at once)] for every emulator test."""
    sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
    out = []

    def walk(suite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                walk(item)
            else:
                out.append((item.id(), getattr(getattr(item, item._testMethodName), 'units', DEFAULT_UNITS)))
    walk(unittest.defaultTestLoader.loadTestsFromName(EMULATOR_MODULE))
    return out


def plan(jobs, budget):
    """Order of starting: what can start now, given what is running. jobs is [(name, weight)]; returns a function(running_weights) -> index or None."""
    def pick(pending, used):
        for i, (_, weight) in enumerate(pending):
            if used == 0 or used+min(weight, budget) <= budget:
                return i
        return None
    return pick


def counts(text):
    ran = re.search(r'^Ran (\d+) tests? in', text, re.M)
    skipped = re.search(r'skipped=(\d+)', text)
    return int(ran.group(1)) if ran else 0, int(skipped.group(1)) if skipped else 0


def run_all(jobs, budget, log):
    """jobs: [(name, weight)]. Returns (ran, skipped, failed names)."""
    env = dict(os.environ, PYTHONPATH=f'{ROOT}{os.pathsep}{ROOT/"tests"}')
    pending = sorted(jobs, key=lambda job: -job[1])
    pick = plan(jobs, budget)
    running, failed, ran, skipped = [], [], 0, 0
    while pending or running:
        used = sum(weight for _, weight, _, _ in running)
        i = pick(pending, used)
        if i is not None:
            name, weight = pending.pop(i)
            # Output goes to a file, not a pipe: nobody reads a pipe while the test runs, and a test that says a lot
            # (a failure that prints a whole document) would fill it and stand for ever.
            output = tempfile.TemporaryFile(mode='w+', encoding='utf-8')
            process = subprocess.Popen([sys.executable, '-W', 'ignore::ResourceWarning', '-m', 'unittest', name], cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            process.output = output
            running.append((name, min(weight, budget), process, time.monotonic()))
            continue
        time.sleep(0.2)
        for entry in list(running):
            name, _, process, started = entry
            if process.poll() is None:
                continue
            running.remove(entry)
            process.output.seek(0)
            output = process.output.read()
            process.output.close()
            one_ran, one_skipped = counts(output)
            ran, skipped = ran+one_ran, skipped+one_skipped
            ok = process.returncode == 0 and one_ran > 0
            line = f'{"ok  " if ok else "FAIL"} {time.monotonic()-started:6.0f} s  {name}'+(f'  ({one_skipped} skipped)' if one_skipped else '')
            print(line, flush=True)
            log.write(f'\n===== {line}\n{output}')
            log.flush()
            if not ok:
                failed.append(name)
                print(output, flush=True)
    return ran, skipped, failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--quick', action='store_true', help='leave out the tests that boot the emulator')
    parser.add_argument('--units', type=int, default=max(2, (os.cpu_count() or 2)+2), help='how many emulated units may run at once')
    parser.add_argument('--log', default=None, help='where the full output goes (default: private/test-run-latest.log if private/ exists)')
    a = parser.parse_args(argv)
    log_path = Path(a.log) if a.log else ROOT/'private/test-run-latest.log' if (ROOT/'private').is_dir() else Path(os.devnull)
    started = time.monotonic()
    jobs = [(path.stem, 1) for path in sorted((ROOT/'tests').glob('test_*.py')) if path.stem != EMULATOR_MODULE]
    if not a.quick:
        jobs += emulator_tests()
    with open(log_path, 'w', encoding='utf-8') as log:
        ran, skipped, failed = run_all(jobs, a.units, log)
        summary = f'Ran {ran} tests in {time.monotonic()-started:.0f} s'+(f', {skipped} skipped' if skipped else '')+(' (emulator tests left out)' if a.quick else '')
        summary += f'\nFAILED: {", ".join(failed)}' if failed else '\nOK'
        log.write(f'\n{summary}\n')
    print(summary)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
