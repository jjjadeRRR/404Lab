"""What the emulator can see after an input, and how inputs are performed. No emulator or firmware needed: these run on a fake unit."""
import hashlib
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from lab404.emulator import CONTROLS_NOT_ON_THE_LINK, FRAME_BYTES, KEY_LEDS, KEYS, Emulator, control_route
from lab404.knowledge import Knowledge
from lab404.observe import NO_ROUTE, ROUTE_PAGE, ROUTES, LedState, Observation, Untouched, arrival, changes, classify, control_id, do_step, evidence_for, failed_ids, jobs_for, perform, record_sweep, select, signature_for, summarise, sweep


class FakeUnit:
    def __init__(self):
        self.log = []

    def hold(self, name):
        self.log.append(('hold', name))

    def release(self, name):
        self.log.append(('release', name))

    def press(self, name, **_):
        self.log.append(('press', name))

    def turn_control(self, name, step):
        self.log.append(('turn', name, step))

    def wait(self, seconds):
        self.log.append(('wait', seconds))


def obs(**fields):
    base = dict(page=1, frame='a', lit=10, leds={}, audio_peak=0, parameter_writes=0)
    return Observation(**{**base, **fields})


class ScriptedUnit(Emulator):
    """The real waiting logic, on a scripted screen: (seconds, page, lit) steps, without starting a machine."""

    def __init__(self, script):
        super().__init__(b'')
        self.script, self.started = script, time.time()

    def _now(self):
        at = time.time()-self.started
        return next((step for step in self.script if at < step[0]), self.script[-1])

    def read_u32(self, address):
        return 0xFFFF0000+self._now()[1]

    def wait_until_stable(self, timeout=60, quiet=3.0):
        raise AssertionError('not expected')


class ReadyMeansTheMainScreen(unittest.TestCase):
    def test_a_logo_that_stays_still_is_not_the_main_screen(self):
        unit = ScriptedUnit([(1.0, 2, 500), (9, 1, 1981)])

        def machine():
            for _ in range(40):
                unit.frame = bytes([unit._now()[2] & 255])*FRAME_BYTES
                unit.audio_frames += 64
                time.sleep(0.05)
        threading.Thread(target=machine, daemon=True).start()
        self.assertTrue(unit.wait_for_main(timeout=5, quiet=0.2))
        self.assertGreaterEqual(time.time()-unit.started, 1.0, 'it returned during the logo')

    def test_a_machine_that_stopped_is_not_ready_even_on_a_still_main_screen(self):
        unit = ScriptedUnit([(99, 1, 500)])
        unit.frame = bytes([1])*FRAME_BYTES
        self.assertFalse(unit.wait_for_main(timeout=0.5, quiet=0.1), 'no audio blocks arrived, so nothing shows the machine is running')

    def test_never_reaching_the_main_screen_is_a_timeout(self):
        unit = ScriptedUnit([(99, 2, 500)])
        unit.frame = bytes([1])*FRAME_BYTES
        self.assertFalse(unit.wait_for_main(timeout=0.5, quiet=0.1))


class Leds(unittest.TestCase):
    def test_the_latest_write_on_either_page_wins(self):
        leds = LedState()
        leds.feed([bytes.fromhex('01004 0ff'.replace(' ', '')), bytes.fromhex('0101401f')])
        self.assertEqual(leds.snapshot(), {0x40: 'steady:31'})

    def test_blink_and_pulse_are_told_apart_and_a_steady_write_stops_them(self):
        leds = LedState()
        leds.feed([bytes.fromhex('0106013f'), bytes.fromhex('0109 3a ff'.replace(' ', ''))])
        self.assertEqual(leds.snapshot(), {0x01: 'blink:63', 0x3A: 'pulse9:255'})
        leds.feed([bytes.fromhex('0100 01 00'.replace(' ', ''))])
        self.assertEqual(leds.snapshot()[0x01], 'steady:0')

    def test_other_traffic_is_not_a_light(self):
        leds = LedState()
        leds.feed([bytes.fromhex('00ff0401'), bytes.fromhex('04f04110'), bytes.fromhex('0104000c')])
        self.assertEqual(leds.snapshot(), {})

    def test_slow_and_fast_pulse_stay_different(self):
        leds = LedState()
        leds.feed([bytes.fromhex('010701ff'), bytes.fromhex('010902ff')])
        self.assertEqual(leds.snapshot(), {0x01: 'pulse7:255', 0x02: 'pulse9:255'})


class SysEx(unittest.TestCase):
    def test_a_parameter_write_is_read_out_of_its_packets(self):
        leds = LedState()
        # F0 41 10 00 00 00 00 08 12 | address 02 01 00 1E | data 05 | checksum | F7, in 3-byte MIDI-over-USB groups.
        groups = ['f04110', '000000', '000812', '020100', '1e0552', 'f7']
        leds.feed([bytes.fromhex('04'+g) for g in groups[:-1]]+[bytes.fromhex('05f70000')])
        self.assertEqual(leds.parameter_writes, 1)
        self.assertEqual(leds.parameter_addresses, ['0201001e'])

    def test_other_sysex_is_not_a_parameter_write(self):
        leds = LedState()
        leds.feed([bytes.fromhex('04f07e7f'), bytes.fromhex('0506f700')])
        self.assertEqual(leds.parameter_writes, 0)


class Changes(unittest.TestCase):
    def test_nothing_changed(self):
        self.assertEqual(changes(obs(), obs()), {})

    def test_each_signal_is_reported(self):
        got = changes(obs(), obs(page=4, frame='b', leds={0x40: 'steady:255'}, audio_peak=9, parameter_writes=3))
        self.assertEqual(got, {'page': [1, 4], 'screen': True, 'leds': {'0x40': [None, 'steady:255']}, 'audio_peak': 9, 'parameter_writes': 3})

    def test_a_write_that_changes_no_light_is_not_a_change(self):
        self.assertEqual(changes(obs(leds={0x40: 'steady:31'}), obs(leds={0x40: 'steady:31'})), {})


class Perform(unittest.TestCase):
    """Each phase of an input is looked at separately, so a modifier's own action is not credited to the chord, and a short-lived menu is not missed."""

    def run_input(self, keys, gesture):
        unit = FakeUnit()
        seen = perform(unit, keys, gesture, lambda: len(unit.log))
        return [x for x in unit.log if x[0] != 'wait'], seen, unit

    def test_a_modifier_is_held_around_the_key(self):
        moves, seen, _ = self.run_input(['SHIFT', 'LOOP'], 'press')
        self.assertEqual(moves, [('hold', 'SHIFT'), ('hold', 'LOOP'), ('release', 'LOOP'), ('release', 'SHIFT')])
        self.assertEqual(list(seen), ['modifiers', 'down', 'up', 'released'])

    def test_a_single_key_has_no_modifier_phase(self):
        _, seen, _ = self.run_input(['LOOP'], 'press')
        self.assertEqual(list(seen), ['down', 'up', 'released'])

    def test_a_held_gesture_is_looked_at_while_held(self):
        moves, seen, unit = self.run_input(['SHIFT', 'MARK'], 'hold')
        self.assertEqual(moves, [('hold', 'SHIFT'), ('hold', 'MARK'), ('release', 'MARK'), ('release', 'SHIFT')])
        self.assertEqual(list(seen), ['modifiers', 'down', 'up', 'released'])
        self.assertGreaterEqual(sum(x[1] for x in unit.log if x[0] == 'wait'), 3, 'three-second holds must really last')

    def test_a_turn_turns_the_turnable_control_whatever_its_position(self):
        moves, seen, _ = self.run_input(['VALUE', 'ROLL'], 'turn')
        self.assertEqual(moves, [('hold', 'ROLL'), ('turn', 'VALUE', 1), ('release', 'ROLL')])
        self.assertEqual(list(seen), ['modifiers', 'down', 'released'])

    def test_with_two_turnable_controls_the_last_turns_and_the_first_is_held(self):
        moves, _, _ = self.run_input(['VALUE', 'CTRL1'], 'turn')
        self.assertEqual(moves, [('hold', 'VALUE'), ('turn', 'CTRL1', 1), ('release', 'VALUE')])

    def test_a_turn_without_a_turnable_control_is_refused(self):
        with self.assertRaises(ValueError):
            perform(FakeUnit(), ['LOOP'], 'turn', lambda: None)

    def test_power_on_and_press_turn_are_refused_rather_than_approximated(self):
        for gesture in ('power_on', 'press_turn'):
            with self.assertRaises(ValueError):
                perform(FakeUnit(), ['VALUE'], gesture, lambda: None)

    def test_a_control_takes_the_same_time_and_touches_nothing(self):
        for keys, gesture in ((['A', 'B'], 'press'), (['A', 'B'], 'hold'), (['A', 'VALUE'], 'turn')):
            pressed, idle = FakeUnit(), FakeUnit()
            perform(pressed, keys, gesture, lambda: None)
            perform(Untouched(idle), keys, gesture, lambda: None)
            self.assertEqual({x[0] for x in idle.log}, {'wait'})
            self.assertAlmostEqual(sum(x[1] for x in idle.log), sum(x[1] for x in pressed.log if x[0] == 'wait'), places=3)


class Coverage(unittest.TestCase):
    """Every recorded stock binding is either tried or named as not tried. Nothing silently drops out."""

    def setUp(self):
        self.stock = Knowledge().bindings['stock-5.52']['bindings']

    def test_every_control_in_a_stock_binding_can_be_reached(self):
        for binding in self.stock:
            for key in binding['keys']:
                self.assertIsNotNone(control_route(key), f'{binding["id"]}: no way to operate {key}')

    def test_controls_off_the_link_are_named(self):
        self.assertLessEqual({'VOLUME', 'INPUT GAIN', 'MIC/GUITAR', 'POWER'}, set(CONTROLS_NOT_ON_THE_LINK))

    def test_every_binding_gets_a_job_or_a_stated_reason(self):
        jobs, skipped = jobs_for(self.stock)
        tried = [j['id'] for j in jobs if not j['control']]
        self.assertEqual(len(tried)+len(skipped), len(self.stock))
        self.assertEqual(set(tried) | set(skipped), {b['id'] for b in self.stock})
        for reason in skipped.values():
            self.assertTrue(reason.strip())

    def test_every_screen_with_bindings_has_a_route(self):
        for binding in self.stock:
            self.assertIn(binding['screen'], {**ROUTES, **NO_ROUTE, 'any': [], 'power-on': []}, binding['id'])

    def test_a_screen_without_a_route_says_why(self):
        jobs, skipped = jobs_for([dict(id='x', screen='skipback', keys=['REC'], gesture='press')])
        self.assertEqual(jobs, [])
        self.assertEqual(skipped['x'], NO_ROUTE['skipback'])

    def test_each_screen_and_gesture_has_a_matching_control(self):
        jobs, _ = jobs_for(self.stock)
        controls = {(j['screen'], j['gesture']) for j in jobs if j['control']}
        self.assertEqual(controls, {(j['screen'], j['gesture']) for j in jobs if not j['control']})
        for job in jobs:
            if job['control']:
                self.assertTrue(job['keys'], 'a control copies the shape of the input it stands in for')
                self.assertEqual(job['id'], control_id(job['screen'], job['gesture']))


class RouteArrival(unittest.TestCase):
    def test_every_route_says_which_page_it_must_reach(self):
        self.assertEqual(set(ROUTES)-set(ROUTE_PAGE), set())

    def test_a_job_that_missed_its_screen_is_not_an_observation_of_it(self):
        self.assertEqual(arrival('pitch-speed', 4), 'arrived')
        self.assertEqual(arrival('pitch-speed', 1), 'missed')
        self.assertEqual(arrival('pitch-speed', None), 'unknown')

    def test_a_binding_for_any_screen_is_tried_away_from_home(self):
        jobs, _ = jobs_for([dict(id='x', screen='any', keys=['EXIT'], gesture='press')])
        self.assertEqual(jobs[0]['screen'], 'pitch-speed')


class Signatures(unittest.TestCase):
    """What would count as proof is declared from the binding alone, before anything runs."""

    def binding(self, action, keys=('LOOP',), screen='sample'):
        return dict(id='x', screen=screen, keys=list(keys), gesture='press', action=action)

    def test_opening_a_screen_means_its_page(self):
        self.assertEqual(signature_for(self.binding('Open pitch/speed screen')), dict(page=4))
        self.assertEqual(signature_for(self.binding('Open the utility menu')), dict(page=45))

    def test_a_toggle_means_its_own_light(self):
        self.assertEqual(signature_for(self.binding('Toggle loop')), dict(led=['0x40']))

    def test_playing_means_sound(self):
        self.assertEqual(signature_for(self.binding('Play the sample on pad 3', ['PAD3'])), dict(audio=True))

    def test_a_step_toggle_means_that_pads_lights(self):
        self.assertEqual(signature_for(self.binding('Toggle step 2 of the current bar', ['PAD2'])), dict(led=['0x03', '0x04', '0x05']))

    def test_leaving_means_the_page_changes(self):
        self.assertEqual(signature_for(self.binding('Leave', ['EXIT'], 'utility-menu')), dict(left=True))

    def test_resampling_has_its_own_page(self):
        self.assertEqual(signature_for(self.binding('Open resample standby')), dict(page=14))

    def test_anything_else_has_no_signature(self):
        self.assertIsNone(signature_for(self.binding('Metronome volume')))

    def test_every_light_named_is_a_real_control(self):
        self.assertLessEqual(set(KEY_LEDS), set(KEYS) | {'SHIFT', 'SUB PAD'})


FAKE_MACHINE = '''#!/usr/bin/env python3
# Stands in for the emulator: says a lot on stderr, as the real one does at boot, and only then sends a screen. A blocked stderr would stop it, as it stopped real boots.
import socket, struct, sys, time
path = next(arg for arg in sys.argv if 'path=' in arg).split('path=')[1].split(',')[0]
server = socket.socket(socket.AF_UNIX)
server.bind(path)
server.listen()
link, _ = server.accept()
sys.stderr.write('x' * 1000000)
sys.stderr.write('the last line said')
sys.stderr.flush()
link.sendall(struct.pack('<BBH', 1, 0, 1024) + bytes(1024))
time.sleep(30)
'''


NOT_ON_WINDOWS = unittest.skipIf(sys.platform == 'win32', 'the emulator uses unix sockets and runs on Linux (WSL on Windows), docs/STAND.md')


@NOT_ON_WINDOWS
class EmulatorOutput(unittest.TestCase):
    """A machine that talks a lot must never stall because nobody listens. An unread stderr pipe left boots blank: 1 frame, no audio, the processor stuck writing."""

    def test_a_talkative_machine_does_not_stall_and_its_words_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d)/'qemu'
            fake.write_text(FAKE_MACHINE, encoding='utf-8')
            fake.chmod(0o755)
            with Emulator(b'', qemu=fake) as unit:
                end = time.time()+5
                while unit.frames == 0 and time.time() < end:
                    time.sleep(0.05)
                self.assertEqual(unit.frames, 1, 'the machine stalled on its own output')
                self.assertIn('the last line said', unit.output_tail())


@NOT_ON_WINDOWS
class Monitor(unittest.TestCase):
    def test_a_closed_monitor_is_an_error_not_a_hang(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'m.sock'
            server = socket.socket(socket.AF_UNIX)
            server.bind(str(path))
            server.listen()

            def closes_at_once():
                connection, _ = server.accept()
                connection.close()
            threading.Thread(target=closes_at_once, daemon=True).start()
            unit = Emulator(b'')
            unit.monitor_path = path
            result = []
            reader = threading.Thread(target=lambda: result.append(_attempt(unit)), daemon=True)
            reader.start()
            reader.join(3)
            server.close()
            self.assertFalse(reader.is_alive(), 'read_u32 never returned')
            self.assertIsInstance(result[0], (OSError, RuntimeError))


def _attempt(unit):
    try:
        return unit.read_u32(0x80245880)
    except Exception as e:
        return e


class Classify(unittest.TestCase):
    """A verdict needs a declared signature, a valid arrival and a matching control. Silence is never a contradiction."""

    def record(self, **fields):
        return dict(id='k', state='observed', screen='s', arrived='arrived', settled=True, frame='f', keys=['A'], gesture='press', changes={}, phases={}, **fields)

    def control(self, **changes):
        return dict(state='observed', arrived='arrived', settled=True, frame='f', changes=changes)

    def test_a_declared_page_reached_is_confirmed(self):
        record = self.record(after_page=4)
        record['changes'] = {'page': [1, 4]}
        self.assertEqual(classify(record, self.control(), dict(page=4))[0], 'confirmed')

    def test_another_page_reached_is_contradicted(self):
        record = self.record(after_page=9)
        record['changes'] = {'page': [1, 9]}
        self.assertEqual(classify(record, self.control(), dict(page=4))[0], 'contradicted')

    def test_silence_is_no_reaction_even_with_a_signature(self):
        self.assertEqual(classify(self.record(after_page=1), self.control(), dict(page=4))[0], 'no-reaction')

    def test_a_change_without_a_signature_is_only_a_reaction(self):
        record = self.record(after_page=1)
        record['changes'] = {'screen': True}
        self.assertEqual(classify(record, self.control(), None)[0], 'reacted')

    def test_what_the_control_also_shows_is_not_attributed_to_the_input(self):
        record = self.record(after_page=1)
        record['changes'] = {'screen': True}
        self.assertEqual(classify(record, self.control(screen=True), None)[0], 'no-reaction')

    def test_a_change_seen_only_in_a_phase_counts(self):
        record = self.record(after_page=1)
        record['phases'] = {'down': {'screen': True}}
        self.assertEqual(classify(record, self.control(), None)[0], 'reacted')

    def test_the_signature_can_be_met_during_a_phase(self):
        record = self.record(after_page=1)
        record['phases'] = {'down': {'page': [1, 4]}}
        self.assertEqual(classify(record, self.control(), dict(page=4))[0], 'confirmed')

    def test_a_modifier_alone_does_not_confirm_the_chord(self):
        record = self.record(after_page=4)
        record['keys'] = ['SHIFT', 'A']
        record['changes'] = {'page': [1, 4]}
        record['phases'] = {'modifiers': {'page': [1, 4]}}
        self.assertEqual(classify(record, self.control(), dict(page=4))[0], 'reacted')

    def test_a_declared_light_change(self):
        record = self.record(after_page=1)
        record['changes'] = {'leds': {'0x40': ['steady:31', 'steady:255']}}
        self.assertEqual(classify(record, self.control(), dict(led=['0x40']))[0], 'confirmed')
        self.assertEqual(classify(record, self.control(), dict(led=['0x41']))[0], 'reacted')

    def test_declared_sound(self):
        record = self.record(after_page=1)
        record['changes'] = {'audio_peak': 300}
        self.assertEqual(classify(record, self.control(), dict(audio=True))[0], 'confirmed')

    def test_a_missed_route_or_another_starting_picture_is_unobserved(self):
        self.assertEqual(classify({**self.record(), 'arrived': 'missed'}, self.control(), None)[0], 'unobserved')
        self.assertEqual(classify({**self.record(), 'frame': 'other'}, self.control(), None)[0], 'unobserved')
        self.assertEqual(classify(dict(id='k', state='failed', error='x'), self.control(), None)[0], 'unobserved')

    def test_no_usable_control_is_unobserved(self):
        self.assertEqual(classify(self.record(), None, None)[0], 'unobserved')
        self.assertEqual(classify(self.record(), dict(state='failed'), None)[0], 'unobserved')


class Selecting(unittest.TestCase):
    def test_a_selection_brings_the_controls_it_needs(self):
        jobs, _ = jobs_for([dict(id='a', screen='sample', keys=['LOOP'], gesture='press'), dict(id='b', screen='envelope', keys=['LOOP'], gesture='press')])
        self.assertEqual(sorted(j['id'] for j in select(jobs, {'a'})), ['a', control_id('sample', 'press')])

    def test_failed_ids_are_read_from_an_earlier_run(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)/'run.jsonl'
            run.write_text('\n'.join(json.dumps(x) for x in (dict(experiment='e'), dict(id='a', state='failed'), dict(id='b', state='observed')))+'\n', encoding='utf-8')
            self.assertEqual(failed_ids(run), {'a'})


class Recording(unittest.TestCase):
    bindings = [dict(id='a', screen='sample', keys=['LOOP'], gesture='press', action='Toggle loop'), dict(id='b', screen='sample', keys=['GATE'], gesture='press', action='Do a thing'),
                dict(id='c', screen='sample', keys=['DEL'], gesture='press', action='Other thing'), dict(id='d', screen='power-on', keys=['SHIFT'], gesture='power_on', action='Update')]

    def runs(self):
        common = dict(state='observed', screen='sample', arrived='arrived', settled=True, frame='f', gesture='press', after_page=1, phases={}, control=False)
        control = dict(id=control_id('sample', 'press'), **{**common, 'control': True}, changes={}, keys=['X'])
        first = [control, dict(id='a', **common, keys=['LOOP'], changes={'leds': {'0x40': ['steady:31', 'steady:255']}, 'audio_peak': 77}), dict(id='b', **common, keys=['GATE'], changes={'screen': True}),
                 dict(id='c', state='failed', error='hung')]
        second = [control, dict(id='c', **common, keys=['DEL'], changes={})]
        return [first, second]

    def test_a_later_run_replaces_a_failed_job_and_each_is_judged_by_its_own_control(self):
        record = summarise(self.runs(), self.bindings, {})
        self.assertEqual({k: v['verdict'] for k, v in record['verdicts'].items()}, dict(a='confirmed', b='reacted', c='no-reaction'))

    def test_what_was_not_tried_is_listed_with_its_reason(self):
        self.assertEqual(summarise(self.runs(), self.bindings, {'d': 'needs power-on'})['not_tried'], {'d': 'needs power-on'})

    def test_nothing_from_the_users_project_or_roland_screens_is_kept(self):
        text = json.dumps(summarise(self.runs(), self.bindings, {}))
        self.assertNotIn('audio_peak', text)
        self.assertNotIn('frame', text)

    def test_only_a_seen_effect_becomes_evidence(self):
        record = summarise(self.runs(), self.bindings, {})
        self.assertIn('confirmed', evidence_for('a', record)['source'])
        self.assertIn('meaning not proven', evidence_for('b', record)['source'])
        self.assertIsNone(evidence_for('c', record))
        self.assertIsNone(evidence_for('d', record))
        self.assertEqual(evidence_for('a', record)['label'], 'EMULATOR')


STOCK_SHA = '4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80'


class RecordingKeepsFiles(unittest.TestCase):
    def test_the_binding_file_keeps_its_compact_form(self):
        binding = dict(id='a', screen='sample', keys=['LOOP'], gesture='press', action='Toggle loop', status='verified', evidence=[dict(label='DOC', source='s')])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'bindings').mkdir()
            path = root/'bindings/stock-5.52.json'
            path.write_text(json.dumps(dict(firmware='stock-5.52', coverage={}, bindings=[binding]), separators=(',', ':'), ensure_ascii=False)+'\n', encoding='utf-8')
            run = root/'run.jsonl'
            run.write_text(json.dumps(dict(experiment=dict(firmware='stock-5.52', drive='x', image_sha256=STOCK_SHA, bindings_sha256=hashlib.sha256(path.read_bytes()).hexdigest())))+'\n', encoding='utf-8')
            record_sweep('stock-5.52', [run], root)
            self.assertEqual(path.read_text(encoding='utf-8').count('\n'), 1)
            self.assertNotIn('drive', json.loads((root/'observations/stock-5.52.json').read_text(encoding='utf-8'))['experiments'][0])


class Sweep(unittest.TestCase):
    def test_a_results_file_from_another_experiment_is_refused(self):
        jobs = [dict(id='j0', screen='s', route=[], keys=['LOOP'], gesture='press', control=False)]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'out.jsonl'
            sweep(jobs, lambda job: dict(id=job['id'], state='observed'), out, workers=1, experiment=dict(firmware='a'))
            self.assertEqual(json.loads(out.read_text(encoding='utf-8').splitlines()[0])['experiment'], dict(firmware='a'))
            with self.assertRaises(ValueError):
                sweep(jobs, lambda job: dict(id=job['id'], state='observed'), out, workers=1, experiment=dict(firmware='b'))
            self.assertEqual(sweep(jobs, lambda job: 1/0, out, workers=1, experiment=dict(firmware='a')), 0)

    def test_results_land_on_disk_as_they_come_and_a_rerun_continues(self):
        jobs = [dict(id=f'j{i}', screen='s', route=[], keys=['LOOP'], gesture='press', control=False) for i in range(3)]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'out.jsonl'
            calls = []

            def first(job):
                calls.append(job['id'])
                if job['id'] == 'j1':
                    raise KeyboardInterrupt
                return dict(id=job['id'], state='observed')

            with self.assertRaises(KeyboardInterrupt):
                sweep(jobs, first, out, workers=1)
            self.assertEqual([json.loads(x)['id'] for x in out.read_text(encoding='utf-8').splitlines() if 'id' in json.loads(x)], ['j0'])
            calls.clear()
            sweep(jobs, lambda job: calls.append(job['id']) or dict(id=job['id'], state='observed'), out, workers=1)
            self.assertEqual(sorted(calls), ['j1', 'j2'])
            self.assertEqual(sorted(json.loads(x)['id'] for x in out.read_text(encoding='utf-8').splitlines() if 'id' in json.loads(x)), ['j0', 'j1', 'j2'])

    def test_a_failed_boot_is_recorded_and_not_retried(self):
        jobs = [dict(id='j0', screen='s', route=[], keys=['LOOP'], gesture='press', control=False)]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'out.jsonl'
            calls = []

            def fails(job):
                calls.append(job['id'])
                raise RuntimeError('no stable screen')

            sweep(jobs, fails, out, workers=1)
            record = json.loads(out.read_text(encoding='utf-8').splitlines()[-1])
            self.assertEqual(record['state'], 'failed')
            self.assertIn('no stable screen', record['error'])
            self.assertEqual(calls, ['j0'])


if __name__ == '__main__':
    unittest.main()
