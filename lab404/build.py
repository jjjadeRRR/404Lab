"""Build a mod described by mod.json on a user's APP1. Writes a new package and never replaces an existing one."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from . import hooks as hook_tools
from .identify import identify
from .image import Image, ImageError, extend, matches, protected, room, sha256
from .link import link

CFLAGS = ('--target=arm-none-eabi', '-mcpu=cortex-m7', '-mthumb', '-mfloat-abi=soft', '-mfpu=none', '-Os', '-ffreestanding',
          '-fno-common', '-fno-builtin', '-fno-exceptions', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
          '-fno-jump-tables', '-fno-stack-protector', '-fno-pic', '-std=c11', '-Wall', '-Wextra', '-Werror')
SFLAGS = ('--target=arm-none-eabi', '-mcpu=cortex-m7', '-mthumb')


class BuildError(ValueError):
    pass


def _int(value):
    return int(value, 0) if isinstance(value, str) else value


def _compile(argv):
    r = subprocess.run(['clang', *argv], capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        raise BuildError('compile failed:\n'+r.stderr)


def compile_payload(mod_dir, mod, base_address, stubs, externals):
    """Compile with stub addresses left to the linker. Returns (payload, symbols)."""
    with tempfile.TemporaryDirectory(prefix='lab404-') as tmp:
        tmp = Path(tmp)
        blobs = []
        for source in mod['sources']:
            obj = tmp/(Path(source).name+'.o')
            _compile([*CFLAGS, '-c', str(mod_dir/source), '-o', str(obj)])
            blobs.append((source, obj.read_bytes()))
        if stubs:
            asm = tmp/'stubs.S'
            asm.write_text('.syntax unified\n.thumb\n.text\n'+''.join(stubs), encoding='utf-8')
            obj = tmp/'stubs.o'
            _compile([*SFLAGS, '-c', str(asm), '-o', str(obj)])
            blobs.append(('stubs.S', obj.read_bytes()))
        return link(blobs, base_address, externals)


GUARD_BYTES = 8  # enough of a function's start to tell it from its neighbours


def firmware_symbols(mod, image):
    """Addresses of firmware functions the mod calls, each checked against the bytes the mod's author saw there.
    An address belongs to one exact image. Without this, a mod built on another base would call into whatever happens to be at that address."""
    out = {}
    for name, entry in mod.get('firmware_symbols', {}).items():
        if not isinstance(entry, dict) or not ('expect' in entry or 'sha256' in entry):
            raise BuildError(f'firmware symbol {name} must be {{"address": ..., "size": N, "sha256": "..."}}: '
                             f'get them with `read BASE ADDRESS N --sha256` (or "expect": hex of the bytes, for local use)')
        address = _int(entry['address'])
        expect = {'size': entry['size'], 'sha256': entry['sha256']} if 'sha256' in entry else {'hex': entry['expect']}
        length = int(expect['size']) if 'size' in expect else len(bytes.fromhex(expect['hex']))
        zone = protected(image, address)
        if zone:
            raise BuildError(f'firmware symbol {name}: 0x{address & ~1:08X} is inside {zone}. This code can erase the loader and brick the unit: a mod may not call it')
        if length < GUARD_BYTES:
            raise BuildError(f'firmware symbol {name}: the check needs at least {GUARD_BYTES} bytes')
        try:
            same, got = matches(image, address & ~1, expect)
        except ImageError as e:
            raise BuildError(f'firmware symbol {name}: {e}') from None
        if not same:
            raise BuildError(f'firmware symbol {name}: the {length} bytes at 0x{address & ~1:08X} are not the ones the mod expects '
                             f'(sha256 there {got}). This address is not that function on this base')
        out[name] = address
    return out


def source_digest(mod_dir, mod=None):
    """Every file in the mod folder, headers and notes included, except the user's approval, which is about the interface and not the code."""
    mod_dir = Path(mod_dir)
    h = hashlib.sha256()
    for path in sorted(p for p in mod_dir.rglob('*') if p.is_file() and p.name != 'approval.json' and '__pycache__' not in p.parts):
        h.update(str(path.relative_to(mod_dir)).encode()+b'\0'+path.read_bytes())
    return h.hexdigest()


def source_revision():
    """The revision of these tools, for every report."""
    root = str(Path(__file__).resolve().parents[1])
    try:
        head = subprocess.run(['git', '-C', root, 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True, encoding='utf-8').stdout.strip()
        dirty = subprocess.run(['git', '-C', root, 'status', '--porcelain'], capture_output=True, text=True, check=True, encoding='utf-8').stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'not a git checkout'
    return head+(' with uncommitted changes' if dirty else '')


def build(mod_dir, base_path, out_dir):
    mod_dir, out_dir = Path(mod_dir), Path(out_dir)
    if out_dir.exists():
        raise BuildError(f'{out_dir} exists: every build gets a new folder')
    mod = json.loads((mod_dir/'mod.json').read_text(encoding='utf-8'))
    raw = Path(base_path).read_bytes()
    who = identify(raw)
    if who['status'] != 'known':
        raise BuildError(f'base image not identified ({who["status"]}): identify it with the user first')
    allowed = mod.get('bases', [])
    if who['sha256'] not in allowed:
        raise BuildError(f'{mod["name"]} declares no support for {who["family"]} {who["version"]} ({who["sha256"]})')
    image = Image(raw)
    base_address = _int(mod['payload']['address'])
    limit = _int(mod['payload']['max_size'])
    externals = firmware_symbols(mod, image)
    stubs, sites = [], []
    hooks = [hook for hook in mod.get('hooks', []) if who['sha256'] in hook.get('bases', allowed)]  # addresses belong to one exact image
    for i, hook in enumerate(hooks):
        if hook.get('kind') != 'entry':
            raise BuildError(f'hook kind {hook.get("kind")!r} is not supported')
        address = _int(hook['address'])
        declared = tuple(_int(item['address']) for item in hook.get('not_pointers', []))
        displaced, _ = hook_tools.check_entry_hook(image, address, declared)
        stubs.append(hook_tools.stub_source(i, address, hook['function'], displaced))
        sites.append((i, address, declared))
    payload, symbols = compile_payload(mod_dir, mod, base_address, stubs, externals)
    if len(payload) > limit:
        raise BuildError(f'payload is {len(payload)} bytes, limit {limit}')
    patches = [hook_tools.plan_patch(image, address, symbols[f'lab404_stub_{i}'], declared) for i, address, declared in sites]
    result = extend(raw, base_address, payload, patches)
    manifest = dict(mod=mod['name'], mod_version=mod.get('version'), parent_sha256=who['sha256'], parent=f'{who["family"]} {who["version"]}',
                    candidate_sha256=sha256(result), size=len(result), flash_room_left=room(result), source_sha256=source_digest(mod_dir, mod), source_revision=source_revision(),
                    payload=dict(address=hex(base_address), bytes=len(payload), sha256=sha256(payload)),
                    hooks=[dict(address=hex(p['address']), before=p['before'].hex(), after=p['after'].hex()) for p in patches],
                    symbols={k: hex(v) for k, v in sorted(symbols.items()) if not k.startswith('lab404_stub_')},
                    compiler=subprocess.run(['clang', '--version'], capture_output=True, text=True, encoding='utf-8').stdout.splitlines()[0],
                    status='candidate: built and structurally checked, not proven on a unit')
    out_dir.mkdir(parents=True)
    (out_dir/'SP404MKII_APP1.bin').write_bytes(result)
    (out_dir/'manifest.json').write_text(json.dumps(manifest, indent=1)+'\n', encoding='utf-8')
    return manifest


__all__ = ['BuildError', 'ImageError', 'build']
