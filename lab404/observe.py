"""Press a recorded key binding on the whole-firmware emulator and write down what could be seen, then say what that does and does not establish.

Five signals are visible: the screen picture, the firmware's current-page word, the lights it sends, the effect parameters it sends to the second processor, and audio peak
(meaningful only with a project on the drive).

Rules that keep this honest:
- Each job gets a fresh boot, because many inputs change state (DEL, REC).
- Each screen and gesture gets a control that goes through the same motions and touches nothing. What the control also shows is not credited to the input.
- Every phase of an input is looked at: modifiers down, key down, key up, all released. What a modifier does alone is not credited to the chord.
- What would prove a binding is declared from its description before running (`signature_for`). Without a declared signature a change is only a reaction.
- A failed boot is written down and never retried, so failures stay visible and countable. Silence is never a contradiction: the action may need a condition this run lacks.
"""
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import emulator as emulator_module
from .emulator import CONTROLS_NOT_ON_THE_LINK, KEY_LEDS, KNOBS, MAIN_PAGE_WORD, Emulator, lit_pixels

PAGE_WORD = {'stock-5.52': MAIN_PAGE_WORD, 'doom-os-0.7.3': MAIN_PAGE_WORD, 'doom-os-0.7.4': MAIN_PAGE_WORD}
HOLD_SECONDS = 3.5
LED_MODES = {0: 'steady', 1: 'steady', 6: 'blink', 7: 'pulse7', 9: 'pulse9'}  # BMC light pages [DOC: DM-404's notes]
TURNABLE = ('VALUE', *KNOBS)

TRREC = ['PATTERN SELECT', 'REC', 'PAD16', 'REMAIN', 'REC']
# How to reach each screen from a fresh boot. 'A+B' is A held while B is pressed; '~1' turns VALUE one detent. Each was checked by eye on stock 5.52 with a project on the
# drive, and its page number is what a run must find on arrival [EMULATOR: test_every_route_arrives]. Some screens share a page, so a job's starting picture must also match its control.
ROUTES = {
    'sample': [], 'pattern-select': ['PATTERN SELECT'], 'pattern-rec': ['PATTERN SELECT', 'REC', 'PAD16'], 'tr-rec': TRREC,
    'pattern-edit': ['PATTERN SELECT', 'PATTERN EDIT'], 'pattern-chain': ['PATTERN SELECT', 'HOLD+PAD1'], 'sampling': ['REC'],
    'looper': ['SHIFT+VALUE', '~1', 'VALUE', 'MARK'], 'sound-gen': ['SHIFT+RECORD SETTING'], 'sample-edit': ['START/END', 'PAD1'],
    'marker-edit': ['PAD1', 'SHIFT+START/END'], 'envelope': ['SHIFT+PITCH/SPEED'], 'pitch-speed': ['PITCH/SPEED'], 'chromatic': ['PAD1', 'SHIFT+PAD4'],
    'velocity-16': ['PAD1', 'SHIFT+PAD2'], 'tempo-sel': ['SHIFT+PAD11'], 'efx-edit': ['REMAIN+DELAY'], 'dj-mode': ['BANK D/I+BANK E/J'],
    'utility-menu': ['SHIFT+PAD13'], 'system': ['SHIFT+PAD12'], 'efx-set': ['SHIFT+PAD16'], 'pad-set': ['SHIFT+PAD15'], 'import-export': ['SHIFT+PAD14'],
    'select-project': ['SHIFT+SUB PAD'], 'input-setting': ['SHIFT+EXT SOURCE'], 'pad-link': ['SHIFT+PAD7'], 'mute-group': ['SHIFT+PAD8'],
    'exchange': ['SHIFT+PAD5'], 'sample-merge': ['SHIFT+RESAMPLE'], 'bank-volume': ['SHIFT+BANK A/F'], 'copy-select': ['COPY'], 'delete-select': ['DEL'],
    'microscope': [*TRREC, 'PAD1', 'PATTERN EDIT+PAD1'],
}
ROUTE_PAGE = {
    'sample': 1, 'pattern-select': 17, 'pattern-rec': 18, 'tr-rec': 17, 'pattern-edit': 19, 'pattern-chain': 20, 'sampling': 13, 'looper': 39, 'sound-gen': 30, 'sample-edit': 5,
    'marker-edit': 8, 'envelope': 16, 'pitch-speed': 4, 'chromatic': 24, 'velocity-16': 23, 'tempo-sel': 37, 'efx-edit': 34, 'dj-mode': 31, 'utility-menu': 45, 'system': 53,
    'efx-set': 54, 'pad-set': 55, 'import-export': 46, 'select-project': 49, 'input-setting': 22, 'pad-link': 27, 'mute-group': 26, 'exchange': 50, 'sample-merge': 58,
    'bank-volume': 38, 'copy-select': 50, 'delete-select': 50, 'microscope': 42,
}
# Screens known to exist that a run cannot reach yet.
NO_ROUTE = {'skipback': 'needs recorded audio above the skip-back threshold; on the emulator MARK reports no triggered data'}

# Resampling waits on a page of its own. Set after a sweep: 13 was declared first and the run reached 14; the picture, checked by eye, is the same standby as REC.
RESAMPLE_PAGE = 14
# Action text to the screen it says it opens. The page is that screen's arrival page.
OPENS = (('BANK VOLUME', 'bank-volume'), ('16 velocity mode', 'velocity-16'), ('chromatic mode', 'chromatic'), ('exchange', 'exchange'), ('pad link groups', 'pad-link'),
         ('mute groups', 'mute-group'), ('tempo select', 'tempo-sel'), ('SYSTEM screen', 'system'), ('utility menu', 'utility-menu'), ('import/export menu', 'import-export'),
         ('pad settings', 'pad-set'), ('effect settings', 'efx-set'), ('project select', 'select-project'), ('input setting screen', 'input-setting'), ('envelope', 'envelope'),
         ('marker edit', 'marker-edit'), ('sample merge', 'sample-merge'), ('sound generator', 'sound-gen'), ('pad delete selection', 'delete-select'),
         ('copy selection', 'copy-select'), ('sample edit', 'sample-edit'), ('pitch/speed screen', 'pitch-speed'), ('sampling standby', 'sampling'),
         ('pattern edit', 'pattern-edit'))


def signature_for(binding):
    """What, if seen, would establish this binding's documented action. None when nothing visible would."""
    action, key = binding['action'], binding['keys'][-1]
    pad = re.fullmatch(r'PAD(\d+)', key)
    if 'resample standby' in action:
        return dict(page=RESAMPLE_PAGE)
    if action.startswith('Open '):
        return next((dict(page=ROUTE_PAGE[screen]) for text, screen in OPENS if text in action), None)
    if action.startswith('Switch to the pattern sequencer'):
        return dict(page=ROUTE_PAGE['pattern-select'])
    if re.match(r'(Leave|Finish|Back)\b', action):
        return dict(left=True)
    if action.startswith(('Toggle gate', 'Toggle loop', 'Toggle reverse', 'Toggle BPM sync', 'Toggle that effect')) and key in KEY_LEDS:
        return dict(led=[f'0x{KEY_LEDS[key]:02X}'])
    if action.startswith('Toggle step') and pad:
        first = 3*(int(pad[1])-1)
        return dict(led=[f'0x{first+i:02X}' for i in range(3)])
    if action.startswith('Play '):
        return dict(audio=True)
    return None


def arrival(screen, page):
    if page is None:
        return 'unknown'
    return 'arrived' if ROUTE_PAGE[screen] == page else 'missed'


class LedState:
    """The lights as the firmware last set them, where the latest write to a light wins on any page; and the effect parameters it sent."""

    def __init__(self):
        self.lights = {}
        self.parameter_writes = 0
        self.parameter_addresses = []
        self._sysex = bytearray()

    def feed(self, packets):
        for packet in packets:
            for at in range(0, len(packet)-3, 4):
                head, one, two, three = packet[at:at+4]
                kind = head & 0x0F
                if head == 0x01 and one in LED_MODES:
                    self.lights[two] = f'{LED_MODES[one]}:{three}'
                elif kind == 0x04:
                    self._sysex += bytes((one, two, three))
                elif kind in (0x05, 0x06, 0x07) and self._sysex:
                    self._sysex += bytes((one, two, three))[:kind-4]
                    self._finish_sysex()

    def _finish_sysex(self):
        message, self._sysex = bytes(self._sysex), bytearray()
        if message[:3] == b'\xF0\x41\x10' and len(message) > 13 and message[8] == 0x12:  # a Roland data write [DOC: DM-404's notes]
            self.parameter_writes += 1
            self.parameter_addresses.append(message[9:13].hex())

    def clear_counts(self):
        self.parameter_writes = 0
        self.parameter_addresses = []

    def snapshot(self):
        return dict(self.lights)


@dataclass
class Observation:
    page: object
    frame: str
    lit: int
    leds: dict = field(default_factory=dict)
    audio_peak: int = 0
    parameter_writes: int = 0
    parameter_addresses: list = field(default_factory=list)


def changes(before, after):
    """What differs between two observations. Audio and parameter writes are what happened since `before`, so they are taken as they stand."""
    out = {}
    if before.page != after.page:
        out['page'] = [before.page, after.page]
    if before.frame != after.frame:
        out['screen'] = True
    leds = {f'0x{i:02X}': [before.leds.get(i), after.leds.get(i)] for i in sorted(set(before.leds) | set(after.leds)) if before.leds.get(i) != after.leds.get(i)}
    if leds:
        out['leds'] = leds
    if after.audio_peak:
        out['audio_peak'] = after.audio_peak
    if after.parameter_writes:
        out['parameter_writes'] = after.parameter_writes
    if after.parameter_addresses:
        out['parameter_addresses'] = sorted(set(after.parameter_addresses))[:12]
    return out


class Untouched:
    """Stands in for the unit in a control: the same waits, and no control touched."""

    def __init__(self, unit):
        self.wait = unit.wait

    def hold(self, name):
        pass

    def release(self, name):
        pass

    def turn_control(self, name, step):
        pass


def perform(unit, keys, gesture, look):
    """Do one input, looking after each phase. Returns {phase: what `look` returned}."""
    if gesture not in ('press', 'hold', 'turn'):
        raise ValueError(f'gesture {gesture} cannot be performed here')
    seen = {}
    if gesture == 'turn':
        target = next((k for k in reversed(keys) if k in TURNABLE), None)  # with two, as in VALUE+CTRL1, the first is held
        if target is None:
            raise ValueError(f'nothing to turn in {keys}')
        held = [k for k in keys if k != target]
    else:
        held, target = keys[:-1], keys[-1]
    for name in held:
        unit.hold(name)
        unit.wait(0.1)
    if held:
        seen['modifiers'] = look()
    if gesture == 'turn':
        unit.turn_control(target, 1)
        unit.wait(0.6)
        seen['down'] = look()
    else:
        unit.hold(target)
        unit.wait(HOLD_SECONDS if gesture == 'hold' else 0.15)
        seen['down'] = look()
        unit.release(target)
        unit.wait(0.6)
        seen['up'] = look()
    for name in reversed(held):
        unit.release(name)
        unit.wait(0.1)
    unit.wait(0.3)
    seen['released'] = look()
    return seen


def control_id(screen, gesture):
    return f'control-{screen}-{gesture}'


def jobs_for(bindings):
    """(jobs, {binding id: why not tried}). Every binding lands in one or the other. Each screen and gesture tried also gets a control with the same motions."""
    jobs, skipped, shapes = [], {}, {}
    for binding in bindings:
        screen = 'pitch-speed' if binding['screen'] == 'any' else binding['screen']  # 'any': tried away from home, where it has something to do
        if binding['gesture'] not in ('press', 'hold', 'turn'):
            skipped[binding['id']] = 'needs the control down during power-on; a run starts already powered'
        elif set(binding['keys']) & set(CONTROLS_NOT_ON_THE_LINK):
            skipped[binding['id']] = 'a control the firmware cannot see on the emulator'
        elif screen not in ROUTES:
            skipped[binding['id']] = NO_ROUTE.get(screen, f'no known way to reach screen {screen}')
        else:
            jobs.append(dict(id=binding['id'], screen=screen, route=ROUTES[screen], keys=binding['keys'], gesture=binding['gesture'], control=False))
            shapes.setdefault((screen, binding['gesture']), binding['keys'])
    for (screen, gesture), keys in shapes.items():
        jobs.append(dict(id=control_id(screen, gesture), screen=screen, route=ROUTES[screen], keys=keys, gesture=gesture, control=True))
    return jobs, skipped


def select(jobs, ids):
    """Only these jobs, with the controls they are judged against."""
    chosen = [job for job in jobs if job['id'] in ids]
    needed = {control_id(job['screen'], job['gesture']) for job in chosen if not job['control']}
    return chosen+[job for job in jobs if job['id'] in needed and job['id'] not in ids]


def failed_ids(path):
    lines = (json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip())
    return {line['id'] for line in lines if line.get('state') == 'failed'}


class Watcher:
    """Reads one unit's signals. Parameter writes and audio count from the last `reset_counts`."""

    def __init__(self, unit, firmware):
        self.unit, self.word = unit, PAGE_WORD.get(firmware)
        self.leds = LedState()
        self.fed = 0

    def _take(self):
        unit = self.unit
        with unit.lock:
            frame, peak = unit.frame, unit.audio_peak
            packets = unit.bmc_packets[self.fed:]
            self.fed += len(packets)
        self.leds.feed(packets)
        return frame, peak, len(packets)

    def settle(self, quiet=0.5, limit=3.0):
        """Let traffic from the steps before die down, so it is not credited to what comes next. Returns False if it never did within the limit."""
        end = time.monotonic()+limit
        last, since = None, time.monotonic()
        while time.monotonic() < end:
            frame, _, count = self._take()
            if count or frame != last:
                last, since = frame, time.monotonic()
            elif time.monotonic()-since >= quiet:
                return True
            time.sleep(0.05)
        return False

    def reset_counts(self):
        self._take()
        self.leds.clear_counts()
        with self.unit.lock:
            self.unit.audio_peak = 0

    def look(self):
        page = None
        if self.word is not None:
            try:
                page = self.unit.read_u32(self.word) & 0xFFFF
            except (OSError, RuntimeError):
                pass  # stays None: the page is reported unknown, and the picture still counts
        frame, peak, _ = self._take()
        return Observation(page, hashlib.sha256(frame).hexdigest()[:16], lit_pixels(frame), self.leds.snapshot(), peak, self.leds.parameter_writes, list(self.leds.parameter_addresses))


def do_step(unit, step):
    if step.startswith('~'):
        unit.turn_control('VALUE', int(step[1:]))
        unit.wait(0.4)
        return
    perform(unit, _join_filter_drive(step.split('+')), 'press', lambda: None)


def _join_filter_drive(parts):
    """FILTER+DRIVE is one button whose name holds the separator."""
    out, i = [], 0
    while i < len(parts):
        if parts[i] == 'FILTER' and i+1 < len(parts) and parts[i+1] == 'DRIVE':
            out.append('FILTER+DRIVE')
            i += 2
        else:
            out.append(parts[i])
            i += 1
    return out


def run_job(job, image, firmware, drive, shots=None):
    """One fresh boot: reach the screen, let it settle, look, do the input or its control, looking after each phase. Raises if the boot fails."""
    with Emulator(image, drive=drive) as unit:
        if not unit.wait_for_main(45, 3):
            raise RuntimeError(f'no main screen: {unit.frames} frames, {lit_pixels(unit.frame)} lit: {json.dumps(unit.diagnose())}')
        for step in job['route']:
            do_step(unit, step)
        watcher = Watcher(unit, firmware)
        settled = watcher.settle()
        before = watcher.look()
        watcher.reset_counts()
        if shots:
            unit.save_screen(shots/f'{job["id"]}.before.png')
        actor = Untouched(unit) if job['control'] else unit

        looks = []

        def look():
            looks.append(watcher.look())
            if shots:
                unit.save_screen(shots/f'{job["id"]}.{len(looks)}.png')
            return looks[-1]
        seen = perform(actor, job['keys'], job['gesture'], look)
        after = seen['released']
        return dict(id=job['id'], state='observed', screen=job['screen'], keys=job['keys'], gesture=job['gesture'], control=job['control'], settled=settled,
                    arrived=arrival(job['screen'], before.page), page=before.page, frame=before.frame,
                    phases={name: changes(before, one) for name, one in seen.items() if name != 'released'}, changes=changes(before, after), after_page=after.page, after_frame=after.frame)


def _meets(signature, seen):
    if 'page' in signature:
        return 'page' in seen and seen['page'][1] == signature['page']
    if 'left' in signature:
        return 'page' in seen
    if 'led' in signature:
        return bool(set(signature['led']) & set(seen.get('leds', {})))
    if 'audio' in signature:
        return bool(seen.get('audio_peak'))
    return False


def _without_noise(seen, noise):
    out = {k: v for k, v in seen.items() if k not in ('leds',) and not noise.get(k)}
    leds = {k: v for k, v in seen.get('leds', {}).items() if k not in noise.get('leds', {})}
    if leds:
        out['leds'] = leds
    return out


def classify(record, control, signature):
    """(verdict, reason). confirmed, reacted, no-reaction, contradicted or unobserved."""
    if record.get('state') != 'observed':
        return 'unobserved', record.get('error', 'not observed')
    if not control or control.get('state') != 'observed':
        return 'unobserved', 'no usable control for this screen and gesture'
    for observation in (record, control):
        if observation.get('arrived') != 'arrived' or observation.get('settled') is not True:
            return 'unobserved', 'the screen or its stable starting state was not confirmed'
    noise = {}
    for seen in [control.get('changes', {}), *control.get('phases', {}).values()]:
        for key, value in seen.items():
            noise[key] = {**noise.get(key, {}), **value} if isinstance(value, dict) else value
    if not noise.get('screen') and record.get('frame') != control.get('frame'):
        return 'unobserved', 'it started from a different picture than its control'
    final = _without_noise(record.get('changes', {}), noise)
    phases = {name: _without_noise(seen, noise) for name, seen in record.get('phases', {}).items()}
    modifiers = phases.pop('modifiers', {})
    moments = [final, *phases.values()]
    reacted = any(moments) or bool(modifiers)
    if not reacted:
        return 'no-reaction', 'nothing attributable was seen; the action may need a condition this run lacks'
    if signature is None:
        return 'reacted', 'something changed; no declared signature says what it means'
    if _meets(signature, modifiers):
        return 'reacted', 'the modifier alone already produced this'
    if any(_meets(signature, seen) for seen in moments):
        return 'confirmed', f'declared signature met: {signature}'
    if 'page' in signature and any('page' in seen for seen in moments):
        return 'contradicted', f'expected page {signature["page"]}, reached {[seen["page"][1] for seen in moments if "page" in seen]}'
    return 'reacted', f'something changed, but not the declared signature {signature}'


VERDICTS = ('confirmed', 'reacted', 'no-reaction', 'unobserved', 'contradicted')


def _signal_words(record):
    """Which kinds of signal changed, without their values: pictures and levels come from Roland's screens and the user's own project."""
    seen = {key for moment in [record.get('changes', {}), *record.get('phases', {}).values()] for key in moment}
    names = {'page': 'page', 'screen': 'picture', 'leds': 'lights', 'audio_peak': 'sound', 'parameter_writes': 'effect parameters'}
    return [names[key] for key in names if key in seen]


def summarise(runs, bindings, not_tried):
    """One record of what a sweep established, from one or more runs. A later run replaces an earlier result. Each job is judged by the control of its own run."""
    verdicts = {}
    by_id = {binding['id']: binding for binding in bindings}
    for run in runs:
        records = {record['id']: record for record in run if 'id' in record}
        for binding_id, record in records.items():
            if binding_id not in by_id:
                continue
            control = records.get(control_id(record.get('screen'), record.get('gesture')))
            verdict, reason = classify(record, control, signature_for(by_id[binding_id]))
            verdicts[binding_id] = dict(verdict=verdict, why=reason, signals=_signal_words(record))
    return dict(verdicts=verdicts, not_tried=dict(not_tried))


def evidence_for(binding_id, record):
    """The [EMULATOR] evidence this binding gets, or None. Silence and failed runs are no evidence either way."""
    entry = record['verdicts'].get(binding_id)
    if not entry or entry['verdict'] not in ('confirmed', 'reacted'):
        return None
    what = entry['why'] if entry['verdict'] == 'confirmed' else f'changed {", ".join(entry["signals"])}, meaning not proven'
    return dict(label='EMULATOR', source=f'lab404 sweep, knowledge/observations: {entry["verdict"]}: {what}')


def record_sweep(firmware, paths, root=None):
    """Write knowledge/observations/<firmware>.json and set the [EMULATOR] evidence of each binding to match it. Returns a one-line count."""
    root = Path(root) if root else Path(__file__).parents[1]/'knowledge'
    binding_path = root/'bindings'/f'{firmware}.json'
    data = json.loads(binding_path.read_text(encoding='utf-8'))
    runs = [[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()] for path in paths]
    from .identify import TABLE
    from .knowledge import firmware_id_of
    image_hashes = {e['sha256'] for e in TABLE if firmware_id_of(e) == firmware}
    legacy_digest = hashlib.sha256(binding_path.read_bytes()).hexdigest()
    definitions = _binding_digest(data)
    for run in runs:
        headers = [line['experiment'] for line in run if 'experiment' in line]
        if len(headers) != 1 or not isinstance(headers[0], dict) or headers[0].get('firmware') != firmware:
            raise ValueError('missing or mismatched experiment firmware')
        header = headers[0]
        if header.get('image_sha256') not in image_hashes:
            raise ValueError('experiment image hash does not match the firmware')
        if header.get('bindings_sha256') not in (definitions, legacy_digest):
            raise ValueError('experiment binding definitions differ from the current bindings')
    _, not_tried = jobs_for(data['bindings'])
    record = summarise(runs, data['bindings'], not_tried)
    record = dict(firmware=firmware, meaning='What the whole-firmware emulator showed. Never proof of behaviour on a unit. no-reaction and unobserved are no evidence either way: the action may need a condition these runs lacked.',
                  experiments=[{k: v for k, v in line['experiment'].items() if k != 'drive'} for run in runs for line in run if 'experiment' in line], **record)
    (root/'observations').mkdir(exist_ok=True)
    (root/'observations'/f'{firmware}.json').write_text(json.dumps(record, indent=0, ensure_ascii=False)+'\n', encoding='utf-8')
    for binding in data['bindings']:
        binding['evidence'] = [item for item in binding['evidence'] if item['label'] != 'EMULATOR']
        evidence = evidence_for(binding['id'], record)
        if evidence:
            binding['evidence'].append(evidence)
    binding_path.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False)+'\n', encoding='utf-8')
    counts = {name: sum(1 for entry in record['verdicts'].values() if entry['verdict'] == name) for name in VERDICTS}
    return f'{len(record["verdicts"])} observed, {len(record["not_tried"])} not tried: {counts}'


def _binding_digest(data):
    # Recording a run updates EMULATOR citations. Those are outputs of the experiment.
    bindings = [{**b, 'evidence': [e for e in b['evidence'] if e['label'] != 'EMULATOR']}
                for b in data['bindings']]
    content = json.dumps({**data, 'bindings': bindings}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def experiment_of(firmware, image, drive):
    """What a sweep's results depend on. The drive is too large to hash whole each time, so it is named by size, modified time and its first 16 MB."""
    source = Path(__file__).read_bytes()+Path(emulator_module.__file__).read_bytes()
    binding_path = Path(__file__).parents[1]/'knowledge/bindings'/f'{firmware}.json'
    bindings = _binding_digest(json.loads(binding_path.read_text(encoding='utf-8')))
    with open(drive, 'rb') as f:
        start = hashlib.sha256(f.read(16*1024*1024)).hexdigest()
    stat = os.stat(drive)
    return dict(firmware=firmware, image_sha256=hashlib.sha256(image).hexdigest(), drive=dict(size=stat.st_size, mtime=int(stat.st_mtime), start_sha256=start), bindings_sha256=bindings,
                tools_sha256=hashlib.sha256(source).hexdigest(), emulator_sha256=hashlib.sha256(Path(emulator_module.DEFAULT_QEMU).read_bytes()).hexdigest())


def sweep(jobs, runner, out, workers=4, experiment=None):
    """Run jobs, appending each result to the file as it finishes. Jobs already in the file are not run again, so an interrupted sweep continues.
    With `experiment`, a file from a different experiment is refused, so evidence from different setups never mixes."""
    done = set()
    if out.exists():
        lines = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines() if line.strip()]
        found = next((line['experiment'] for line in lines if 'experiment' in line), None)
        if experiment is not None and found != experiment:
            raise ValueError(f'{out} holds another experiment: {found}')
        done = {line['id'] for line in lines if 'id' in line}
    elif experiment is not None:
        out.write_text(json.dumps(dict(experiment=experiment))+'\n', encoding='utf-8')
    todo = [job for job in jobs if job['id'] not in done]
    lock = threading.Lock()

    def one(job):
        try:
            record = runner(job)
        except Exception as e:  # recorded, not retried: a failure stays a visible fact about this run
            record = dict(id=job['id'], state='failed', error=str(e), screen=job.get('screen'), keys=job.get('keys'), gesture=job.get('gesture'), control=job.get('control'))
        with lock, out.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record)+'\n')
        return record

    if workers == 1:
        for job in todo:
            one(job)
    else:
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(one, todo))
    return len(todo)
