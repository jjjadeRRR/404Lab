"""Check a built candidate against its base and sources. The report belongs to one exact file.

Results per check: pass, fail or unknown. `unknown` means something could not be established, for example a key on a screen the knowledge base
does not fully cover, or a mod with no compatibility scenarios. It is reported to the user and never counted as a pass.
A clean report still means "candidate": nothing here shows it works on a unit.
"""
import json
import runpy
from pathlib import Path

from .build import source_digest, source_revision
from .identify import TABLE
from .image import APP1_ROOM, DISABLEABLE, RETURN_ZERO, Image, ImageError, file_offset, protected, room, scatter, sha256
from .knowledge import Knowledge, firmware_id_of
from .stand import Boundary, Machine


def _result(name, state, detail=''):
    return dict(check=name, state=state, detail=detail)


def check_structure(base_raw, candidate_raw, manifest):
    """Only the table pointers, declared hook bytes and appended data may differ from the base."""
    out = []
    rows_base, rows_new = scatter(base_raw), scatter(candidate_raw)
    if rows_new[:len(rows_base)] != rows_base or len(rows_new) != len(rows_base)+1:
        out.append(_result('scatter', 'fail', 'existing rows changed, or more than one row added'))
    else:
        out.append(_result('scatter', 'pass'))
    overlap = next((row for row in rows_base for added in rows_new[len(rows_base):] if max(row[1], added[1]) < min(row[1]+row[2], added[1]+added[2])), None)
    out.append(_result('allocation', 'fail', f'the added block overwrites memory at 0x{overlap[1]:08X}') if overlap else _result('allocation', 'pass'))
    allowed = set(range(0x80, 0x88))
    bad_hook = None
    for hook in manifest['hooks']:
        address = int(hook['address'], 16)
        before, after = bytes.fromhex(hook['before']), bytes.fromhex(hook['after'])
        at = file_offset(base_raw, address, len(before))
        allowed |= set(range(at, at+len(before)))
        if base_raw[at:at+len(before)] != before or candidate_raw[at:at+len(after)] != after:
            bad_hook = hook['address']
    out.append(_result('hooks', 'fail', f'hook at {bad_hook} does not match the manifest') if bad_hook else _result('hooks', 'pass'))
    # Checked again here, not only trusted from the build: a candidate can come from elsewhere, or from a build tool with a hole.
    image = Image(base_raw)
    # The one change allowed inside that code: a guarded service routine made to return at once (hooks.check_disable_hook).
    def switched_off(hook):
        address = int(hook['address'], 16)
        return (address in DISABLEABLE and bytes.fromhex(hook['after']) == RETURN_ZERO and len(bytes.fromhex(hook['before'])) == len(RETURN_ZERO)
                and (protected(image, address) or '').startswith(f'0x{address:08X}'))
    off = [hook['address'] for hook in manifest['hooks'] if switched_off(hook)]
    guarded = next((f'{hook["address"]} touches {zone}' for hook in manifest['hooks'] if not switched_off(hook)
                    for at in range(int(hook['address'], 16), int(hook['address'], 16)+len(bytes.fromhex(hook['before'])))
                    for zone in [protected(image, at)] if zone), None)
    out.append(_result('loader-code', 'fail', f'{guarded}: this code can erase the loader') if guarded else
               _result('loader-code', 'pass', f'switched off (return 0 at entry): {", ".join(off)}' if off else ''))
    out.append(_result('flash-room', 'fail', f'{len(candidate_raw)} bytes, but the loader erases only {APP1_ROOM} for APP1 (hw.update.app1-range)')
               if room(candidate_raw) < 0 else _result('flash-room', 'pass', f'{room(candidate_raw)} bytes left'))
    if 'flash' in manifest:  # a block kept in flash after the image: its bytes must be the ones the build made
        at = int(manifest['flash']['address'], 16)-0x60080000
        block = candidate_raw[at:at+manifest['flash']['bytes']]
        same = len(block) == manifest['flash']['bytes'] and sha256(block) == manifest['flash']['sha256']
        out.append(_result('flash-block', 'pass' if same else 'fail', '' if same else f'the block at {manifest["flash"]["address"]} differs from the manifest'))
    changed = [i for i, (a, b) in enumerate(zip(base_raw, candidate_raw)) if a != b and i not in allowed]
    if len(candidate_raw) < len(base_raw) or changed:
        where = f'first at file offset 0x{changed[0]:X}' if changed else 'candidate is shorter than its base'
        out.append(_result('undeclared-changes', 'fail', where))
    else:
        out.append(_result('undeclared-changes', 'pass'))
    return out


def check_keys(mod, firmware, knowledge):
    """Every input the mod claims must be free on that firmware."""
    adds = mod.get('adds', {}).get('bindings', [])
    if not adds:
        return [_result('keys', 'pass', 'the mod declares no key bindings')]
    out = []
    for item in adds:
        label = f'{"+".join(item["keys"])} {item.get("gesture", "press")} on {item["screen"]}'
        state, detail = knowledge.check_keys(firmware, item['screen'], item['keys'], item.get('gesture', 'press'))
        if state == 'occupied':
            out.append(_result(f'keys: {label}', 'fail', f'already used: {detail["action"]} ({detail["id"]})'))
        elif state == 'unknown':
            out.append(_result(f'keys: {label}', 'unknown', detail))
        else:
            out.append(_result(f'keys: {label}', 'pass'))
    return out


def check_scenarios(mod_dir, mod, base_raw, candidate_raw):
    """Run the mod's compatibility scenarios on base and candidate. Each scenario raises when they differ."""
    names = mod.get('scenarios', [])
    if not names:
        return [_result('compatibility', 'unknown', 'the mod declares no compatibility scenarios')]
    out = []
    module = runpy.run_path(str(Path(mod_dir)/'scenarios.py'))
    for name in names:
        try:
            compared = module[name](Machine(base_raw), Machine(candidate_raw))
            # A scenario says how many comparisons it made, so one that compares nothing cannot pass.
            out.append(_result(f'compatibility: {name}', 'pass', f'{compared} comparisons') if compared else _result(f'compatibility: {name}', 'unknown', 'the scenario reports no comparisons'))
        except Boundary as e:
            out.append(_result(f'compatibility: {name}', 'unknown', f'stopped at a stand boundary: {e}'))
        except AssertionError as e:
            out.append(_result(f'compatibility: {name}', 'fail', str(e)[:300]))
    return out


def check_candidate(package_dir, mod_dir, base_path, knowledge=None):
    package_dir, mod_dir = Path(package_dir), Path(mod_dir)
    candidate_raw = (package_dir/'SP404MKII_APP1.bin').read_bytes()
    base_raw = Path(base_path).read_bytes()
    manifest = json.loads((package_dir/'manifest.json').read_text(encoding='utf-8'))
    mod = json.loads((mod_dir/'mod.json').read_text(encoding='utf-8'))
    results = []
    actual = sha256(candidate_raw)
    results.append(_result('candidate-file', 'pass' if actual == manifest['candidate_sha256'] else 'fail',
                           '' if actual == manifest['candidate_sha256'] else 'this file is not the one that was built'))
    parent = sha256(base_raw)
    results.append(_result('parent', 'pass' if parent == manifest['parent_sha256'] else 'fail',
                           '' if parent == manifest['parent_sha256'] else 'this is not the base it was built on'))
    digest = source_digest(mod_dir, mod)
    results.append(_result('sources', 'pass' if digest == manifest['source_sha256'] else 'fail',
                           '' if digest == manifest['source_sha256'] else 'the mod sources changed after this build'))
    entry = next((e for e in TABLE if e['sha256'] == parent), None)
    if results[1]['state'] == 'fail' or entry is None:
        results.append(_result('structure', 'unknown', 'not checked: wrong or unidentified base'))
    else:
        try:
            Image(candidate_raw)
            results += check_structure(base_raw, candidate_raw, manifest)
        except ImageError as e:
            results.append(_result('structure', 'fail', str(e)))
        results += check_keys(mod, firmware_id_of(entry), knowledge or Knowledge())
        if not any(r['state'] == 'fail' for r in results):
            results += check_scenarios(mod_dir, mod, base_raw, candidate_raw)
    states = {r['state'] for r in results}
    overall = 'fail' if 'fail' in states else 'unknown' if 'unknown' in states else 'pass'
    return dict(candidate_sha256=actual, parent_sha256=parent, source_sha256=digest, source_revision=source_revision(), profile=dict(firmware=firmware_id_of(entry) if entry else None), overall=overall, results=results,
                meaning='A pass means these checks passed for this exact file. It does not show the mod works on a unit.')
