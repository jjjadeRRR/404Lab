"""From a mod folder to a package a musician can try. Everything a task needs lives in mod.json, so there is one description, not several to keep in step.

The order is: preview, approval by the user, then package. A package exists only if nothing failed and every unknown was accepted by name, in the user's words. Failures cannot be accepted.
The result is always a candidate. Nothing here shows that it works on a unit.
"""
import hashlib
import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .build import build, source_digest, source_revision
from .check import check_candidate
from .emulator import BLANK_DRIVE, Emulator, MAIN_PAGE_WORD, available
from .identify import TABLE
from .image import sha256
from .knowledge import Knowledge, firmware_id_of
from .observe import ROUTE_PAGE, ROUTES, Watcher, _join_filter_drive, changes, do_step, experiment_of, perform

SCREEN_COLUMNS, SCREEN_ROWS = 21, 8  # characters of the small font that fit on the unit's 128x64 screen [HYPOTHESIS: 6 by 8 pixels]
ROOT = Path(__file__).resolve().parents[1]
# Inputs pressed on base and candidate alike, from the main screen. Short enough to finish before the screen saver starts.
WALK = ('MFX', 'EXIT', 'PITCH/SPEED', 'EXIT', 'START/END', 'EXIT', 'LOOP', 'LOOP', 'GATE', 'GATE', 'ROLL', 'REVERSE', 'REVERSE', 'PATTERN SELECT', 'PATTERN SELECT',
        'SHIFT+PAD13', 'EXIT', 'COPY', 'EXIT', 'DEL', 'EXIT', 'PAD1', 'PAD2', 'HOLD', 'HOLD', 'SHIFT+SUB PAD', 'EXIT')
# Steps whose picture differs between boots of one firmware, so it says nothing about a candidate. Their page and lights are still compared.
# START/END: a few pixels of the waveform differ, in about 1 boot in 3 [EMULATOR: 16 of 29 walks differed from the first, with a project on the drive].
PICTURE_VARIES = ('START/END',)
# Other screens a new input is pressed on, to see that it stays where it was declared.
ELSEWHERE = (('sample', []), ('pitch-speed', ['PITCH/SPEED']), ('pattern-select', ['PATTERN SELECT']), ('sampling', ['REC']), ('utility-menu', ['SHIFT+PAD13']))
# Promises of docs/PLAN.md that no tool can establish yet. Each stays visible and must be accepted by name until one can.
CONTRACT = (('contract: audio bit for bit', 'Only pad peaks can be compared on the emulator, and effects run on a stand-in for the second processor. '
             'Changes to the sound may go unnoticed. Listen to the same backed-up project on the base and the candidate with the new feature unused, including effects. Listening does not prove bit-for-bit equality.'),
            ('contract: project save, load and transfer', 'Not exercised by any tool yet. A project could save or reload differently. '
             'Keep the original backup untouched; save, reload and transfer a disposable copy, and check that the base firmware can still read it.'),
            ('contract: same handler calls and state', 'Only screens, pages and lights are compared, not hidden state. '
             'A change may appear only later. Try your normal playing sequence with the new feature unused, then used and exited. Report delayed changes; a short session cannot rule them all out.'))
BEFORE_UNIT_CHECKS = ('Before flashing, back up your projects to a computer.',
                      'To install, copy SP404MKII_APP1.bin from this folder to the root of a FAT32 SD card. Hold SHIFT while powering on, and confirm with VALUE when the update screen appears.',
                      'Use an SD card you trust. One owner\'s updates stalled about five times on a faulty card in one evening, and went through on the first attempt with a normal one. The unit still started its loader and was not bricked, but that is one person\'s experience and no promise.',
                      'If the update stalls, stop and tell your agent what the screen shows before you try again.')
AFTER_UNIT_CHECKS = ('Listen: with the new function unused, your project should sound as it did on the base firmware.',
                     'Save a project, turn the unit off and on, and load it again.',
                     'To go back, install your base firmware file the same way.')


def _describe_results(results):
    """Keep each check's reason beside its name in refusals and the unit checklist."""
    return ''.join(f'- {r["check"]}: {r["detail"]}\n' for r in results)


class PackageRefused(ValueError):
    def __init__(self, message, failed=(), unknown=(), results=()):
        details = _describe_results(results)
        super().__init__(message+('\n'+details.rstrip() if details else ''))
        self.failed, self.unknown = list(failed), list(unknown)


def _load(mod_dir):
    return json.loads((Path(mod_dir)/'mod.json').read_text(encoding='utf-8'))


def interface_digest(mod):
    """What the user was shown and agreed to. A change to any of this needs a new approval."""
    shown = dict(about=mod.get('about'), asked=mod.get('task', {}).get('asked'), adds=mod.get('adds', {}))
    return hashlib.sha256(json.dumps(shown, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _firmware_of(base_raw):
    entry = next((e for e in TABLE if e['sha256'] == sha256(base_raw)), None)
    return firmware_id_of(entry) if entry else None


def preview(mod_dir, base_path, knowledge=None):
    """The interface in plain text, for showing to the user before anything is built."""
    mod = _load(mod_dir)
    firmware = _firmware_of(Path(base_path).read_bytes())
    knowledge = knowledge or Knowledge()
    task = mod.get('task', {})
    lines = [f'# Preview: {mod["name"]}', '', mod.get('about', ''), '', f'Asked: {task.get("asked", "not recorded")}', f'Can it be done: {task.get("feasible", "not recorded")}', '',
             f'## New keys on {firmware or "an unidentified image"}', '', '| Keys | How | Where | Does | Is it free? |', '|---|---|---|---|---|']
    for item in mod.get('adds', {}).get('bindings', []):
        gesture = item.get('gesture', 'press')
        state, detail = knowledge.check_keys(firmware, item['screen'], item['keys'], gesture)
        said = f'occupied: {detail["action"]}' if state == 'occupied' else 'unknown: not proven free, treat as taken until checked' if state == 'unknown' else 'free'
        lines.append(f'| {"+".join(item["keys"])} | {gesture} | {item["screen"]} | {item.get("action", "")} | {said} |')
    for screen in mod.get('adds', {}).get('screens', []):
        rows = screen['lines']
        too_wide = [row for row in rows if len(row) > SCREEN_COLUMNS]
        if too_wide or len(rows) > SCREEN_ROWS:
            raise PackageRefused(f'screen {screen["name"]} does not fit: at most {SCREEN_ROWS} lines of {SCREEN_COLUMNS} characters')
        border = '+'+'-'*(SCREEN_COLUMNS+2)+'+'
        lines += ['', f'## New screen: {screen["name"]}', '', '```', border, *[f'| {row:<{SCREEN_COLUMNS}} |' for row in [*rows, *['']*(SCREEN_ROWS-len(rows))]], border, '```']
    lines += ['', f'Interface digest: {interface_digest(mod)}']
    return '\n'.join(lines)+'\n'


def approve(mod_dir, said):
    """Record the user's agreement to the interface as it stands now, in their words."""
    if not said.strip():
        raise PackageRefused('an approval needs what the user said')
    path = Path(mod_dir)/'approval.json'
    path.write_text(json.dumps(dict(interface_sha256=interface_digest(_load(mod_dir)), said=said), indent=1, ensure_ascii=False)+'\n', encoding='utf-8')


def replay_verdicts(base, again, candidate):
    """Compare one walk of the base, a second walk of the base, and a walk of the candidate, signal by signal. A difference on a signal the base holds steady always fails.
    Where the base disagrees with itself, that signal says nothing about the candidate, so the result is unknown and someone has to accept it."""
    if len(candidate) != len(base) or len(again) != len(base):
        return dict(state='fail', detail=f'walks have different lengths: {len(base)}, {len(again)}, {len(candidate)}')
    differ, noisy, unsettled = [], [], []
    for one, two, new in zip(base, again, candidate):
        if one['step'] != two['step'] or one['step'] != new['step']:
            return dict(state='fail', detail=f'walks have different steps: {one["step"]}, {two["step"]}, {new["step"]}')
        steady = [signal for signal in ('frame', 'page', 'lights') if one[signal] == two[signal] and one[signal] is not None and one.get('settled', True) and two.get('settled', True)]
        if any(one[signal] != new[signal] for signal in steady):
            differ.append(f'{one["step"]} ({", ".join(signal for signal in steady if one[signal] != new[signal])})')
        if len(steady) < 3:
            noisy.append(one['step'])
        if not new.get('settled', True):
            unsettled.append(one['step'])
    if differ:
        return dict(state='fail', detail=f'differs from the base after: {", ".join(differ)}')
    if noisy or unsettled:
        reasons = []
        if noisy:
            reasons.append(f'the base was unstable, unreadable or disagreed with itself after: {", ".join(noisy)}')
        if unsettled:
            reasons.append(f'the candidate did not settle after: {", ".join(unsettled)}')
        return dict(state='unknown', detail='comparison incomplete: '+'; '.join(reasons))
    if len({state['frame'] for state in base}) < 2:
        return dict(state='unknown', detail='the screen never changed during the walk, so this comparison would be empty')
    return dict(state='pass', detail=f'{len(base)} steps match, on screens, pages and lights, each after it settled. Not compared: what happens between steps, and the picture after {", ".join(PICTURE_VARIES)}, which varies between boots of the base')


def _walk(unit, firmware):
    if not unit.wait_for_main(45, 3):
        raise RuntimeError('no main screen')
    watcher = Watcher(unit, firmware)
    states = []
    for step in WALK:
        do_step(unit, step)
        settled = watcher.settle()
        seen = watcher.look()
        states.append(dict(step=step, frame='varies' if step in PICTURE_VARIES else seen.frame, page=seen.page, lights=seen.leds, settled=settled))
    return states


def _at_binding_screen(unit, firmware, screen):
    if screen not in ROUTES:
        return None
    for step in ROUTES[screen]:
        do_step(unit, step)
    watcher = Watcher(unit, firmware)
    if watcher.settle() and watcher.look().page == ROUTE_PAGE[screen]:
        return watcher
    return None


def _demonstrate(item, base_raw, candidate_raw, drive, firmware):
    """The added function really appears on the candidate, not on the base, and EXIT leaves both on the same screen."""
    def run(image):
        with Emulator(image, drive=drive) as unit:
            if not unit.wait_for_main(45, 3):
                raise RuntimeError('no main screen')
            screen = item.get('screen', 'sample')
            watcher = _at_binding_screen(unit, firmware, screen)
            if watcher is None:
                raise RuntimeError(f'could not confirm screen {screen}')
            perform(unit, _join_filter_drive(item['keys']), item.get('gesture', 'press'), lambda: None)
            watcher.settle()
            page = unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF
            do_step(unit, 'EXIT')
            watcher.settle()
            return page, unit.read_u32(MAIN_PAGE_WORD) & 0xFFFF, bytes(unit.frame)
    with ThreadPoolExecutor(2) as pool:
        (base_page, base_after, base_frame), (page, after, frame) = pool.map(run, (base_raw, candidate_raw))
    name = f'demonstrate: {"+".join(item["keys"])}'
    if page != item['page']:
        return dict(check=name, state='fail', detail=f'expected page {item["page"]} on the candidate, reached {page}')
    if base_page == item['page']:
        return dict(check=name, state='fail', detail='the base does the same, so this shows nothing added')
    if (after, frame) != (base_after, base_frame):
        return dict(check=name, state='fail', detail='after EXIT the candidate is not where the base is')
    return dict(check=name, state='pass', detail=f'reached page {page}; EXIT returned to the same screen as the base')


def _contained(item, base_raw, candidate_raw, drive, firmware):
    """A new input must do nothing new on screens it was not declared for: there, its keys are the firmware's."""
    def run(job):
        image, screen, route = job
        with Emulator(image, drive=drive) as unit:
            if not unit.wait_for_main(45, 3):
                raise RuntimeError('no main screen')
            for step in route:
                do_step(unit, step)
            watcher = Watcher(unit, firmware)
            watcher.settle()
            arrived = watcher.look().page == ROUTE_PAGE[screen]
            pages = perform(unit, _join_filter_drive(item['keys']), item.get('gesture', 'press'), lambda: watcher.look().page)
            watcher.settle()
            seen = watcher.look()
            return arrived, list(pages.values()), seen.page, seen.frame, seen.leds
    routes = [(screen, route) for screen, route in ELSEWHERE if screen != item['screen']]
    with ThreadPoolExecutor(4) as pool:
        base = list(pool.map(run, [(base_raw, *r) for r in routes]))
        candidate = list(pool.map(run, [(candidate_raw, *r) for r in routes]))
    name = f'contained: {"+".join(item["keys"])}'
    differ = [routes[i][0] for i in range(len(routes)) if base[i][1:] != candidate[i][1:]]
    if differ:
        return dict(check=name, state='fail', detail=f'on screens it was not declared for, it differs from the base on: {", ".join(differ)}')
    missed = [routes[i][0] for i in range(len(routes)) if not (base[i][0] and candidate[i][0])]
    if missed:
        return dict(check=name, state='unknown', detail=f'did not reach: {", ".join(missed)}')
    return dict(check=name, state='pass', detail=f'same as the base on {len(routes)} other screens: {", ".join(r[0] for r in routes)}. Other screens were not tried')


def _unused_on_base(item, base_raw, drive, firmware):
    """The new input does nothing on the base where it is declared. The key records cannot show this: HOLD + LOOP has no record, yet LOOP still toggles."""
    name = f'unused on the base: {"+".join(item["keys"])}'
    if item['screen'] not in ROUTES:
        return dict(check=name, state='unknown', detail=f'no known way to reach screen {item["screen"]}')
    with Emulator(base_raw, drive=drive) as unit:
        if not unit.wait_for_main(45, 3):
            raise RuntimeError('no main screen')
        watcher = _at_binding_screen(unit, firmware, item['screen'])
        if watcher is None:
            return dict(check=name, state='unknown', detail=f'could not confirm screen {item["screen"]}')
        before = watcher.look()
        watcher.reset_counts()
        seen = perform(unit, _join_filter_drive(item['keys']), item.get('gesture', 'press'), watcher.look)
        moved = sorted({key for moment in seen.values() for key in changes(before, moment)})
        loaded = False
        if not moved:  # silence means something only if the drive really holds samples for keys to act on
            for pad in ('PAD1', 'PAD2', 'PAD3', 'PAD4'):
                unit.press(pad, hold=0.3, settle=0.7)
                if unit.audio_peak:
                    loaded = True
                    break
    if moved:
        return dict(check=name, state='fail', detail=f'on the base these keys already change: {", ".join(moved)}')
    if not loaded:
        return dict(check=name, state='unknown', detail='nothing seen, but no pad made a sound, so there may be no samples for these keys to act on. Use --drive with a project')
    return dict(check=name, state='pass', detail='nothing seen on the base in this one run, with samples loaded. That does not prove it is free')


def replay(base_raw, candidate_raw, mod, drive, firmware):
    """The same inputs on base and candidate on the whole-firmware emulator. Screens, pages and lights outside what the mod declares must match."""
    name = 'replay: screens, pages and lights'
    if not available():
        return [dict(check=name, state='unknown', detail='the emulator is not installed: tools/setup_dm404.sh')]
    def one(image):
        with Emulator(image, drive=drive) as unit:
            return _walk(unit, firmware)
    try:
        with ThreadPoolExecutor(3) as pool:
            base, again, candidate = pool.map(one, (base_raw, base_raw, candidate_raw))
        results = [dict(check=name, **replay_verdicts(base, again, candidate))]
    except RuntimeError as e:
        results = [dict(check=name, state='unknown', detail=f'the walk did not finish: {e}')]
    shows = mod.get('adds', {}).get('demonstrate', [])
    if not shows:
        results.append(dict(check='demonstrate', state='unknown', detail='the mod does not say how to show what it adds'))
    for item in shows:
        try:
            results.append(_demonstrate(item, base_raw, candidate_raw, drive, firmware))
        except RuntimeError as e:
            results.append(dict(check=f'demonstrate: {"+".join(item["keys"])}', state='unknown', detail=f'did not finish: {e}'))
    for item in mod.get('adds', {}).get('bindings', []):
        try:
            results.append(_contained(item, base_raw, candidate_raw, drive, firmware))
        except RuntimeError as e:
            results.append(dict(check=f'contained: {"+".join(item["keys"])}', state='unknown', detail=f'did not finish: {e}'))
        try:
            results.append(_unused_on_base(item, base_raw, drive, firmware))
        except RuntimeError as e:
            results.append(dict(check=f'unused on the base: {"+".join(item["keys"])}', state='unknown', detail=f'did not finish: {e}'))
    return results


def _test_inputs(firmware, base_raw, drive):
    try:
        return experiment_of(firmware, base_raw, drive)
    except OSError as e:
        return dict(firmware=firmware, image_sha256=sha256(base_raw), note=f'emulator inputs not available: {e}')


DANGEROUS_FILES = ('sp404mkii_app1w.bin', 'sp404mkii_app0w.bin', 'sp404mkii_app1u.bin', 'mirxrt1060-evk.bin', 'td003_rom.bin', 'sp404mkii_app0.bin')


def refuse_dangerous_files(folder):
    """Refuse a folder holding a file the loader or the factory service code would act on (hw.update.whole-files). A user copies a package to a card."""
    found = sorted(str(p.relative_to(folder)) for p in Path(folder).rglob('*') if p.name.lower() in DANGEROUS_FILES)
    if found:
        raise PackageRefused(f'{", ".join(found)}: a file by this name on the SD card can make the unit rewrite its loader or its second processor and brick it. Remove it')


def package(mod_dir, base_path, out_dir, accepted=None, drive=None, replay=replay, knowledge=None):
    """Write a new package folder, or raise PackageRefused and leave nothing behind. accepted maps each unknown check's name to what the user said about it."""
    mod_dir, out_dir, accepted = Path(mod_dir), Path(out_dir), dict(accepted or {})
    if out_dir.exists():
        raise PackageRefused(f'{out_dir} exists: every package gets a new folder')
    mod = _load(mod_dir)
    approval_path = mod_dir/'approval.json'
    if not approval_path.exists():
        raise PackageRefused('the interface has not been approved by the user: run preview, show it, then approve')
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    digest = interface_digest(mod)
    if approval['interface_sha256'] != digest:
        raise PackageRefused('the interface changed since the user approved it: show it again')
    if not mod.get('task', {}).get('unit_checks'):
        raise PackageRefused('the task does not say what to check on the unit')
    def binding_id(item):
        return (item.get('screen', 'sample'), tuple(item['keys']), item.get('gesture', 'press'))

    declared = {binding_id(item) for item in mod.get('adds', {}).get('bindings', [])}
    shown = {binding_id(item) for item in mod.get('adds', {}).get('demonstrate', [])}
    if shown and shown != declared:
        raise PackageRefused(f'screen, keys and gesture to demonstrate must match the declaration: {sorted(shown)} against {sorted(declared)}')
    drive = drive or BLANK_DRIVE
    building = out_dir.with_name(f'{out_dir.name}.building-{uuid.uuid4().hex}')
    refuse_dangerous_files(mod_dir)
    try:
        manifest = build(mod_dir, base_path, building)
        report = check_candidate(building, mod_dir, base_path, knowledge)
        base_raw = Path(base_path).read_bytes()
        candidate_raw = (building/'SP404MKII_APP1.bin').read_bytes()
        firmware = _firmware_of(base_raw)
        results = list(report['results'])
        if not any(r['state'] == 'fail' for r in results):
            results += replay(base_raw, candidate_raw, mod, drive, firmware)
        results += [dict(check=name, state='unknown', detail=detail) for name, detail in CONTRACT]
        failed = [r['check'] for r in results if r['state'] == 'fail']
        unknown = [r['check'] for r in results if r['state'] == 'unknown']
        stray = [name for name in accepted if name not in unknown and name not in failed]
        if stray:
            raise PackageRefused(f'accepted, but there is nothing by that name: {", ".join(stray)}')
        if failed:
            raise PackageRefused(f'failed, and a failure cannot be accepted: {", ".join(failed)}', failed, unknown,
                                 [r for r in results if r['state'] in ('fail', 'unknown')])
        open_items = [name for name in unknown if not accepted.get(name, '').strip()]
        if open_items:
            raise PackageRefused(f'the user has not accepted: {", ".join(open_items)}', [], open_items,
                                 [r for r in results if r['check'] in open_items])
        final = dict(status='candidate: not proven on a unit', mod=mod['name'], mod_version=mod.get('version'), candidate_sha256=report['candidate_sha256'], parent_sha256=report['parent_sha256'],
                     source_sha256=report['source_sha256'], source_revision=source_revision(), profile=dict(firmware=firmware), test_inputs=_test_inputs(firmware, base_raw, drive),
                     interface_sha256=digest, approval=approval, accepted_unknowns={name: accepted[name] for name in unknown}, results=results,
                     meaning=report['meaning'])
        (building/'report.json').write_text(json.dumps(final, indent=1, ensure_ascii=False)+'\n', encoding='utf-8')
        checks = [*BEFORE_UNIT_CHECKS, *mod['task']['unit_checks'], *AFTER_UNIT_CHECKS]
        open_list = _describe_results(r for r in results if r['state'] == 'unknown')
        (building/'UNIT_CHECKS.md').write_text(f'# {mod["name"]} {mod.get("version", "")}: what to check on your unit\n\nThis is a candidate. Tests on an emulator do not show it works on a real unit. Install at your own risk.\n\nBuilt on {firmware}. Candidate SHA-256: {report["candidate_sha256"]}\n\n'
                                               +''.join(f'{i}. {text}\n' for i, text in enumerate(checks, 1))+f'\n## Not established by any test\n\n{open_list}', encoding='utf-8')
        if sha256((building/'SP404MKII_APP1.bin').read_bytes()) != report['candidate_sha256']:
            raise PackageRefused('the candidate changed after it was checked')
        if source_digest(mod_dir, mod, manifest['external_source_inputs']) != report['source_sha256']:
            raise PackageRefused('the mod sources changed after they were checked: build and check them again')
        refuse_dangerous_files(building)
        building.rename(out_dir)
        return final
    finally:
        if building.exists():
            shutil.rmtree(building)
