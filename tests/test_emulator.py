"""Whole firmware on the DM-404 emulator: real boot, real key handling, real screens. Evidence about logic, not about a unit.

The comparison tests are protected against being empty: they also assert that the keys used really change the screen, and that DOOM OS really
differs from stock on a screen of its own. A hook is shown firing in the running firmware, called by its own event code.
"""
import json
import shutil
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lab404.build import build
from lab404.emulator import BLANK_DRIVE, MAIN_PAGE, MAIN_PAGE_WORD, Emulator, available, lit_pixels
from lab404.knowledge import Knowledge
from lab404.pipeline import PackageRefused, _unused_on_base, _walk, approve, package, replay
from lab404.observe import ROUTE_PAGE, ROUTES, classify, control_id, do_step, jobs_for, run_job, select, signature_for
from helpers import DOOM73, DOOM74, PROJECT_DRIVE, ROOT, STOCK

MOD = ROOT/'mods/demo_counter'
# Bases the example mods are tried on. DOOM OS 0.7.4 joins when its image is present, since 2026-11-23: the mods declare it.
BASES = (('stock', STOCK), ('doom', DOOM73))+((('doom74', DOOM74),) if DOOM74.exists() else ())
DOOM_BASES = (DOOM73,)+((DOOM74,) if DOOM74.exists() else ())
KEY_HANDLER = '0x800A80A8'  # [BYTES] stock function that receives key events
VOICE_RENDERER = '0x14B88'  # [BYTES] renders one voice
PADS_PLAYED = ('PAD1', 'PAD2', 'PAD3', 'PAD4')
SCENARIO = ('MFX', 'EXIT', 'PITCH/SPEED', 'EXIT', 'START/END', 'EXIT', 'PATTERN SELECT', 'EXIT')


def units(count):
    """How many emulated units this test starts at once, so tools/run_tests.py can run tests side by side without overloading the computer."""
    def mark(test):
        test.units = count
        return test
    return mark


def boot(unit):
    # Logos come first and can stay still for over 3 seconds, so a still picture alone does not mean booted. The idle screen saver starts about 70 s after
    # the main screen and differs between runs, so scenarios must finish well before it.
    assert unit.wait_for_main(45, 3), f'no main screen: {unit.frames} frames, {lit_pixels(unit.frame)} lit, process {unit.process.poll()}'


def together(function, *units):
    """Run the same steps on several units at once, so both stay clear of the screen saver."""
    with ThreadPoolExecutor(len(units)) as pool:
        return list(pool.map(function, units))


def walk(unit):
    """Screens seen through the scenario, with what was pressed."""
    seen = [('main', unit.frame)]
    for name in SCENARIO:
        unit.press(name)
        seen.append((name, unit.frame))
    return seen


@unittest.skipUnless(available() and STOCK.exists() and DOOM73.exists(), 'emulator or firmware inputs not present')
class WholeFirmware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='lab404-emu-'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    @units(6)
    def test_ready_means_the_main_screen_even_under_load(self):
        # Waiting for a still picture stopped on a boot logo in 8 of 12 loaded boots with a project. Six at once make the load.
        drive = PROJECT_DRIVE if PROJECT_DRIVE.exists() else BLANK_DRIVE

        def boots(_):
            with Emulator(STOCK.read_bytes(), drive=drive) as unit:
                boot(unit)
                frame, page = unit.frame, unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF
                time.sleep(4)
                return page, frame == unit.frame
        with ThreadPoolExecutor(6) as pool:
            self.assertEqual(list(pool.map(boots, range(6))), [(MAIN_PAGE, True)]*6)

    @units(1)
    def test_a_stuck_unit_can_describe_itself(self):
        with Emulator(STOCK.read_bytes()) as unit:
            boot(unit)
            report = unit.diagnose()
        self.assertRegex(report['registers'], r'R15=[0-9a-f]{8}')
        self.assertEqual(report['status'], 'VM status: running')
        self.assertGreater(report['audio_frames_later'], report['audio_frames'])
        self.assertTrue(report['threads'])
        self.assertIn('load', report['host'])

    @units(1)
    def test_stock_boots_and_keys_work(self):
        with Emulator(STOCK.read_bytes()) as unit:
            boot(unit)
            main = unit.frame
            self.assertGreater(lit_pixels(main), 500)
            self.assertGreater(unit.audio_frames, 0)
            unit.press('MFX')
            self.assertNotEqual(unit.frame, main, 'MFX did not change the screen')
            unit.press('EXIT')
            self.assertEqual(unit.frame, main, 'EXIT did not return to the main screen')

    def test_candidate_matches_its_base_screen_for_screen(self):
        for name, base in BASES:
            package = self.tmp/f'pkg-{name}'
            build(MOD, base, package)
            with Emulator(base.read_bytes()) as a, Emulator((package/'SP404MKII_APP1.bin').read_bytes()) as b:
                together(boot, a, b)
                first, second = together(walk, a, b)
            self.assertGreater(len({frame for _, frame in first}), 2, 'the keys changed nothing: the comparison would be empty')
            self.assertEqual([x[0] for x in first], [x[0] for x in second])
            for (key, one), (_, two) in zip(first, second):
                self.assertEqual(one, two, f'{name}: screen differs after {key}')

    @units(1)
    def test_a_hook_fires_in_the_running_firmware(self):
        mod = self.tmp/'keys-mod'
        shutil.copytree(MOD, mod)
        spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
        spec['hooks'][0] = dict(kind='entry', address=KEY_HANDLER, function='demo_counter_hook')
        spec['bases'] = spec['bases'][:1]
        (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
        package = self.tmp/'keys-pkg'
        manifest = build(mod, STOCK, package)
        counter = int(manifest['symbols']['demo_counter_calls'], 16)
        with Emulator((package/'SP404MKII_APP1.bin').read_bytes()) as unit:
            boot(unit)
            before = unit.read_u32(counter)
            unit.press('MFX')
            unit.press('EXIT')
            self.assertGreater(unit.read_u32(counter), before)

    @units(1)
    def test_doom_opens_its_own_screen_and_stock_does_not(self):
        frames = {}
        for name, base in (('stock', STOCK), ('doom', DOOM73)):
            with Emulator(base.read_bytes()) as unit:
                boot(unit)
                main = unit.frame
                unit.key(3, 2, True)  # REMAIN
                time.sleep(0.2)
                unit.analog(0, 6, 4, 0)  # SUB PAD
                time.sleep(0.2)
                unit.analog(0, 6, 4, 4095)
                time.sleep(0.2)
                unit.key(3, 2, False)
                time.sleep(1.5)
                frames[name] = (main, unit.frame)
        self.assertEqual(frames['stock'][0], frames['doom'][0], 'main screens were expected to match')
        self.assertNotEqual(frames['doom'][1], frames['doom'][0], 'REMAIN + SUB PAD did not open DOOM OS')
        self.assertNotEqual(frames['doom'][1], frames['stock'][1], 'DOOM OS did not differ from stock')


@unittest.skipUnless(available() and DOOM73.exists(), 'emulator or firmware inputs not present')
class DoomOsAtRunTime(unittest.TestCase):
    """What DOOM OS does to itself while it starts. A mod that patches the file where DOOM OS patches memory loses its patch."""

    @units(1)
    def test_doom_os_rewrites_the_words_of_its_veneers_and_leaves_its_key_trampoline(self):
        # Eleven veneers `ldr.w pc, [pc]` at 0x80209880..0x802098D0 each jump through the word after them. Recorded as hk.doom.veneers-rewritten.
        from lab404.image import Image
        raw = DOOM73.read_bytes()
        image = Image(raw)
        veneers = [a for a in range(0x80209880, 0x802098D8, 8) if image.u32(a) == 0xF000F8DF]
        self.assertEqual(len(veneers), 11)
        with Emulator(raw) as unit:
            boot(unit)
            live = {a: unit.read_u32(a+4) for a in veneers}
            trampoline = [unit.read_u32(0x802097CC+i) for i in (0, 4, 8)]
        for a in veneers:
            self.assertEqual(image.u32(a+4) >> 20, 0x603, f'{a:#x}: in the file the word points into flash')
            self.assertEqual(live[a] >> 20, 0x835, f'{a:#x}: running, it points into RAM')
        self.assertEqual(trampoline, [image.u32(0x802097CC+i) for i in (0, 4, 8)], 'the key trampoline is not rewritten')


@unittest.skipUnless(available() and DOOM74.exists(), 'emulator or DOOM OS 0.7.4 input not present')
class DoomOs074AtRunTime(unittest.TestCase):
    """0.7.4-651C has thirteen veneers where 0.7.3 had eleven (hk.doom.074.veneers). Does it still repoint them while it starts?"""

    @units(1)
    def test_doom_os_074_rewrites_the_words_of_its_thirteen_veneers_and_leaves_its_key_trampoline(self):
        from lab404.image import Image
        raw = DOOM74.read_bytes()
        image = Image(raw)
        veneers = [a for a in range(0x80209880, 0x802098E8, 8) if image.u32(a) == 0xF000F8DF]
        self.assertEqual(len(veneers), 13)
        self.assertEqual((image.u32(0x8020988C), image.u32(0x802098A4)), (0x60339E31, 0x603395FD))  # voice launch, LOAD
        with Emulator(raw) as unit:
            boot(unit)
            live = {a: unit.read_u32(a+4) for a in veneers}
            trampoline = [unit.read_u32(0x802097CC+i) for i in (0, 4, 8)]
        for a in veneers:
            self.assertEqual(image.u32(a+4) >> 20, 0x603, f'{a:#x}: in the file the word points into flash')
            self.assertEqual(live[a] >> 20, 0x835, f'{a:#x}: running, it points into RAM')
        self.assertEqual(trampoline, [image.u32(0x802097CC+i) for i in (0, 4, 8)], 'the key trampoline is not rewritten')


@unittest.skipUnless(available() and STOCK.exists() and DOOM73.exists(), 'emulator or firmware inputs not present')
class WordHookAtRunTime(unittest.TestCase):
    """A word hook on the panel tick's vtable word is called by the running firmware, and the original it calls keeps the unit as it was."""

    @units(2)
    def test_the_repointed_tick_runs_and_the_screens_stay_the_bases(self):
        from test_word_hooks import TICK, TICK_SLOT, mod_with
        from lab404.identify import identify
        for name, base in BASES:
            with tempfile.TemporaryDirectory() as d:
                mod = mod_with(Path(d)/'mod', dict(address=hex(TICK_SLOT), expect=hex(TICK)), bases=(identify(base.read_bytes())['sha256'],))
                manifest = build(mod, base, Path(d)/'pkg')
                candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
            calls = int(manifest['symbols']['word_hook_calls'], 16)
            with Emulator(base.read_bytes()) as a, Emulator(candidate) as b:
                together(boot, a, b)
                first = b.read_u32(calls)
                time.sleep(1)
                self.assertGreater(b.read_u32(calls), first, f'{name}: the tick never came through the word')
                one, two = together(walk, a, b)
            for (key, x), (_, y) in zip(one, two):
                self.assertEqual(x, y, f'{name}: screen differs after {key}')


@unittest.skipUnless(available() and STOCK.exists() and DOOM73.exists(), 'emulator or firmware inputs not present')
class QuickSystem(unittest.TestCase):
    """A real mod with a visible function, on two bases. HOLD + ROLL opens the SYSTEM screen on the candidate and does nothing on the base."""

    def test_the_chord_does_nothing_away_from_the_screen_it_was_declared_for(self):
        # Declared and checked for the main screen only. Elsewhere those keys are the firmware's own.
        for name, base in BASES:
            with tempfile.TemporaryDirectory() as d:
                build(ROOT/'mods/quick_system', base, Path(d)/'pkg')
                candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
            for route in (['PITCH/SPEED'], ['PATTERN SELECT'], ['REC'], ['SHIFT+PAD13']):
                def go(unit):
                    boot(unit)
                    for step in route:
                        do_step(unit, step)
                    unit.hold('HOLD')
                    time.sleep(0.1)
                    unit.press('ROLL')
                    unit.release('HOLD')
                    time.sleep(0.6)
                    return unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF, unit.frame
                with Emulator(base.read_bytes()) as a, Emulator(candidate) as b:
                    first, second = together(go, a, b)
                self.assertEqual(first, second, f'{name}, from {route}')

    @units(1)
    def test_a_copy_of_a_blank_drive_is_not_taken_for_a_project(self):
        with tempfile.TemporaryDirectory() as d:
            alias = Path(d)/'looks-like-a-project.img'
            alias.symlink_to(BLANK_DRIVE)
            spec = json.loads((ROOT/'mods/quick_system/mod.json').read_text(encoding='utf-8'))
            got = _unused_on_base(spec['adds']['bindings'][0], STOCK.read_bytes(), alias, 'stock-5.52')
        self.assertEqual(got['state'], 'unknown', got)

    def test_on_doom_os_its_own_screen_keeps_the_keys(self):
        for base in DOOM_BASES:
            with self.subTest(base=base.parent.name):
                self.own_screen_keeps_the_keys(base)

    def own_screen_keeps_the_keys(self, base):
        with tempfile.TemporaryDirectory() as d:
            build(ROOT/'mods/quick_system', base, Path(d)/'pkg')
            candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()

        def go(unit):
            boot(unit)
            unit.hold('REMAIN')
            time.sleep(0.2)
            unit.press('SUB PAD', settle=0.2)
            unit.release('REMAIN')
            time.sleep(1.5)
            opened = unit.frame
            unit.hold('HOLD')
            time.sleep(0.1)
            unit.press('ROLL')
            unit.release('HOLD')
            time.sleep(0.6)
            return opened, unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF, unit.frame
        with Emulator(base.read_bytes()) as a, Emulator(candidate) as b:
            first, second = together(go, a, b)
        self.assertEqual(first, second)

    @unittest.skipUnless(PROJECT_DRIVE.exists(), 'the walk varies most with samples on screen')
    @units(6)
    def test_the_walk_repeats_between_boots_of_the_same_firmware(self):
        # Before PICTURE_VARIES this differed in about half of all boots, which could fail a good candidate.
        def go(_):
            with Emulator(STOCK.read_bytes(), drive=PROJECT_DRIVE) as unit:
                return _walk(unit, 'stock-5.52')
        with ThreadPoolExecutor(6) as pool:
            walks = list(pool.map(go, range(12)))
        for walk in walks[1:]:
            self.assertEqual(walk, walks[0])

    @units(4)
    def test_a_whole_task_from_app1_to_package_on_two_bases(self):
        # Works in a clean install too: with no project drive, the check that needs samples answers unknown. DOOM OS 0.7.4 is a third base when present.
        drive = PROJECT_DRIVE if PROJECT_DRIVE.exists() else BLANK_DRIVE
        for _, base in BASES:
            with tempfile.TemporaryDirectory() as d:
                mod = Path(d)/'mod'
                shutil.copytree(ROOT/'mods/quick_system', mod)
                approve(mod, 'owner test')
                with self.assertRaises(PackageRefused) as caught:
                    package(mod, base, Path(d)/'first', drive=drive)
                self.assertEqual(caught.exception.failed, [], caught.exception)
                report = package(mod, base, Path(d)/'pkg', accepted={name: 'owner test' for name in caught.exception.unknown}, drive=drive)
                states = {r['check']: r['state'] for r in report['results']}
                self.assertEqual(states['replay: screens, pages and lights'], 'pass', report['results'])
                self.assertEqual(states['demonstrate: HOLD+ROLL'], 'pass', report['results'])
                self.assertEqual(states['contained: HOLD+ROLL'], 'pass', report['results'])
                self.assertEqual(states['unused on the base: HOLD+ROLL'], 'pass' if drive == PROJECT_DRIVE else 'unknown', report['results'])

    @unittest.skipUnless(PROJECT_DRIVE.exists(), 'needs a project: with no samples LOOP has nothing to act on')
    @units(4)
    def test_a_chord_that_already_does_something_on_the_base_is_refused(self):
        # HOLD + LOOP looks free to the key records, yet LOOP still toggles on the base. Found by the clean-agent exam.
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d)/'mod'
            shutil.copytree(ROOT/'mods/quick_system', mod)
            source = mod/'quick_system.c'
            source.write_text(source.read_text(encoding='utf-8').replace('ROLL = 0x21', 'ROLL = 0x1F'), encoding='utf-8')
            spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
            spec['adds']['bindings'][0]['keys'] = ['HOLD', 'LOOP']
            spec['adds']['demonstrate'][0]['keys'] = ['HOLD', 'LOOP']
            (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
            build(mod, STOCK, Path(d)/'pkg')
            candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
        results = {r['check']: r for r in replay(STOCK.read_bytes(), candidate, spec, PROJECT_DRIVE, 'stock-5.52')}
        self.assertEqual(results['unused on the base: HOLD+LOOP']['state'], 'fail', results)
        results = {r['check']: r for r in replay(STOCK.read_bytes(), candidate, spec, BLANK_DRIVE, 'stock-5.52')}
        self.assertEqual(results['unused on the base: HOLD+LOOP']['state'], 'unknown', 'on a blank drive a quiet base shows nothing')

    @units(4)
    def test_replay_catches_a_chord_that_also_fires_on_screens_it_was_not_declared_for(self):
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d)/'mod'
            shutil.copytree(ROOT/'mods/quick_system', mod)
            source = mod/'quick_system.c'
            source.write_text(source.read_text(encoding='utf-8').replace('CURRENT_PAGE == MAIN_PAGE', '1'), encoding='utf-8')
            spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
            build(mod, STOCK, Path(d)/'pkg')
            candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
        results = {r['check']: r for r in replay(STOCK.read_bytes(), candidate, spec, BLANK_DRIVE, 'stock-5.52')}
        self.assertEqual(results['contained: HOLD+ROLL']['state'], 'fail', results)
        self.assertEqual(results['replay: screens, pages and lights']['state'], 'pass', 'the ordinary walk alone does not press the chord')

    @units(4)
    def test_replay_catches_a_mod_that_changes_something_existing(self):
        # The same mod with one mistake: ROLL alone is enough, so a key that already does something now does something else.
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d)/'mod'
            shutil.copytree(ROOT/'mods/quick_system', mod)
            source = mod/'quick_system.c'
            source.write_text(source.read_text(encoding='utf-8').replace('hold_is_down && CURRENT_PAGE == MAIN_PAGE', '(hold_is_down || 1) && CURRENT_PAGE == MAIN_PAGE'), encoding='utf-8')
            spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
            spec['hooks'] = spec['hooks'][:1]
            (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
            build(mod, STOCK, Path(d)/'pkg')
            candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
        results = {r['check']: r['state'] for r in replay(STOCK.read_bytes(), candidate, spec, BLANK_DRIVE, 'stock-5.52')}
        self.assertEqual(results['replay: screens, pages and lights'], 'fail')

    def chord(self, unit):
        boot(unit)
        unit.hold('HOLD')
        time.sleep(0.1)
        unit.press('ROLL')
        unit.release('HOLD')
        time.sleep(0.6)
        return unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF

    def test_the_chord_opens_system_on_the_candidate_only_and_exit_returns(self):
        for name, base in BASES:
            with tempfile.TemporaryDirectory() as d:
                build(ROOT/'mods/quick_system', base, Path(d)/'pkg')
                candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
            with Emulator(base.read_bytes()) as a, Emulator(candidate) as b:
                pages = together(self.chord, a, b)
                self.assertEqual(pages, [MAIN_PAGE, ROUTE_PAGE['system']], name)
                b.press('EXIT', settle=1.0)
                self.assertEqual(b.read_u32(MAIN_PAGE_WORD) & 0xFFFF, MAIN_PAGE, f'{name}: EXIT did not return')
                self.assertEqual(a.frame, b.frame, f'{name}: after EXIT the screen differs from the base')


@unittest.skipUnless(available() and STOCK.exists() and DOOM73.exists(), 'emulator or firmware inputs not present')
class FaultScreen(unittest.TestCase):
    """mods/fault_screen on the whole firmware: HOLD + ROLL faults on purpose, the four hooked vectors reach the handler, and the
    screen it draws by polling the display port is what the controller model shows, on every base."""

    @units(1)
    def test_a_fault_on_purpose_is_shown_and_the_unit_stands(self):
        from test_fault_screen import expected
        for name, base in BASES:
            with self.subTest(base=name), tempfile.TemporaryDirectory() as d:
                manifest = build(ROOT/'mods/fault_screen', base, Path(d)/'pkg')
                candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
                shown = int(manifest['symbols']['fault_screen_shown'], 16)
                with Emulator(candidate) as unit:
                    boot(unit)
                    self.assertEqual(unit.read_u32(shown), 0)
                    unit.hold('HOLD')
                    time.sleep(0.1)
                    unit.press('ROLL')
                    unit.release('HOLD')
                    time.sleep(3)
                    self.assertEqual(unit.read_u32(shown), 1)
                    first = unit.frame
                    time.sleep(3)
                    self.assertEqual(unit.frame, first, 'the unit should stand on the fault screen')
                px = [[bool(first[y*16+x//8] & (0x80 >> (x % 8))) for x in range(128)] for y in range(64)]
                want = expected({0: ['404LAB FAULT SCREEN'], 2: ['USAGE FAULT'], 5: ['CFSR', '00010000'], 7: ['PHOTO THIS, POWER OFF']})
                for y in list(range(0, 24))+list(range(40, 48))+list(range(56, 64)):
                    self.assertEqual(px[y], want[y], f'{name}, row {y}')


@unittest.skipUnless(available() and STOCK.exists() and PROJECT_DRIVE.exists(), 'emulator, firmware or a project drive not present')
class WithAProject(unittest.TestCase):
    """A real project on the internal drive, so pads make sound. The drive is the user's own and is not in this repository."""

    @units(6)
    def test_recorded_verdicts_still_hold(self):
        # A sample of confirmed bindings of each kind, against the record in knowledge/observations. The full sweep is `python -m lab404 sweep`.
        record = json.loads((ROOT/'knowledge/observations/stock-5.52.json').read_text(encoding='utf-8'))['verdicts']
        bindings = {b['id']: b for b in Knowledge().bindings['stock-5.52']['bindings']}
        kinds = {}
        for binding_id, entry in record.items():
            signature = signature_for(bindings[binding_id])
            if entry['verdict'] == 'confirmed':
                kinds.setdefault(next(iter(signature)), []).append(binding_id)
        self.assertEqual(set(kinds), {'page', 'led', 'audio', 'left'})
        picked = {i for ids in kinds.values() for i in ids[:3]}
        jobs = select(jobs_for(list(bindings.values()))[0], picked)
        image = STOCK.read_bytes()
        with ThreadPoolExecutor(6) as pool:
            done = {r['id']: r for r in pool.map(lambda job: run_job(job, image, 'stock-5.52', PROJECT_DRIVE), jobs)}
        for binding_id in picked:
            run = done[binding_id]
            got = classify(run, done[control_id(run['screen'], run['gesture'])], signature_for(bindings[binding_id]))
            self.assertEqual(got[0], 'confirmed', f'{binding_id}: {got[1]}')

    @units(6)
    def test_every_route_arrives(self):
        # The routes that key checks rely on really reach their screens, and a control job with no input stays quiet on a screen meant to be still.
        def go(screen):
            job = dict(id=f'control-{screen}', screen=screen, route=ROUTES[screen], keys=['EXIT'], gesture='press', control=True)
            return screen, run_job(job, STOCK.read_bytes(), 'stock-5.52', PROJECT_DRIVE)['arrived']
        with ThreadPoolExecutor(6) as pool:
            got = dict(pool.map(go, ROUTES))
        self.assertEqual({s: a for s, a in got.items() if a != 'arrived'}, {})

    def test_a_hook_in_the_voice_renderer_fires_and_pads_sound_the_same(self):
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d)/'mod'
            shutil.copytree(MOD, mod)
            spec = json.loads((mod/'mod.json').read_text(encoding='utf-8'))
            spec['hooks'][0] = dict(kind='entry', address=VOICE_RENDERER, function='demo_counter_hook')
            spec['bases'] = spec['bases'][:1]
            (mod/'mod.json').write_text(json.dumps(spec), encoding='utf-8')
            manifest = build(mod, STOCK, Path(d)/'pkg')
            candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
        counter = int(manifest['symbols']['demo_counter_calls'], 16)

        def play(unit):
            boot(unit)
            peaks = []
            for pad in PADS_PLAYED:
                unit.audio_peak = 0
                unit.press(pad, hold=0.3, settle=0.7)
                peaks.append(unit.audio_peak)
            return peaks

        with Emulator(STOCK.read_bytes(), drive=PROJECT_DRIVE) as base, Emulator(candidate, drive=PROJECT_DRIVE) as modded:
            first, second = together(play, base, modded)
            calls = modded.read_u32(counter)
        self.assertGreater(max(first), 0, 'no pad made a sound: the comparison would be empty')
        self.assertEqual(first, second, 'pad peaks differ between base and candidate')
        self.assertGreater(calls, 0, 'the voice renderer hook never fired')

    @units(1)
    def test_the_mixer_helper_is_not_on_the_ordinary_pad_path(self):
        # Why the Unicorn scenario on 0x15FEE says nothing about ordinary pad playing. Recorded in knowledge as hook.helper-15fee-not-on-pad-path.
        with tempfile.TemporaryDirectory() as d:
            manifest = build(MOD, STOCK, Path(d)/'pkg')
            candidate = (Path(d)/'pkg/SP404MKII_APP1.bin').read_bytes()
        with Emulator(candidate, drive=PROJECT_DRIVE) as unit:
            boot(unit)
            unit.audio_peak = 0
            for pad in PADS_PLAYED:
                unit.press(pad, hold=0.3, settle=0.7)
            self.assertGreater(unit.audio_peak, 0)
            self.assertEqual(unit.read_u32(int(manifest['symbols']['demo_counter_calls'], 16)), 0)


@unittest.skipUnless(available() and STOCK.exists() and PROJECT_DRIVE.exists(), 'emulator, firmware or a project drive not present')
class StockSaverLeak(unittest.TestCase):
    """st.ui.saver-leak on unmodified stock 5.52: each start of the Custom screensaver keeps about 66 KB of the malloc pool when
    the project holds its four screen_saver pictures. The other types keep nothing. Measured with the pool walk of
    Emulator.malloc_pool, which reads the RTOS records from outside."""

    @staticmethod
    def choose_custom(unit):
        # SYSTEM (SHIFT + pad 12), GENERAL tab (CTRL3 to one end), row 7 Scrn Saver Type, two steps from OldRave to Custom.
        unit.shift(True)
        unit.press('PAD12')
        unit.shift(False)
        time.sleep(1.5)
        unit.turn_control('CTRL3', 5)
        time.sleep(1)
        for _ in range(6):
            unit.turn(1, settle=0.4)
        unit.press('VALUE', settle=0.8)
        unit.turn(1, settle=0.5)
        unit.turn(1, settle=0.5)
        unit.press('VALUE', settle=0.8)
        for _ in range(8):
            if unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF == MAIN_PAGE:
                break
            unit.press('EXIT', settle=1.2)
        assert unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF == MAIN_PAGE, 'could not leave SYSTEM'

    @staticmethod
    def cycle(unit):
        """One screensaver start and wake. The screensaver object word 0x80249730 is non-zero while it runs (st.ui.flags)."""
        start = time.time()
        while time.time()-start < 150 and not unit.read_u32(0x80249730):
            time.sleep(2)
        assert unit.read_u32(0x80249730), 'the screensaver did not start'
        time.sleep(5)
        unit.press('EXIT', settle=2)
        assert not unit.read_u32(0x80249730), 'the screensaver did not end'
        time.sleep(2)
        return unit.malloc_pool()['free']

    @units(1)
    def test_custom_keeps_about_66_kb_a_start_and_the_default_type_nothing(self):
        with Emulator(STOCK.read_bytes(), drive=str(PROJECT_DRIVE)) as unit:
            boot(unit)
            time.sleep(2)
            start = unit.malloc_pool()['free']
            default = self.cycle(unit)
            self.choose_custom(unit)
            time.sleep(2)
            before = unit.malloc_pool()['free']
            first = self.cycle(unit)
            second = self.cycle(unit)
        self.assertEqual(default, start, 'the default type (OldRave) should give back what it took')
        for lost in (before-first, first-second):
            self.assertTrue(60000 <= lost <= 72000, lost)


if __name__ == '__main__':
    unittest.main()
