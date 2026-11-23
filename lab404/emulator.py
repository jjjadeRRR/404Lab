"""Boot a whole APP1 on the DM-404 emulator, press its keys and look at its screen.

DM-404 is a separate project, built by tools/setup_dm404.sh and used as an external program. It runs the firmware on an emulated machine with
interrupts and the RTOS, so it reaches what lab404/stand.py cannot: real screens and real key handling. Two limits stay:
- It stands in for the second processor, so effects do not sound like the unit, and its timing is not the unit's.
- A run here is evidence about firmware logic, never proof that something works on a unit.

Each run gets its own blank flash and a temporary overlay on a blank drive, so runs cannot affect each other or anything of the user's.
"""
import os
import re
import socket
import struct
import subprocess
import tempfile
import threading
import time
import zlib
from pathlib import Path

DM404 = Path(os.environ.get('LAB404_DEPS', Path.home()/'lab404-deps'))/'dm-404'
DEFAULT_QEMU = DM404/'build/qemu/qemu-system-arm'
BLANK_DRIVE = DM404/'build/internal-blank.img'  # formatted once; each run writes to a temporary overlay
WIDTH, HEIGHT = 128, 64
FRAME_BYTES = WIDTH*HEIGHT//8
FLASH_SIZE = 4*1024*1024
MSG_FRAME, MSG_AUDIO, MSG_BMC = 1, 2, 3
SEND_KEY, SEND_ANALOG, SEND_BMC, SEND_ENCODER = 0x81, 0x82, 0x83, 0x84


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
    return Path(qemu).exists() and BLANK_DRIVE.exists()


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

    def __init__(self, image, qemu=DEFAULT_QEMU, extra_args=(), drive=BLANK_DRIVE):
        """drive is a formatted internal drive image, used read-only through a temporary overlay."""
        self.image, self.qemu, self.extra_args, self.drive = image, str(qemu), list(extra_args), drive
        self.audio_peak = 0
        self.frame = bytes(FRAME_BYTES)
        self.frames = 0
        self.audio_frames = 0
        self.bmc_packets = []
        self.lock = threading.Lock()

    def __enter__(self):
        if not hasattr(socket, 'AF_UNIX') or os.name == 'nt':
            raise RuntimeError('the whole-firmware emulator talks to DM-404 over unix sockets and is set up on Linux only. '
                                'On Windows run it inside WSL; see docs/STAND.md. Every other tool works here')
        self.dir = tempfile.TemporaryDirectory(prefix='lab404-unit-')
        root = Path(self.dir.name)
        (root/'APP1.bin').write_bytes(self.image)
        (root/'flash.bin').write_bytes(b'\xFF'*FLASH_SIZE)
        link_path = root/'link.sock'
        self.monitor_path = root/'monitor.sock'
        # A file, not a pipe: nobody reads a pipe while the machine runs, and when one filled the emulated processor stopped dead. A boot writes about 20 KB [EMULATOR].
        self.output_path = root/'output.log'
        with self.output_path.open('wb') as output:
            self.process = subprocess.Popen(
                [self.qemu, '-M', f'sp404mk2,flash={root/"flash.bin"},link=link', '-bios', str(root/'APP1.bin'),
                 '-chardev', f'socket,id=link,path={link_path},server=on,wait=on',
                 '-drive', 'if=sd,index=0',  # the SD slot, empty
                 '-drive', f'if=sd,index=1,format=raw,snapshot=on,file={self.drive}',
                 '-nographic', '-monitor', f'unix:{self.monitor_path},server,nowait', '-serial', 'none', *self.extra_args],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=output)
        self.sock = socket.socket(socket.AF_UNIX)
        for _ in range(100):
            try:
                self.sock.connect(str(link_path))
                break
            except OSError:
                if self.process.poll() is not None:
                    raise RuntimeError('emulator exited: '+self.output_tail()) from None
                time.sleep(0.1)
        else:
            self.process.kill()
            raise RuntimeError('emulator did not open its link')
        threading.Thread(target=self._reader, daemon=True).start()
        return self

    def __exit__(self, *_):
        self.process.kill()
        self.process.wait()
        self.sock.close()
        self.dir.cleanup()

    def output_tail(self, size=500):
        """The last things the machine said."""
        return self.output_path.read_bytes()[-size:].decode(errors='replace')

    def _reader(self):
        buffer = b''
        while True:
            try:
                data = self.sock.recv(65536)
            except OSError:
                return
            if not data:
                return
            buffer += data
            while len(buffer) >= 4:
                kind, _, size = struct.unpack_from('<BBH', buffer)
                if len(buffer) < 4+size:
                    break
                payload, buffer = buffer[4:4+size], buffer[4+size:]
                with self.lock:
                    if kind == MSG_FRAME:
                        self.frame = payload
                        self.frames += 1
                    elif kind == MSG_AUDIO:
                        self.audio_frames += size//4
                        samples = struct.unpack(f'<{size//2}h', payload[:size & ~1])
                        self.audio_peak = max(self.audio_peak, max(map(abs, samples), default=0))
                    elif kind == MSG_BMC:
                        self.bmc_packets.append(payload)

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

    def read_u32(self, address):
        """A word of the running firmware's memory, through the emulator's monitor. Raises RuntimeError if it cannot be read within two seconds."""
        data = b''
        end = time.monotonic()+2
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(1)
            s.connect(str(self.monitor_path))
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
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(1)
            s.connect(str(self.monitor_path))
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
        report['host'] = dict(load=os.getloadavg(), available_kb=next(int(line.split()[1]) for line in open('/proc/meminfo', encoding='utf-8') if line.startswith('MemAvailable')))
        return report

    def save_screen(self, path, scale=4):
        Path(path).write_bytes(frame_png(self.frame, scale))
