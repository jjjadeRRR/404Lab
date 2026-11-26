"""Boot a whole APP1 on the DM-404 emulator, press its keys and look at its screen.

DM-404 is a separate project, built by tools/setup_dm404.sh and used as an external program. It runs the firmware on an emulated machine with
interrupts and the RTOS, so it reaches what lab404/stand.py cannot: real screens and real key handling. Two limits stay:
- It models the second processor with a separate effects engine. Its sound and timing differ from the unit.
- A run here is evidence about firmware logic, never proof that something works on a unit.

Each run gets its own blank flash and a temporary overlay on a blank drive, so runs cannot affect each other or anything of the user's.
"""
import ctypes
import math
import os
import queue
import re
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from dataclasses import dataclass
from itertools import chain
from pathlib import Path, PurePosixPath

DM404 = Path(os.environ.get('LAB404_DEPS', Path.home()/'lab404-deps'))/'dm-404'
def _first_file(paths):
    return next((path for path in paths if path.is_file()), None)


def _release_dirs(root):
    return [root, root/'build', *sorted(root.glob('DM-404*-win64'), reverse=True),
            *sorted((root/'build/dist').glob('DM-404*-win64'), reverse=True)]


def find_qemu(root=None, windows=None):
    root = DM404 if root is None else Path(root)
    windows = os.name == 'nt' if windows is None else windows
    name = 'qemu-system-arm.exe' if windows else 'qemu-system-arm'
    return _first_file(directory/subdir/name for directory in _release_dirs(root)
                       for subdir in ('qemu', '', 'bin')) or root/'build/qemu'/name


def find_fatimg(root=None, windows=None):
    root = DM404 if root is None else Path(root)
    windows = os.name == 'nt' if windows is None else windows
    name = 'fatimg.exe' if windows else 'fatimg'
    return (_first_file(directory/subdir/name for directory in _release_dirs(root)
                        for subdir in ('', 'tools', 'qemu', 'bin')) or shutil.which(name))


def find_fx(qemu=None, system=None):
    if os.environ.get('SP404_FX'):
        override = Path(os.environ['SP404_FX']).expanduser()
        return override.resolve() if os.environ['SP404_FX'] != 'off' and override.is_file() else None
    qemu = Path(qemu or find_qemu())
    names = {'win32': ('sp404fx.dll',), 'darwin': ('sp404fx.dylib', 'libsp404fx.dylib')}.get(
        system or sys.platform, ('libsp404fx.so', 'sp404fx.so'))
    return _first_file(directory/name for directory in (qemu.parent, qemu.parent.parent/'fx')
                       for name in names)


def find_blank_drive(root=None):
    root = DM404 if root is None else Path(root)
    paths = [root/'build/internal-blank.img']
    paths.extend(directory/name for directory in _release_dirs(root)
                 for name in ('internal-blank.img', 'internal.img'))
    if os.environ.get('LOCALAPPDATA'):
        paths.append(Path(os.environ['LOCALAPPDATA'])/'DM-404/internal.img')
    return _first_file(paths) or paths[0]


DEFAULT_QEMU = find_qemu()
BLANK_DRIVE = find_blank_drive()  # QEMU opens the base through a temporary overlay
WIDTH, HEIGHT = 128, 64
FRAME_BYTES = WIDTH*HEIGHT//8
FLASH_SIZE = 4*1024*1024
MSG_FRAME, MSG_AUDIO, MSG_BMC = 1, 2, 3
SEND_KEY, SEND_ANALOG, SEND_BMC, SEND_ENCODER = 0x81, 0x82, 0x83, 0x84
PCM_RATE, PCM_FRAME_BYTES = 48000, 4
_PCM_BATCH_BYTES = 512 * PCM_FRAME_BYTES
_PCM_PRIME_BYTES = 6 * _PCM_BATCH_BYTES  # 64 ms of audio before opening the sink



# Wiring of the panel in the emulated machine [DOC: DM-404's panel map]. Names are those of knowledge/controls.json.
KEYS = {'EXT SOURCE': (0, 0), 'BUS FX': (0, 1), 'RESAMPLE': (0, 2), 'BANK E/J': (0, 3), 'DEL': (0, 4), 'ISOLATOR': (1, 0), 'HOLD': (1, 1), 'REC': (1, 2),
        'BANK D/I': (1, 3), 'DELAY': (2, 0), 'MARK': (2, 1), 'RECORD SETTING': (2, 2), 'GATE': (2, 3), 'DJFX LOOPER': (3, 0), 'ROLL': (3, 1), 'REMAIN': (3, 2),
        'BANK C/H': (3, 3), 'RESONATOR': (4, 0), 'REVERSE': (4, 1), 'COPY': (4, 2), 'BANK B/G': (4, 3), 'FILTER+DRIVE': (5, 0), 'LOOP': (5, 1), 'EXIT': (5, 2),
        'BANK A/F': (5, 3), 'MFX': (6, 0), 'START/END': (6, 1), 'PATTERN EDIT': (6, 2), 'BPM SYNC': (6, 3), 'PITCH/SPEED': (7, 1), 'PATTERN SELECT': (7, 2),
        'VALUE': (7, 3)}
PADS = {1: (5, 7), 2: (5, 5), 3: (4, 5), 4: (4, 3), 5: (5, 6), 6: (5, 4), 7: (4, 7), 8: (4, 2), 9: (5, 3), 10: (5, 0), 11: (4, 6), 12: (4, 1),
        13: (5, 2), 14: (5, 1), 15: (4, 4), 16: (4, 0)}
SUB_PAD = (6, 4)
KNOBS = {'CTRL1': (6, 1), 'CTRL2': (6, 2), 'CTRL3': (6, 3)}
ANALOG_IDLE, ANALOG_FULL = 4095, 0
# Light index of each button [DOC: DM-404's panel map]. Pad n has three lights, red, green and blue, at 3(n-1) onward.
KEY_LEDS = {'BANK A/F': 70, 'BANK B/G': 71, 'BANK C/H': 72, 'BANK D/I': 73, 'BANK E/J': 74, 'BPM SYNC': 62, 'BUS FX': 49, 'COPY': 68, 'DEL': 59, 'DELAY': 78, 'DJFX LOOPER': 80, 'EXIT': 67,
            'EXT SOURCE': 51, 'FILTER+DRIVE': 76, 'GATE': 63, 'HOLD': 50, 'ISOLATOR': 79, 'LOOP': 64, 'MARK': 58, 'MFX': 81, 'PATTERN EDIT': 54, 'PATTERN SELECT': 53, 'PITCH/SPEED': 57,
            'REC': 60, 'RECORD SETTING': 55, 'REMAIN': 69, 'RESAMPLE': 61, 'RESONATOR': 77, 'REVERSE': 65, 'ROLL': 66, 'SHIFT': 75, 'START/END': 56, 'SUB PAD': 52}
LED_COUNT = max(KEY_LEDS.values()) + 1
# The firmware's current-page word [DOC: DM-404's notes]. The main screen reads as MAIN_PAGE, the boot logos as 2 [EMULATOR: test_ready_means_the_main_screen_even_under_load].
MAIN_PAGE_WORD, MAIN_PAGE = 0x80245880, 1
CONTROLS_NOT_ON_THE_LINK = ('VOLUME', 'INPUT GAIN', 'MIC/GUITAR', 'POWER')  # analog parts after the firmware, or the machine's power [DOC: DM-404's notes]


def control_route(name):
    """How a named control reaches the firmware: 'key', 'pad', 'shift', 'knob', or None if it cannot be operated here."""
    if name == 'SHIFT':
        return 'shift'
    if name == 'SUB PAD' or (name.startswith('PAD') and name[3:].isdigit() and int(name[3:]) in PADS):
        return 'pad'
    if name in KNOBS:
        return 'knob'
    return 'key' if name in KEYS else None


def available(qemu=DEFAULT_QEMU):
    return Path(qemu).is_file() and find_blank_drive().is_file()


@dataclass(frozen=True)
class Transport:
    family: int
    link: str | tuple
    monitor: str | tuple
    chardev: str
    monitor_arg: str


def select_transport(root, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    if not windows and hasattr(socket, 'AF_UNIX'):
        link, monitor = str(root/'link.sock'), str(root/'monitor.sock')
        # QEMU separates socket options with commas. Keep the actual paths for connect().
        link_arg, monitor_arg = link.replace(',', ',,'), monitor.replace(',', ',,')
        return Transport(socket.AF_UNIX, link, monitor, f'socket,id=link,path={link_arg},server=on,wait=on',
                         f'unix:{monitor_arg},server,nowait')
    host = '127.0.0.1'
    # Keep both sockets bound until both distinct ports have been selected.
    with socket.socket() as left, socket.socket() as right:
        left.bind((host, 0))
        right.bind((host, 0))
        link, monitor = left.getsockname(), right.getsockname()
    return Transport(socket.AF_INET, link, monitor,
                     f'socket,id=link,host={host},port={link[1]},server=on,wait=on',
                     f'tcp:{host}:{monitor[1]},server,nowait')


@dataclass(frozen=True)
class ProjectMedia:
    drive: Path | None = None
    sd_card: Path | None = None


def _run_fatimg(args, cancel, *, capture=False):
    # Read diagnostics without filling up a pipe. Close can cancel a large import.
    with tempfile.TemporaryFile() as output, subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
        try:
            while process.poll() is None:
                if cancel.wait(0.1):
                    raise RuntimeError('Project import cancelled.')
        finally:
            if process.poll() is None:
                process.kill()
        if process.returncode:
            output.seek(0, os.SEEK_END)
            output.seek(max(0, output.tell() - 1500))
            raise RuntimeError('fatimg could not prepare the project: ' + output.read().decode('utf-8', 'replace').strip())
        if capture:
            output.seek(0)
            return output.read().decode('utf-8', 'replace')


def _run_picker(args, cancel):
    with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, encoding='utf-8') as process:
        while not cancel.is_set():
            try:
                output, _ = process.communicate(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
            if process.returncode == 1:
                return None  # the user cancelled the dialog
            if process.returncode != 0:
                raise OSError('The file picker could not open.')
            return output.removesuffix('\n') or None
        process.kill()
        return None


def pick_linux_path(title, initial, file_filter=None, *, cancel=None):
    """Use the installed desktop file picker and return its local path, if selected."""
    cancel = cancel or threading.Event()
    kde = 'kde' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    programs = ('kdialog', 'zenity', 'yad') if kde else ('zenity', 'yad', 'kdialog')
    for program in programs:
        if cancel.is_set():
            return None
        binary = shutil.which(program)
        if not binary:
            continue
        args = [binary, '--title', title]
        if program == 'kdialog':
            args.extend(['--getopenfilename' if file_filter else '--getexistingdirectory', str(initial)])
            if file_filter:
                label, patterns = file_filter
                args.append(f'{label} ({patterns})')
        else:
            args.extend(['--file-selection' if program == 'zenity' else '--file',
                         '--filename=' + str(initial).rstrip('/') + '/'])
            if file_filter:
                label, patterns = file_filter
                args.append(f'--file-filter={label} | {patterns}')
            else:
                args.append('--directory')
        try:
            return _run_picker(args, cancel)
        except OSError:
            continue
    raise RuntimeError('Could not open a Linux file picker. Install KDialog, Zenity, or YAD.')


def _is_sd_image(path):
    with path.open('rb') as image:
        boot = image.read(512)
    if len(boot) != 512 or boot[510:] != b'\x55\xaa':
        return False
    if boot[82:90] == b'FAT32   ':
        return True
    if boot[3:11] in (b'EXFAT   ', b'NTFS    ') or boot[54:62] in (b'FAT12   ', b'FAT16   '):
        return False
    # Partitioned SD cards have an MBR rather than a FAT boot sector at LBA 0.
    return any(boot[i] in (0, 128) and boot[i + 4] in (1, 4, 6, 7, 11, 12, 14, 238)
               and int.from_bytes(boot[i + 8:i + 12], 'little') > 0
               and int.from_bytes(boot[i + 12:i + 16], 'little') > 0
               for i in range(446, 510, 16))


def _project_entries(source, entries):
    name = source.name.upper()
    if name.startswith('PROJECT_'):
        yield source, '/IMPORT'
        return
    if name == 'EXPORT':
        for entry in entries:
            if entry.is_dir() and entry.name.upper() in ('PROJECT', 'SAMPLE'):
                yield from ((child, '/IMPORT') for child in sorted(entry.iterdir()))
            else:
                yield entry, '/IMPORT'
        return

    work = [source] if name in ('IMPORT', 'ROLAND') else entries
    for entry in work:
        name = entry.name.upper()
        if entry.is_dir() and name in ('IMPORT', 'EXPORT'):
            yield from ((child, '/' + name) for child in sorted(entry.iterdir()))
        elif entry.is_dir() and name == 'ROLAND':
            projects = [child for model in sorted(entry.iterdir())
                        if model.is_dir() and model.name.upper() == 'SP-404MKII'
                        for child in sorted(model.iterdir())
                        if child.is_dir() and child.name.upper().startswith('PROJECT_')]
            if projects:
                yield from ((project, '/IMPORT') for project in projects)
            else:
                yield entry, '/'
        else:
            yield entry, '/IMPORT'


PADCONF_SIZES = (0x7B00, 0xCB00, 0xCB20)  # st.storage.padconf


def _padconf(entries):
    return next((entry for entry in entries if entry.name.upper() == 'PADCONF.BIN'), None)


def _check_padconf(path):
    if path.is_file() and not path.is_symlink() and path.stat().st_size in PADCONF_SIZES:
        with path.open('rb') as config:
            if config.read(8) == b'RFPD\x00\x00\x00\xa0':
                return
    raise ValueError(f'Invalid SP-404MKII PADCONF.BIN in {path.parent.name}.')


def _check_wav(path):
    with path.open('rb') as sample:
        header = sample.read(12)
        size = path.stat().st_size
        if header[:4] == b'RIFF' and header[8:] == b'WAVE':
            end = min(size, int.from_bytes(header[4:8], 'little') + 8)
            found = set()
            while sample.tell() + 8 <= end:
                tag, length = struct.unpack('<4sI', sample.read(8))
                if sample.tell() + length > end:
                    break
                if (tag == b'fmt ' and length >= 16) or (tag == b'data' and length > 0):
                    found.add(tag)
                if found == {b'fmt ', b'data'}:
                    return
                sample.seek(length + length % 2, os.SEEK_CUR)
    raise ValueError(f'Invalid WAV file: {path.name}.')


def _import_entries(entry, destination, cancel):
    if cancel.is_set():
        raise RuntimeError('Project import cancelled.')
    if entry.name.startswith('.'):
        return
    if entry.is_symlink():
        raise ValueError('Remove symbolic links from the project folder and try again.')
    if entry.is_dir():
        children = sorted(entry.iterdir())
        config = _padconf(children)
        if config is not None:
            _check_padconf(config)
            yield entry, destination
        else:
            for child in children:
                yield from _import_entries(child, f'{destination}/{entry.name}', cancel)
    elif entry.is_file() and entry.suffix.lower() == '.wav':
        _check_wav(entry)
        yield entry, destination


def _check_tree(paths, cancel):
    size = 0
    count = 0
    for source in paths:
        for entry in chain((source,), source.rglob('*')):
            if cancel.is_set():
                raise RuntimeError('Project import cancelled.')
            if entry.is_symlink():
                raise ValueError('Remove symbolic links from the project folder and try again.')
            if entry.is_file():
                size += entry.stat().st_size
                count += 1
            elif not entry.is_dir():
                raise ValueError('Project folders must contain regular files and folders.')
    return size, count


def _project_folder(source, cancel):
    entries = sorted(source.iterdir())
    config = _padconf(entries)
    if config is not None:
        _check_padconf(config)
        items = [entry for entry in entries if not entry.name.startswith('.')]
        _check_tree(items, cancel)
        return True, [(entry, '/ROLAND/SP-404MKII/PROJECT_01') for entry in items]
    roots = [entry for entry in entries if entry.is_dir() and entry.name.upper() in ('IMPORT', 'EXPORT', 'ROLAND')]
    prepared = [item for entry, destination in _project_entries(source, roots or entries)
                for item in _import_entries(entry, destination.rstrip('/'), cancel)]
    if not prepared:
        raise ValueError('Choose an SP-404MKII project or WAV folder.')
    return False, prepared


def _extract_and_check(fatimg, image, remote_path, filename, scratch, cancel, check):
    with tempfile.TemporaryDirectory(dir=scratch) as extracted:
        _run_fatimg([str(fatimg), 'get', str(image), remote_path, extracted], cancel)
        check(Path(extracted)/filename)


def _scan_sd_wav(fatimg, image, directory, scratch, cancel):
    try:
        listing = _run_fatimg([str(fatimg), 'ls', str(image), directory], cancel, capture=True)
    except RuntimeError:
        if cancel.is_set():
            raise
        return False
    for match in re.finditer(r'^.{17} *(\d+)  ([^/\\\r\n]+\.wav)$', listing, re.M | re.I):
        if int(match[1]) > 0:
            _extract_and_check(fatimg, image, f'{directory}/{match[2]}', match[2], scratch, cancel, _check_wav)
            return True
    for name in re.findall(r'^.{17} *<DIR>  ([^/\\\r\n]+)$', listing, re.M):
        if _scan_sd_wav(fatimg, image, f'{directory}/{name}', scratch, cancel):
            return True
    return False


def _validate_project_image(image, scratch, fatimg, cancel):
    if cancel.is_set():
        raise RuntimeError('Project import cancelled.')
    sd_card = _is_sd_image(image)
    with image.open('rb') as file:
        boot = file.read(512)
    if len(boot) != 512 or boot[510:] != b'\x55\xaa' or (not sd_card and boot[3:11] != b'EXFAT   '):
        raise ValueError('Choose a FAT SD card or a DM-404 internal project image.')
    if not fatimg:
        raise RuntimeError('fatimg is required to check project images.')
    prefix = [str(fatimg), 'ls', str(image)]
    locations = ('/IMPORT', '/EXPORT/PROJECT') if sd_card else ('/ROLAND/SP-404MKII',)
    for location in locations:
        try:
            listing = _run_fatimg([*prefix, location], cancel, capture=True)
        except RuntimeError:
            if cancel.is_set():
                raise
            continue
        for name in re.findall(r'^.{17} *<DIR>  ([^/\\\r\n]+)$', listing, re.M):
            project = f'{location}/{name}'
            contents = _run_fatimg([*prefix, project], cancel, capture=True)
            config = re.search(r'^.{17} *(\d+)  (PADCONF\.BIN)$', contents, re.M | re.I)
            if config and int(config[1]) in PADCONF_SIZES:
                _extract_and_check(fatimg, image, f'{project}/{config[2]}', config[2], scratch, cancel, _check_padconf)
                return ProjectMedia(sd_card=image) if sd_card else ProjectMedia(drive=image)
    if sd_card:
        for location in ('/IMPORT', '/EXPORT/SAMPLE'):
            if _scan_sd_wav(fatimg, image, location, scratch, cancel):
                return ProjectMedia(sd_card=image)
        raise ValueError('The project image contains no SP-404MKII project or WAV samples.')
    raise ValueError('The project image contains no SP-404MKII project.')


def check_project_source(source, scratch, *, cancel, fatimg=None):
    source = Path(source).expanduser().resolve()
    if source.is_file() and source.suffix.lower() == '.img':
        return _validate_project_image(source, Path(scratch), fatimg or find_fatimg(), cancel)
    if not source.is_dir():
        raise ValueError('Choose an SP-404MKII project or WAV folder, or a project image (.img).')
    return _project_folder(source, cancel)


def prepare_project_media(source, directory, *, fatimg=None, cancel=None):
    """Prepare an internal project, an SD import folder, or an existing image."""
    cancel = cancel or threading.Event()
    media = check_project_source(source, directory, cancel=cancel, fatimg=fatimg)
    if isinstance(media, ProjectMedia):
        return media
    internal, imports = media
    fatimg = fatimg or find_fatimg()
    if not fatimg:
        raise RuntimeError('fatimg was not found. Build fatimg from DM-404 to import project media.')
    size, count = _check_tree((src for src, _ in imports), cancel)
    image = Path(directory)/'project.img'
    # Allow for FAT metadata, cluster rounding and room for firmware writes.
    mb = max(128, (size + count * 32768 + (1 << 20) - 1) // (1 << 20) + 64)
    mb = 1 << (mb - 1).bit_length()
    prefix = [str(fatimg)]
    directories = set() if internal else {'IMPORT', 'EXPORT'}
    for _, target in imports:
        path = PurePosixPath(target)
        directories.update(str(parent).lstrip('/') for parent in (path, *path.parents) if parent.name)
    kind = 'exfat' if internal or mb > 32768 else 'fat32'
    _run_fatimg([*prefix, 'create', str(image), str(mb), kind, 'bare' if internal else 'part',
                 'SP-404MKII', *sorted(directories)], cancel)
    for entry, target in imports:
        _run_fatimg([*prefix, 'add', str(image), str(entry), target or '/'], cancel)
    return ProjectMedia(drive=image) if internal else ProjectMedia(sd_card=image)


def led_level(state, seconds):
    """Interpolate the BMC pages using DM-404's blink and pulse frequencies."""
    base, page, target = state
    if page == 6:
        return target if seconds % 0.5 < 0.25 else (base if base < target else 0)
    if page in (7, 9):
        hz = 1.5 if page == 7 else 0.5
        weight = (1 - math.cos(seconds * math.tau * hz)) / 2
        return int(base + (target - base) * weight + 0.5)
    return base


def _drive_arg(index, path):
    if path is None:
        return f'if=sd,index={index}'
    file = str(Path(path).resolve()).replace(',', ',,')
    return f'if=sd,index={index},format=raw,snapshot=on,file={file}'



def frame_png(frame, scale=4):
    """A 1-bit frame, 128x64, most significant bit first, as PNG bytes."""
    rows = []
    for y in range(HEIGHT*scale):
        row = bytearray([0])
        for x in range(WIDTH*scale):
            lit = frame[(y//scale)*(WIDTH//8)+(x//scale)//8] & (0x80 >> ((x//scale) & 7))
            row += b'\xe8\xf0\xff' if lit else b'\x00\x00\x00'
        rows.append(bytes(row))

    def chunk(kind, body):
        return struct.pack('>I', len(body))+kind+body+struct.pack('>I', zlib.crc32(kind+body) & 0xFFFFFFFF)
    header = struct.pack('>IIBBBBB', WIDTH*scale, HEIGHT*scale, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', header)+chunk(b'IDAT', zlib.compress(b''.join(rows)))+chunk(b'IEND', b'')


def lit_pixels(frame):
    return sum(bin(b).count('1') for b in frame)


class Emulator:
    """with Emulator(image_bytes) as unit: unit.wait_for_screen(); unit.tap(row, col); unit.frame"""

    def __init__(self, image, qemu=DEFAULT_QEMU, extra_args=(), drive=BLANK_DRIVE,
                 sd_card=None, audio_sink=None, cancel=None, fx=None):
        """Use an overlay for each mounted drive. The optional audio sink receives PCM bytes."""
        self.image, self.qemu, self.extra_args, self.drive = image, str(qemu), list(extra_args), drive
        self.sd_card, self.audio_sink, self.fx = sd_card, audio_sink, fx
        self._cancel = cancel or threading.Event()
        self.audio_queue = queue.Queue(maxsize=16)
        self._audio_batch = bytearray()
        self._stopped = threading.Event()
        self.audio_peak = 0
        self.frame = bytes(FRAME_BYTES)
        self.frames = 0
        self.audio_frames = 0
        self.bmc_packets = []
        self.leds = {}
        self._led_pending = {}
        self._led_epoch = time.monotonic()
        self.lock = threading.Lock()
        self.process = self.sock = self.dir = None
        self._reader_thread = self._audio_thread = None
        self.disconnected = threading.Event()
        self._fx_active = None

    def __enter__(self):
        self._stopped.clear()
        self.disconnected.clear()
        self._fx_active = None
        self.dir = tempfile.TemporaryDirectory(prefix='lab404-unit-')
        try:
            self._start(Path(self.dir.name))
        except BaseException:
            self.__exit__()
            raise
        return self

    def _start(self, root):
        (root/'APP1.bin').write_bytes(self.image)
        (root/'flash.bin').write_bytes(b'\xFF'*FLASH_SIZE)
        self.transport = select_transport(root)
        monitor = self.transport.monitor
        self.monitor_path = Path(monitor) if isinstance(monitor, str) else monitor
        self.output_path = root/'output.log'
        env = os.environ.copy()
        # Preserve the engine choice of existing callers. The GUI passes the
        # discovered library explicitly, and QEMU still honors SP404_FX itself.
        if self.fx:
            env['SP404_FX'] = str(Path(self.fx).resolve())
        flash = str(root/'flash.bin').replace(',', ',,')
        # A file avoids the backpressure of an unread QEMU diagnostic pipe.
        with self.output_path.open('wb') as output:
            self.process = subprocess.Popen(
                [self.qemu, '-M', f'sp404mk2,flash={flash},link=link', '-bios', str(root/'APP1.bin'),
                 '-chardev', self.transport.chardev,
                 '-drive', _drive_arg(0, self.sd_card), '-drive', _drive_arg(1, self.drive),
                 '-nographic', '-monitor', self.transport.monitor_arg, '-serial', 'none', *self.extra_args],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=output, env=env,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(100):
            with socket.socket(self.transport.family) as attempt:
                try:
                    attempt.settimeout(0.1)
                    attempt.connect(self.transport.link)
                except OSError:
                    if self.process.poll() is not None:
                        raise RuntimeError('DM-404 exited: ' + self.output_tail()) from None
                    if self._cancel.wait(0.1):
                        raise RuntimeError('Emulator start cancelled.') from None
                else:
                    attempt.settimeout(None)
                    self.sock = attempt.dup()
                    break
        else:
            raise RuntimeError('DM-404 did not open its link.')
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()
        if self.audio_sink is not None:
            self._audio_thread = threading.Thread(target=self._play_audio, daemon=True)
            self._audio_thread.start()

    def __exit__(self, *_):
        self._stopped.set()
        if self.process is not None:
            self.process.kill()
            self.process.wait()
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
        if self._reader_thread is not None:
            self._reader_thread.join()
        if isinstance(self.audio_sink, NativeAudioPlayer):
            self.audio_sink.stop()
        if self._audio_thread is not None:
            self._audio_thread.join(timeout=2)
        if self.dir is not None:
            self.dir.cleanup()

    @property
    def fx_active(self):
        if self._fx_active is None and self.frames:
            # Machine initialization resumes after the initial link connects.
            # The first frame arrives after the FX engine has logged its result.
            with self.output_path.open('rb') as output:
                self._fx_active = b'sp404-fx: effects engine ' in output.read(65536)
        return bool(self._fx_active)

    def output_tail(self, size=500):
        """The last things the machine said."""
        with self.output_path.open('rb') as output:
            output.seek(0, os.SEEK_END)
            output.seek(max(0, output.tell() - size))
            return output.read().decode('utf-8', errors='replace')

    def _queue_audio(self, payload):
        try:
            self.audio_queue.put_nowait(payload)
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            self.audio_queue.put_nowait(payload)

    def _deliver_audio(self, payload):
        if not isinstance(self.audio_sink, NativeAudioPlayer):
            self._queue_audio(payload)
            return
        # The DM-404 link sends 64 frames per packet. Batch eight packets
        # before waking the playback thread, so the queue can absorb bursts.
        self._audio_batch.extend(payload)
        complete = len(self._audio_batch) // _PCM_BATCH_BYTES * _PCM_BATCH_BYTES
        for offset in range(0, complete, _PCM_BATCH_BYTES):
            self._queue_audio(bytes(self._audio_batch[offset:offset+_PCM_BATCH_BYTES]))
        del self._audio_batch[:complete]

    def _play_audio(self):
        try:
            while not self._stopped.is_set() and not self.disconnected.is_set():
                try:
                    payload = self.audio_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                self.audio_sink(payload)
        finally:
            if isinstance(self.audio_sink, NativeAudioPlayer):
                self.audio_sink.finish()

    def _read_leds(self, payload, now):
        for at in range(0, len(payload)-3, 4):
            head, page, index, value = payload[at:at+4]
            if head & 0x0F != 1 or page >= 16 or page in (4, 5) or index >= LED_COUNT:
                continue
            base = self.leds.get(index, (0, 0, 0))[0]
            if page in (6, 7, 9):
                self.leds[index] = (base, page, value)
            else:
                previous = self._led_pending.get(index, (now, now, self.leds.get(index, (0, 0, 0))))
                self._led_pending[index] = (previous[0], now, previous[2])
                self.leds[index] = (value, 0, value)

    def panel_snapshot(self, now):
        with self.lock:
            for index, (first, last, _) in tuple(self._led_pending.items()):
                if now - last >= 0.012 or now - first >= 0.04:
                    del self._led_pending[index]
            elapsed = now - self._led_epoch
            levels = {}
            for index, state in self.leds.items():
                if state[1] == 0 and index in self._led_pending:
                    state = self._led_pending[index][2]
                levels[index] = led_level(state, elapsed)
            return self.frame, levels

    def _reader(self):
        buffer = b''
        try:
            while data := self.sock.recv(65536):
                buffer += data
                offset = 0
                while len(buffer)-offset >= 4:
                    kind, _, size = struct.unpack_from('<BBH', buffer, offset)
                    start, end = offset+4, offset+4+size
                    if len(buffer) < end:
                        break
                    payload = buffer[start:end]
                    offset = end
                    with self.lock:
                        if kind == MSG_FRAME and size == FRAME_BYTES:
                            self.frame = payload
                            self.frames += 1
                        elif kind == MSG_AUDIO:
                            size -= size % 4
                            self.audio_frames += size//4
                            samples = struct.unpack(f'<{size//2}h', payload[:size])
                            self.audio_peak = max(self.audio_peak, max(map(abs, samples), default=0))
                        elif kind == MSG_BMC:
                            self.bmc_packets.append(payload)
                            self._read_leds(payload, time.monotonic())
                    if kind == MSG_AUDIO and self.audio_sink is not None and size:
                        self._deliver_audio(payload[:size])
                buffer = buffer[offset:]
        except OSError:
            pass
        finally:
            self.disconnected.set()

    def _send(self, kind, payload):
        self.sock.sendall(struct.pack('<BBH', kind, 0, len(payload))+payload)

    def key(self, row, col, down):
        self._send(SEND_KEY, bytes([row, col, 1 if down else 0]))

    def tap(self, row, col, hold=0.15, settle=0.6):
        self.key(row, col, True)
        time.sleep(hold)
        self.key(row, col, False)
        time.sleep(settle)

    def press(self, name, hold=0.15, settle=0.6):
        """Tap a control by name: a key, or PAD1 to PAD16."""
        self.hold(name)
        time.sleep(hold)
        self.release(name)
        time.sleep(settle)

    def hold(self, name):
        """Put a control down and leave it down. Any control with a route, SHIFT included."""
        self._contact(name, True)

    def release(self, name):
        self._contact(name, False)

    def _contact(self, name, down):
        route = control_route(name)
        if route == 'shift':
            self._send(SEND_BMC, bytes.fromhex('00ffff01' if down else '00ffff00'))
        elif route == 'key':
            self.key(*KEYS[name], down)
        elif route == 'pad':
            channel, mux = SUB_PAD if name == 'SUB PAD' else PADS[int(name[3:])]
            self.analog(0, channel, mux, ANALOG_FULL if down else ANALOG_IDLE)
        else:
            raise ValueError(f'{name} cannot be held on the emulator')

    def turn_control(self, name, step):
        """VALUE by detents. A CTRL knob moves from its middle by step tenths of its travel; the first move also sets the middle."""
        if name == 'VALUE':
            self.turn(step, settle=0)
        elif name in KNOBS:
            channel, mux = KNOBS[name]
            self.analog(0, channel, mux, 2048)
            time.sleep(0.2)
            self.analog(0, channel, mux, 2048+step*400)
        else:
            raise ValueError(f'{name} cannot be turned')

    def set_knob(self, name, value):
        """Set a CTRL knob position from fully counterclockwise (0) to clockwise (4095)."""
        channel, mux = KNOBS[name.replace(' ', '')]
        position = max(0, min(4095, int(value)))
        # As in the DM-404 panel, the ADC value falls as the knob turns clockwise.
        self.analog(0, channel, mux, 4095 - position)

    def wait(self, seconds):
        time.sleep(seconds)

    def shift(self, down):
        """SHIFT reaches the firmware from the second processor, as a packet."""
        self._send(SEND_BMC, bytes.fromhex('00ffff01' if down else '00ffff00'))
        time.sleep(0.1)

    def press_with_shift(self, name, settle=0.8):
        self.shift(True)
        self.press(name, settle=0.2)
        self.shift(False)
        time.sleep(settle)

    def turn(self, detents, settle=0.4):
        self._send(SEND_ENCODER, struct.pack('<b', detents))
        if settle:
            time.sleep(settle)

    def analog(self, adc, channel, mux, value):
        self._send(SEND_ANALOG, struct.pack('<BBBH', adc, channel, mux, value))

    def wait_until_stable(self, timeout=60, quiet=3.0):
        """Wait until the screen has lit pixels and stops changing. Returns False on timeout. Time here is wall clock, for a live emulator."""
        end = time.time()+timeout
        last, since = None, time.time()
        while time.time() < end:
            with self.lock:
                current = self.frame
            if current != last:
                last, since = current, time.time()
            elif lit_pixels(current) and time.time()-since >= quiet:
                return True
            time.sleep(0.1)
        return False

    def wait_for_main(self, timeout=45, quiet=3.0):
        """Wait for the main screen: the page word says so, the picture has stopped changing, and audio blocks keep arriving, which shows the machine and the link are alive.
        A still logo during boot does not count. Returns False on timeout. The word's address is checked on stock 5.52 and DOOM OS 0.7.3 and their candidates;
        on anything else this times out rather than guessing."""
        end = time.time()+timeout
        last, since, audio_at = None, time.time(), self.audio_frames
        while time.time() < end:
            with self.lock:
                current, audio = self.frame, self.audio_frames
            try:
                on_main = self.read_u32(MAIN_PAGE_WORD) & 0xFFFF == MAIN_PAGE
            except (OSError, RuntimeError):
                on_main = False
            if current != last or not on_main:
                last, since, audio_at = current, time.time(), audio
            elif lit_pixels(current) and time.time()-since >= quiet and audio > audio_at:
                return True
            time.sleep(0.1)
        return False

    def _monitor_socket(self):
        endpoint = self.monitor_path
        if isinstance(endpoint, tuple):
            family = socket.AF_INET
        else:
            family, endpoint = socket.AF_UNIX, os.fspath(endpoint)
        connection = socket.socket(family)
        try:
            connection.settimeout(1)
            connection.connect(endpoint)
        except BaseException:
            connection.close()
            raise
        return connection

    def read_u32(self, address):
        """A word of the running firmware's memory, through the emulator's monitor. Raises RuntimeError if it cannot be read within two seconds."""
        data = b''
        end = time.monotonic()+2
        with self._monitor_socket() as s:
            s.sendall(f'xp/1wx 0x{address:08X}\n'.encode())
            while time.monotonic() < end:
                reply = data.split(b'xp/1wx', 1)[-1]
                if b'(qemu) ' in reply and b':' in reply:
                    break
                try:
                    more = s.recv(4096)
                except socket.timeout:
                    break
                if not more:
                    break
                data += more
        for line in data.decode(errors='replace').splitlines():
            if line.strip().lower().startswith((f'{address:016x}:', f'{address:08x}:')):
                return int(line.split(':')[1].split()[0], 16)
        raise RuntimeError(f'could not read 0x{address:08X}')

    def _monitor(self, command):
        data = b''
        with self._monitor_socket() as s:
            s.sendall(command.encode()+b'\n')
            end = time.monotonic()+2
            while time.monotonic() < end and data.count(b'(qemu) ') < 2:
                try:
                    more = s.recv(65536)
                except socket.timeout:
                    break
                if not more:
                    break
                data += more
        text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', data.decode(errors='replace')).replace('\r', '')  # the monitor redraws its line with terminal codes
        return text.split('\n', 1)[-1].split('(qemu)', 1)[0].strip() if command not in text else text.split(command, 1)[-1].split('(qemu)', 1)[0].strip()

    def words(self, address, count):
        """count words of the running firmware's memory, read in one go through the monitor."""
        text = self._monitor(f'xp /{count}wx 0x{address:08X}')
        out = [int(x, 16) for line in text.splitlines() if ':' in line for x in re.findall(r'0x([0-9a-f]{8})', line.split(':', 1)[1])]
        if len(out) != count:
            raise RuntimeError(f'read {len(out)} of {count} words at 0x{address:08X}')
        return out

    def malloc_pool(self):
        """The stock malloc pool as the RTOS keeps it: free bytes, the biggest free piece, the number of free pieces (st.mem.heap-walk).

        Walked from outside, so it works on any image with the stock heap, with or without a mod's own monitor. Raises RuntimeError
        when the walk leaves the pool, which means the layout is not the one described in the fact."""
        pool_id = self.words(0x80245820, 1)[0]
        if not 1 <= pool_id <= 8:
            raise RuntimeError(f'malloc pool id {pool_id}')
        block = 0x202BA8EC+60*(pool_id-1)
        w = self.words(block, 15)
        start, size, head = w[12], w[5], block+0x20
        end = start+size
        free = biggest = pieces = 0
        node = w[8]
        while node != head:
            if pieces >= 4000 or not start+8 <= node < end:
                raise RuntimeError(f'the pool walk left the pool at 0x{node:08X}')
            piece = node-8
            following = self.words(piece, 1)[0] & ~7
            stop = following if piece < following <= end else end
            free += stop-piece
            biggest = max(biggest, stop-piece)
            pieces += 1
            node = self.words(node, 1)[0]
        return dict(free=free, biggest=biggest, pieces=pieces, start=start, size=size)

    def diagnose(self):
        """What a stuck unit was doing, for the record of a failure: where the processor is, whether it moves, whether frames and audio still arrive, and the host's condition."""
        def threads():
            out = []
            for task in Path(f'/proc/{self.process.pid}/task').glob('*'):
                try:
                    out.append(f'{(task/"comm").read_text(encoding="utf-8").strip()} {(task/"stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]} {(task/"wchan").read_text(encoding="utf-8").strip()}')
                except OSError:
                    pass
            return sorted(out)
        with self.lock:
            report = dict(frames=self.frames, audio_frames=self.audio_frames, bmc_packets=len(self.bmc_packets), first_bmc=[p.hex() for p in self.bmc_packets[:8]], process=self.process.poll())
        try:
            report['status'] = self._monitor('info status')
            report['registers'] = self._monitor('info registers')
            time.sleep(1)
            report['registers_later'] = self._monitor('info registers')
        except OSError as e:
            report['monitor_error'] = repr(e)
        with self.lock:
            report.update(frames_later=self.frames, audio_frames_later=self.audio_frames, bmc_packets_later=len(self.bmc_packets))
        report['threads'] = threads()
        report['output_tail'] = self.output_tail()
        report['host'] = {}
        if hasattr(os, 'getloadavg'):
            report['host']['load'] = os.getloadavg()
        if Path('/proc/meminfo').is_file():
            with open('/proc/meminfo', encoding='utf-8') as info:
                report['host']['available_kb'] = next(int(line.split()[1]) for line in info if line.startswith('MemAvailable'))
        return report

    def save_screen(self, path, scale=4):
        Path(path).write_bytes(frame_png(self.frame, scale))


class NativeAudioPlayer:
    """Play 48 kHz stereo signed 16-bit little-endian PCM on the emulator's audio worker."""

    def __init__(self):
        self.volume = 100
        self.muted = False
        self.error = None
        self._stop = threading.Event()
        self._backend = None
        self._prime = bytearray()
        if sys.platform == 'win32':
            self._backends = iter((_WaveOut,))
        elif sys.platform == 'darwin':
            self._backends = iter((_AudioQueue,))
        else:
            self._backends = iter((
                lambda: _LinuxAudio('pw-cat', '--playback', '--raw', '--rate', '48000',
                                    '--channels', '2', '--format', 's16', '--latency=40ms',
                                    '-P', '{"application.name":"404Lab","node.name":"404lab-preview"}', '-'),
                lambda: _LinuxAudio('pacat', '--playback', '--raw', '--rate=48000',
                                    '--channels=2', '--format=s16le'),
                lambda: _LinuxAudio('aplay', '-q', '-t', 'raw', '-f', 'S16_LE', '-r', '48000', '-c', '2', '-'),
            ))

    def level(self, pcm):
        level = 0 if self.muted else self.volume
        if level == 100:
            return pcm
        if level <= 0:
            return bytes(len(pcm))
        fmt = f'<{len(pcm)//2}h'
        return struct.pack(fmt, *(int(sample * level / 100) for sample in struct.unpack(fmt, pcm)))

    def __call__(self, pcm):
        if self.error or (self.muted and self._backend is None):
            self._prime.clear()
            return
        if self._backend is None:
            self._prime += pcm
            if len(self._prime) < _PCM_PRIME_BYTES:
                return
            pcm = bytes(self._prime)
            self._prime.clear()
        pcm = self.level(pcm)
        while not self._stop.is_set():
            try:
                if self._backend is None:
                    self._backend = next(self._backends)()
                self._backend.write(pcm, self._stop)
                return
            except StopIteration:
                self.error = 'No working audio output is available.'
                return
            except OSError:
                self.finish()

    def stop(self):
        self._stop.set()

    def finish(self):
        if self._backend is not None:
            self._backend.close()
            self._backend = None


def _retime_pcm(pcm, delta):
    """Redistribute one frame across a stereo batch without a hard splice."""
    frames = len(pcm) // PCM_FRAME_BYTES
    samples = struct.unpack(f'<{frames * 2}h', pcm)
    output_intervals = frames - 1 + delta
    result = list(samples[:2])
    for frame in range(1, output_intervals):
        source, part = divmod(frame * (frames - 1), output_intervals)
        for channel in (0, 1):
            at = source * 2 + channel
            current, following = samples[at], samples[at + 2]
            result.append(current + (following-current)*part // output_intervals)
    result.extend(samples[-2:])
    return struct.pack(f'<{len(result)}h', *result)


class _LinuxAudio:
    def __init__(self, *args):
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, bufsize=0)
        self.fd = self.process.stdin.fileno()
        os.set_blocking(self.fd, False)
        self.ready = select.poll()
        self.ready.register(self.fd, select.POLLOUT)

    def _waiting_bytes(self):
        import fcntl
        import termios

        count = bytearray(4)
        try:
            fcntl.ioctl(self.fd, termios.FIONREAD, count)
        except OSError:
            return None
        return struct.unpack('=i', count)[0]

    def write(self, pcm, stop):
        if len(pcm) == _PCM_BATCH_BYTES:
            buffered = self._waiting_bytes()
            if buffered is not None:
                # The output device and QEMU have independent clocks. Stay
                # near the prefill level with at most one frame per batch.
                if buffered < PCM_RATE * PCM_FRAME_BYTES * 40 // 1000:
                    pcm = _retime_pcm(pcm, 1)
                elif buffered > PCM_RATE * PCM_FRAME_BYTES * 90 // 1000:
                    pcm = _retime_pcm(pcm, -1)
        data = memoryview(pcm)
        while data and not stop.is_set():
            if self.process.poll() is not None:
                raise OSError('Audio player stopped.')
            try:
                data = data[os.write(self.fd, data):]
            except BlockingIOError:
                self.ready.poll(20)

    def close(self):
        self.process.kill()
        self.process.wait()
        self.process.stdin.close()


_PCM_CAPACITY = 65536


def _native_function(library, name, *parameters):
    function = getattr(library, name)
    function.argtypes = parameters
    function.restype = ctypes.c_int
    return function


def _audio_result(result):
    if result:
        raise OSError(f'Audio output failed ({result}).')


class _WaveFormat(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('format', ctypes.c_uint16), ('channels', ctypes.c_uint16),
                ('rate', ctypes.c_uint32), ('byte_rate', ctypes.c_uint32),
                ('alignment', ctypes.c_uint16), ('bits', ctypes.c_uint16), ('extra', ctypes.c_uint16)]


class _WaveHeader(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('length', ctypes.c_uint32),
                ('recorded', ctypes.c_uint32), ('user', ctypes.c_size_t),
                ('flags', ctypes.c_uint32), ('loops', ctypes.c_uint32),
                ('next', ctypes.c_void_p), ('reserved', ctypes.c_size_t)]


class _WaveOut:
    def __init__(self):
        lib = ctypes.WinDLL('winmm.dll')
        ptr, uint = ctypes.c_void_p, ctypes.c_uint
        header = ctypes.POINTER(_WaveHeader)
        self._prepare = _native_function(lib, 'waveOutPrepareHeader', ptr, header, uint)
        self._unprepare = _native_function(lib, 'waveOutUnprepareHeader', ptr, header, uint)
        self._write = _native_function(lib, 'waveOutWrite', ptr, header, uint)
        self._reset = _native_function(lib, 'waveOutReset', ptr)
        self._close = _native_function(lib, 'waveOutClose', ptr)
        wave_open = _native_function(lib, 'waveOutOpen', ctypes.POINTER(ptr), uint,
                                     ctypes.POINTER(_WaveFormat), ctypes.c_size_t, ctypes.c_size_t, uint)
        self.handle = ptr()
        self.buffers = [ctypes.create_string_buffer(_PCM_CAPACITY) for _ in range(4)]
        self.headers = [_WaveHeader(ctypes.addressof(buffer)) for buffer in self.buffers]
        self.size = ctypes.sizeof(_WaveHeader)
        _audio_result(wave_open(ctypes.byref(self.handle), 0xFFFFFFFF,
                                ctypes.byref(_WaveFormat(1, 2, 48000, 192000, 4, 16, 0)), 0, 0, 0))

    def write(self, pcm, stop):
        while not stop.is_set():
            for header in self.headers:
                if header.flags & 0x10:  # WHDR_INQUEUE
                    continue
                if header.flags & 0x02:  # WHDR_PREPARED
                    _audio_result(self._unprepare(self.handle, ctypes.byref(header), self.size))
                header.flags = 0
                header.length = len(pcm)
                ctypes.memmove(header.data, pcm, header.length)
                _audio_result(self._prepare(self.handle, ctypes.byref(header), self.size))
                _audio_result(self._write(self.handle, ctypes.byref(header), self.size))
                # Move to the next slot even if a fast driver already returned this one.
                self.headers = self.headers[1:] + self.headers[:1] if header is self.headers[0] else self.headers
                return
            stop.wait(0.005)

    def close(self):
        self._reset(self.handle)
        for header in self.headers:
            if header.flags & 0x02:
                self._unprepare(self.handle, ctypes.byref(header), self.size)
        self._close(self.handle)


class _StreamFormat(ctypes.Structure):
    _fields_ = [('rate', ctypes.c_double), ('format', ctypes.c_uint32), ('flags', ctypes.c_uint32),
                ('packet_bytes', ctypes.c_uint32), ('frames', ctypes.c_uint32),
                ('frame_bytes', ctypes.c_uint32), ('channels', ctypes.c_uint32),
                ('bits', ctypes.c_uint32), ('reserved', ctypes.c_uint32)]


class _QueueBuffer(ctypes.Structure):
    # Only the leading fields are needed. AudioQueue owns the allocation.
    _fields_ = [('capacity', ctypes.c_uint32), ('data', ctypes.c_void_p), ('size', ctypes.c_uint32)]


class _AudioQueue:
    def __init__(self):
        lib = ctypes.CDLL('/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox')
        ptr, uint = ctypes.c_void_p, ctypes.c_uint32
        buffer_ref = ctypes.POINTER(_QueueBuffer)
        callback_type = ctypes.CFUNCTYPE(None, ptr, ptr, buffer_ref)
        self.free = queue.SimpleQueue()
        self._callback = callback_type(lambda _user, _queue, buffer: self.free.put(buffer))
        self.handle = ptr()
        self.started = False
        queue_new = _native_function(lib, 'AudioQueueNewOutput', ctypes.POINTER(_StreamFormat),
                                     callback_type, ptr, ptr, ptr, uint, ctypes.POINTER(ptr))
        allocate = _native_function(lib, 'AudioQueueAllocateBuffer', ptr, uint, ctypes.POINTER(buffer_ref))
        self._enqueue = _native_function(lib, 'AudioQueueEnqueueBuffer', ptr, buffer_ref, uint, ptr)
        self._start = _native_function(lib, 'AudioQueueStart', ptr, ptr)
        self._dispose = _native_function(lib, 'AudioQueueDispose', ptr, ctypes.c_ubyte)
        fmt = _StreamFormat(48000, int.from_bytes(b'lpcm', 'big'), 12, 4, 1, 4, 2, 16, 0)
        _audio_result(queue_new(ctypes.byref(fmt), self._callback, None, None, None, 0, ctypes.byref(self.handle)))
        try:
            for _ in range(4):
                buffer = buffer_ref()
                _audio_result(allocate(self.handle, _PCM_CAPACITY, ctypes.byref(buffer)))
                self.free.put(buffer)
        except OSError:
            self.close()
            raise

    def write(self, pcm, stop):
        while not stop.is_set():
            try:
                buffer = self.free.get(timeout=0.02)
            except queue.Empty:
                continue
            ctypes.memmove(buffer.contents.data, pcm, len(pcm))
            buffer.contents.size = len(pcm)
            _audio_result(self._enqueue(self.handle, buffer, 0, None))
            if not self.started:
                _audio_result(self._start(self.handle, None))
                self.started = True
            return

    def close(self):
        self._dispose(self.handle, 1)
