"""Command line: python -m lab404 identify|map|read|dis|check-hook|build ..."""
import argparse
import hashlib
import json
import sys

from .image import HANDLER_NAMES, Image, ImageError


def _addr(text):
    return int(text, 0)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='lab404')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('identify', help='say what an APP1 is, or that it is unknown')
    p.add_argument('file')
    p.add_argument('--json', action='store_true')
    sub.add_parser('map', help='scatter table: what startup puts where').add_argument('file')
    p = sub.add_parser('read', help='hex bytes at a runtime address')
    p.add_argument('file')
    p.add_argument('address', type=_addr)
    p.add_argument('size', type=_addr)
    p.add_argument('--sha256', action='store_true', help='print size and SHA-256 instead of the bytes, for a check that carries no firmware')
    p = sub.add_parser('dis', help='disassemble Thumb code at a runtime address')
    p.add_argument('file')
    p.add_argument('address', type=_addr)
    p.add_argument('count', type=int, nargs='?', default=12)
    p = sub.add_parser('check-hook', help='can this function entry take a hook?')
    p.add_argument('file')
    p.add_argument('address', type=_addr)
    p.add_argument('--not-pointer', type=_addr, action='append', default=[], help='a word checked by hand and found to be data')
    p = sub.add_parser('xrefs', help='who calls, branches to or points at this address, as far as bytes show')
    p.add_argument('file')
    p.add_argument('address', type=_addr)
    p = sub.add_parser('find', help='where a text or hex string is, by runtime address')
    p.add_argument('file')
    p.add_argument('what')
    p.add_argument('--hex', action='store_true', help='what is hex bytes, not text')
    p = sub.add_parser('ask', help='search the knowledge base')
    p.add_argument('term', nargs='?', default='', help='words in any order; an exact phrase is listed first')
    p.add_argument('--firmware')
    p.add_argument('--topic', help='only facts of this topic; with no term, all of them')
    sub.add_parser('doctor', help='what this computer still needs before the tools work, and how to get it')
    sub.add_parser('gaps', help='what a mod author needs to know that is not established yet, and how to find it out')
    sub.add_parser('topics', help='what the knowledge base holds: topics and how many facts each has')
    p = sub.add_parser('check-keys', help='is this input free on this screen? occupied, free or unknown')
    p.add_argument('firmware')
    p.add_argument('screen')
    p.add_argument('keys', nargs='+')
    p.add_argument('--gesture', default='press')
    sub.add_parser('verify-knowledge', help="run the knowledge base's byte checks on an image").add_argument('file')
    p = sub.add_parser('sweep', help='press every recorded key binding of a firmware on the emulator and write down what is seen')
    p.add_argument('firmware')
    p.add_argument('file')
    p.add_argument('out', help='results file, one record per line; an existing file is continued, not overwritten')
    p.add_argument('--drive', default=None, help='internal drive image holding a project; used through a temporary overlay')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--only', default=None, help='only these screens, comma separated')
    p.add_argument('--failed-in', default=None, help='only the jobs that failed in this earlier results file, once the cause is fixed. Never to retry an unexplained failure')
    p.add_argument('--shots', default=None, help='folder for screen pictures. Never inside the repository tree that is committed')
    p = sub.add_parser('record-sweep', help='write what sweep results establish into the knowledge base, in order, later runs replacing earlier')
    p.add_argument('firmware')
    p.add_argument('runs', nargs='+')
    p = sub.add_parser('preview', help='the interface of a mod in plain text, to show the user before building')
    p.add_argument('mod')
    p.add_argument('base')
    p = sub.add_parser('approve', help="record the user's agreement to the interface as it stands now")
    p.add_argument('mod')
    p.add_argument('--said', required=True, help='what the user said')
    p = sub.add_parser('package', help='build, check and compare on the emulator, then write a new package folder, or refuse')
    p.add_argument('mod')
    p.add_argument('base')
    p.add_argument('out')
    p.add_argument('--drive', default=None, help='internal drive image holding a project; used through a temporary overlay')
    p.add_argument('--accept', action='append', default=[], metavar='CHECK', help='an unknown result the user accepted, by its name. Repeat for each')
    p.add_argument('--said', default='', help='what the user said when accepting')
    p = sub.add_parser('build', help='build a mod on an identified APP1')
    p.add_argument('mod')
    p.add_argument('base')
    p.add_argument('out')
    p = sub.add_parser('check', help='check a built candidate against its base and sources')
    p.add_argument('package')
    p.add_argument('mod')
    p.add_argument('base')
    a = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        # Windows consoles and pipes default to a local code page; facts and notes hold UTF-8 text (dashes, Russian).
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    if a.command in ('preview', 'approve', 'package'):
        from .build import BuildError
        from .pipeline import PackageRefused, approve, package, preview
        try:
            if a.command == 'preview':
                print(preview(a.mod, a.base), end='')
            elif a.command == 'approve':
                approve(a.mod, a.said)
                print('recorded')
            else:
                report = package(a.mod, a.base, a.out, {name: a.said for name in a.accept}, a.drive)
                print(f'{report["status"]}\n{a.out}\nSHA-256 {report["candidate_sha256"]}')
        except PackageRefused as e:
            print(f'refused: {e}', file=sys.stderr)
            return 2
        except (BuildError, ImageError) as e:
            print(f'refused: {e}', file=sys.stderr)
            return 2
        return 0
    if a.command == 'record-sweep':
        from .observe import record_sweep
        print(record_sweep(a.firmware, a.runs))
        return 0
    try:
        if a.command == 'identify':
            from .identify import explain, identify
            with open(a.file, 'rb') as f:
                result = identify(f.read())
            print(json.dumps(result, indent=1) if a.json else explain(result))
            return 0 if result['status'] == 'known' else 3
        if a.command == 'build':
            from .build import BuildError, build
            try:
                print(json.dumps(build(a.mod, a.base, a.out), indent=1))
            except BuildError as e:
                print(f'refused: {e}', file=sys.stderr)
                return 2
            return 0
        if a.command == 'ask':
            from .knowledge import Knowledge
            found = [f for f in Knowledge().query(a.term, a.firmware) if not a.topic or f['topic'] == a.topic]
            if not found:
                print('nothing found. That is not proof it is unknown: try other words, or `topics` to see what there is')
            for fact in found:
                labels = ','.join(sorted({e['label'] for e in fact['evidence']}))
                print(f'{fact["id"]} [{fact["status"]}, {labels}, {fact["firmware"]}]: {fact["claim"]}')
            return 0
        if a.command == 'doctor':
            from .doctor import report
            rows = report()
            for name, state, hint in rows:
                print(f'{state:20} {name}'+(f'\n{"":20} {hint}' if hint else ''))
            return 1 if any(state == 'missing' for _, state, _ in rows) else 0
        if a.command == 'gaps':
            from .knowledge import gaps
            for q in gaps():
                print(f'{q["state"]:6} {q["id"]}: {q["ask"]}\n       why it matters: {q["why"]}\n       find out: {q["find_out"]}\n       facts: {", ".join(q["facts"]) or "none yet"}')
            return 0
        if a.command == 'topics':
            from .knowledge import Knowledge
            print(', '.join(f'{topic} ({count})' for topic, count in Knowledge().topics().items()))
            print('List one with: python -m lab404 ask --topic TOPIC')
            return 0
        if a.command == 'check-keys':
            from .knowledge import Knowledge
            state, detail = Knowledge().check_keys(a.firmware, a.screen, a.keys, a.gesture)
            print(state, json.dumps(detail, ensure_ascii=False) if isinstance(detail, dict) else detail or '')
            return 0
        if a.command == 'check':
            from .check import check_candidate
            report = check_candidate(a.package, a.mod, a.base)
            print(json.dumps(report, indent=1, ensure_ascii=False))
            return {'pass': 0, 'unknown': 3}.get(report['overall'], 1)
        image = Image.load(a.file)
        if a.command == 'verify-knowledge':
            from .identify import TABLE, identify
            from .knowledge import Knowledge, firmware_id_of
            entry = next((e for e in TABLE if e['sha256'] == image.sha256), None)
            if entry is None:
                print('unknown image: byte facts cannot be assumed to apply. '+identify(image.raw)['sha256'])
                return 3
            results = Knowledge().verify(image, firmware_id_of(entry))
            failed = [r for r in results if r[1] != 'pass']
            print(f'{len(results)-len(failed)} of {len(results)} byte checks pass on {firmware_id_of(entry)}')
            for fact_id, _, detail in failed:
                print(f'FAIL {fact_id}: {detail}')
            return 1 if failed else 0
        if a.command == 'sweep':
            from pathlib import Path
            from .emulator import BLANK_DRIVE
            from .knowledge import Knowledge
            from .observe import experiment_of, failed_ids, jobs_for, run_job, select, sweep
            jobs, skipped = jobs_for(Knowledge().bindings[a.firmware]['bindings'])
            if a.only:
                jobs = [j for j in jobs if j['screen'] in a.only.split(',')]
            if a.failed_in:
                jobs = select(jobs, failed_ids(a.failed_in))
            shots = Path(a.shots) if a.shots else None
            if shots:
                shots.mkdir(parents=True, exist_ok=True)
            count = sweep(jobs, lambda job: run_job(job, image.raw, a.firmware, a.drive or BLANK_DRIVE, shots), Path(a.out), a.workers,
                          experiment_of(a.firmware, image.raw, a.drive or BLANK_DRIVE))
            print(f'ran {count} jobs, {len(jobs)} selected, {len(skipped)} bindings cannot be tried')
            for binding_id, reason in skipped.items():
                print(f'  not tried {binding_id}: {reason}')
            return 0
        if a.command == 'xrefs':
            from .search import xrefs
            found = xrefs(Image.load(a.file), a.address)
            for source, kind in found:
                print(f'0x{source:08X}  {kind}')
            print(f'{len(found)} found for 0x{a.address & ~1:08X}. Calls through registers and computed addresses are not visible, and a pointer may be data')
            return 0
        if a.command == 'find':
            from .search import find_bytes
            found = find_bytes(Image.load(a.file), bytes.fromhex(a.what) if a.hex else a.what.encode())
            for address in found[:200]:
                print(f'0x{address:08X}')
            print(f'{len(found)} found'+(', first 200 shown' if len(found) > 200 else ''))
            return 0
        if a.command == 'map':
            for load, runtime, size, handler in image.rows:
                print(f'{HANDLER_NAMES[handler]:10} load 0x{load:08X}  runtime 0x{runtime:08X}  size 0x{size:X}')
        elif a.command == 'read':
            data = image.read(a.address, a.size)
            print(f'size {len(data)} sha256 {hashlib.sha256(data).hexdigest()}' if a.sha256 else data.hex())
        elif a.command == 'dis':
            from .hooks import _disassembler
            for ins in _disassembler().disasm(image.read(a.address, a.count*4), a.address, count=a.count):
                print(f'0x{ins.address:08X}  {ins.mnemonic} {ins.op_str}')
        elif a.command == 'check-hook':
            from .hooks import check_entry_hook
            displaced, picked = check_entry_hook(image, a.address, tuple(a.not_pointer))
            print(f'ok: displaces {len(displaced)} bytes')
            for ins in picked:
                print(f'  0x{ins.address:08X}  {ins.mnemonic} {ins.op_str}')
        return 0
    except ImageError as e:
        print(f'refused: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
