"""Build a mod described by mod.json on a user's APP1. Writes a new package and never replaces an existing one."""
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from . import hooks as hook_tools
from .identify import identify
from .image import RETURN_ZERO, Image, ImageError, extend, matches, protected, room, sha256
from .copy import place as place_copy, placeholder as copy_placeholder, plan_copy
from .link import LinkError, link_regions

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


def _data_source(mod_dir, items, label):
    """Assembly that puts each declared data file in read-only data under its symbol, with a symbol for its end."""
    out = []
    for n, item in enumerate(items):
        path = (mod_dir/item['file']).resolve()
        if mod_dir.resolve() not in path.parents or not path.is_file():
            raise BuildError(f'data file {item["file"]} must be a file inside the mod folder')
        out.append(f"""
    .section .rodata.lab404_{label}_{n},"a",%progbits
    .balign {int(item.get('align', 4))}
    .global {item['symbol']}
{item['symbol']}:
    .incbin "{path.as_posix()}"
    .global {item['symbol']}_end
{item['symbol']}_end:
""")
    return ''.join(out)


def compile_regions(mod_dir, mod, base_address, stubs, externals, extra_asm='', flash=None):
    """Compile the payload, and the flash block when the mod declares one, and link them together so each can use the
    other's symbols. Returns ([payload, flash block or None], symbols)."""
    with tempfile.TemporaryDirectory(prefix='lab404-') as tmp:
        tmp = Path(tmp)

        def objects(sources, asm, label):
            blobs = []
            for source in sources:
                obj = tmp/f'{label}-{Path(source).name}.o'
                _compile([*CFLAGS, '-c', str(mod_dir/source), '-o', str(obj)])
                blobs.append((source, obj.read_bytes()))
            if asm:
                path = tmp/f'{label}.S'
                path.write_text('.syntax unified\n.thumb\n.text\n'+asm, encoding='utf-8')
                obj = tmp/f'{label}-asm.o'
                _compile([*SFLAGS, '-c', str(path), '-o', str(obj)])
                blobs.append((f'{label}.S', obj.read_bytes()))
            return blobs
        regions = [(base_address, objects(mod['sources'], ''.join(stubs)+extra_asm+_data_source(mod_dir, mod.get('data', []), 'data'), 'payload'))]
        if flash:
            regions.append((_int(flash['address']), objects(flash.get('sources', []), _data_source(mod_dir, flash.get('data', []), 'flash'), 'flash')))
        try:
            blobs, symbols = link_regions(regions, externals)
        except LinkError as e:
            raise BuildError(str(e)) from None
        return blobs+([None] if not flash else []), symbols


def compile_payload(mod_dir, mod, base_address, stubs, externals):
    """Compile with stub addresses left to the linker. Returns (payload, symbols)."""
    (payload, _), symbols = compile_regions(mod_dir, mod, base_address, stubs, externals)
    return payload, symbols


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
    stubs, sites, words, disabled, jumps, byte_patches = [], [], [], [], [], []
    hooks = [hook for hook in mod.get('hooks', []) if who['sha256'] in hook.get('bases', allowed)]  # addresses belong to one exact image
    for i, hook in enumerate(hooks):
        address = _int(hook['address'])
        if hook.get('kind') == 'entry':
            declared = tuple(_int(item['address']) for item in hook.get('not_pointers', []))
            displaced, _ = hook_tools.check_entry_hook(image, address, declared)
            stubs.append(hook_tools.stub_source(i, address, hook['function'], displaced))
            sites.append((i, address, declared))
        elif hook.get('kind') == 'word':
            if 'expect' not in hook:
                raise BuildError(f'word hook at 0x{address:08X} needs "expect": the value the word holds on this base, read with `read BASE ADDRESS 4`')
            if any(address == done for done, _, _ in words):
                raise BuildError(f'two word hooks replace the same word at 0x{address:08X}')
            old = hook_tools.check_word_hook(image, address, _int(hook['expect']), who['family'])
            if 'original' in hook:  # the mod may call the code the word pointed to, by this name
                if hook['original'] in externals:
                    raise BuildError(f'{hook["original"]} is named twice')
                externals[hook['original']] = old
            words.append((address, old, hook['function']))
        elif hook.get('kind') == 'jump':
            declared = tuple(_int(item['address']) for item in hook.get('not_pointers', []))
            replaced = hook_tools.check_jump_hook(image, address, declared)
            if 'resume' in hook:  # where the mod may jump on to: the first byte after the replaced instructions
                if hook['resume'] in externals:
                    raise BuildError(f'{hook["resume"]} is named twice')
                externals[hook['resume']] = (address+len(replaced)) | 1
            jumps.append((address, hook['function'], declared))
        elif hook.get('kind') == 'patch':
            before, after = bytes.fromhex(hook['before']), bytes.fromhex(hook['after'])
            hook_tools.check_byte_patch(image, address, before, after, who['family'])
            byte_patches.append(dict(address=address, before=before, after=after))
        elif hook.get('kind') == 'disable':
            if any(address == done['address'] for done in disabled):
                raise BuildError(f'the routine at 0x{address:08X} is disabled twice')
            disabled.append(dict(address=address, before=hook_tools.check_disable_hook(image, address), after=RETURN_ZERO))
        else:
            raise BuildError(f'hook kind {hook.get("kind")!r} is not supported')
    copies = [plan_copy(image, spec) for spec in mod.get('copies', []) if who['sha256'] in spec.get('bases', allowed)]
    for plan in copies:
        if plan['name'] in externals:
            raise BuildError(f'{plan["name"]} is named twice')
    flash = mod.get('flash')
    (payload, block), symbols = compile_regions(mod_dir, mod, base_address, stubs, externals,
                                                ''.join(copy_placeholder(plan) for plan in copies), flash)
    if len(payload) > limit:
        raise BuildError(f'payload is {len(payload)} bytes, limit {limit}')
    payload = bytearray(payload)
    for plan in copies:  # the copies' room was reserved by the linker; now their bytes are known for their final place
        at = symbols[plan['name']] & ~1
        code = place_copy(plan, at, symbols)
        payload[at-base_address:at-base_address+len(code)] = code
    payload = bytes(payload)
    regions = [(base_address, len(payload))]
    if flash:
        flash_address = _int(flash['address'])
        if len(block) > _int(flash['max_size']):
            raise BuildError(f'flash block is {len(block)} bytes, limit {_int(flash["max_size"])}')
        regions.append((flash_address, len(block)))

    def mod_function(name):
        target = symbols.get(name)
        return target is not None and target & 1 and any(lo <= target < lo+size for lo, size in regions)
    patches = [hook_tools.plan_patch(image, address, symbols[f'lab404_stub_{i}'], declared) for i, address, declared in sites]
    for address, old, function in words:
        target = symbols.get(function)
        if target is None or not any(lo <= target < lo+size for lo, size in regions):
            raise BuildError(f'word hook at 0x{address:08X}: {function} is not defined by the mod')
        if not target & 1:
            raise BuildError(f'word hook at 0x{address:08X}: {function} is not a Thumb function (data, or an address without bit 0)')
        patches.append(dict(address=address, before=struct.pack('<I', old), after=struct.pack('<I', target)))
    for address, function, declared in jumps:
        target = symbols.get(function)
        if not mod_function(function):
            raise BuildError(f'jump hook at 0x{address:08X}: {function} is not a Thumb function of the mod')
        patches.append(hook_tools.jump_hook_patch(image, address, target, declared))
    patches += disabled+byte_patches
    result = extend(raw, base_address, payload, patches, (flash_address, block) if flash else None)
    manifest = dict(mod=mod['name'], mod_version=mod.get('version'), parent_sha256=who['sha256'], parent=f'{who["family"]} {who["version"]}',
                    candidate_sha256=sha256(result), size=len(result), flash_room_left=room(result), source_sha256=source_digest(mod_dir, mod), source_revision=source_revision(),
                    payload=dict(address=hex(base_address), bytes=len(payload), sha256=sha256(payload)),
                    hooks=[dict(address=hex(p['address']), before=p['before'].hex(), after=p['after'].hex()) for p in patches],
                    **(dict(flash=dict(address=hex(flash_address), bytes=len(block), sha256=sha256(block))) if flash else {}),
                    **(dict(copies=[dict(name=c['name'], source=f'0x{c["start"]:08X}-0x{c["end"]:08X}', placed=hex(symbols[c['name']] & ~1)) for c in copies]) if copies else {}),
                    symbols={k: hex(v) for k, v in sorted(symbols.items()) if not k.startswith('lab404_stub_')},
                    compiler=subprocess.run(['clang', '--version'], capture_output=True, text=True, encoding='utf-8').stdout.splitlines()[0],
                    status='candidate: built and structurally checked, not proven on a unit')
    out_dir.mkdir(parents=True)
    (out_dir/'SP404MKII_APP1.bin').write_bytes(result)
    (out_dir/'manifest.json').write_text(json.dumps(manifest, indent=1)+'\n', encoding='utf-8')
    return manifest


__all__ = ['BuildError', 'ImageError', 'build']
