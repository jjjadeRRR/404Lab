"""Native Tk preview of APP1 on DM-404. Importing this module needs no display."""
import ctypes
import json
import math
import os
import signal
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from xml.etree import ElementTree as ET

from .emulator import (FRAME_BYTES, HEIGHT, KEY_LEDS, KNOBS, WIDTH, Emulator,
                       NativeAudioPlayer, check_project_source, find_blank_drive,
                       find_fx, find_qemu, pick_linux_path, prepare_project_media)
from .identify import identify
from .image import APP1_ROOM, FLASH, scatter


MODIFIERS = {'SHIFT', 'REMAIN', 'HOLD', 'MARK', 'COPY', 'DEL', 'REVERSE', 'ROLL',
             'BUS FX', 'VALUE', 'RECORD SETTING'}
LATCH_MODES = ('Off', 'One-shot', 'Lock')
PAD_KEYS = '1234qwerasdfzxcv'
KEYMAP = {
    **{key: f'PAD{n}' for n, key in enumerate(PAD_KEYS, 1)},
    'Shift_L': 'SHIFT', 'Shift_R': 'SHIFT', 'Tab': 'REMAIN', 'space': 'SUB PAD',
    'Escape': 'EXIT', 'Return': 'VALUE', 'h': 'HOLD', 'j': 'ROLL', 'k': 'MARK',
    'l': 'LOOP', 'n': 'REVERSE', 'b': 'BUS FX', 'm': 'MFX', 'u': 'COPY',
    'i': 'DEL', 'BackSpace': 'DEL', 'Delete': 'DEL', 'o': 'REC', 'p': 'RESAMPLE',
    'y': 'RECORD SETTING', 't': 'PATTERN SELECT', 'g': 'PATTERN EDIT',
    **dict(zip('56789', ('BANK A/F', 'BANK B/G', 'BANK C/H', 'BANK D/I', 'BANK E/J'))),
}
TURNS = dict.fromkeys(('Up', 'Right', 'bracketright'), 1) | dict.fromkeys(('Down', 'Left', 'bracketleft'), -1)
# Shift modifies the keysym on the number row and the bracket keys.
SHIFTED_KEYS = dict(zip(('exclam', 'at', 'numbersign', 'dollar', 'percent', 'asciicircum',
                         'ampersand', 'asterisk', 'parenleft'), '123456789'))
SHIFTED_KEYS.update(ISO_Left_Tab='Tab', braceleft='bracketleft', braceright='bracketright')

# Printable keys are mapped by physical position so switching languages does
# not move the pad grid or move a shortcut onto one of its pads.
PC_KEYS = {code: key for first, row in ((2, '123456789'), (16, 'qwertyuiop'),
                                       (30, 'asdfghjkl'), (44, 'zxcvbnm'))
           for code, key in enumerate(row, first)}
PC_KEYS[26], PC_KEYS[27] = 'bracketleft', 'bracketright'
X11_KEYS = {code+8: key for code, key in PC_KEYS.items()}  # XKB evdev codes
MAC_KEYS = {
    **dict(zip((18, 19, 20, 21, 23, 22, 26, 28, 25), '123456789')),
    **dict(zip((12, 13, 14, 15, 17, 16, 32, 34, 31, 35), 'qwertyuiop')),
    **dict(zip((0, 1, 2, 3, 5, 4, 38, 40, 37), 'asdfghjkl')),
    **dict(zip((6, 7, 8, 9, 11, 45, 46), 'zxcvbnm')),
    33: 'bracketleft', 30: 'bracketright',
}


def _windows_scan_code():
    # Tk reports wParam (the layout's virtual key) on Windows.
    user32 = ctypes.WinDLL('user32')
    layout = user32.GetKeyboardLayout
    layout.argtypes = [ctypes.c_uint]
    layout.restype = ctypes.c_void_p
    scan = user32.MapVirtualKeyExW
    scan.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    scan.restype = ctypes.c_uint
    return lambda keycode: scan(keycode, 4, layout(0)) or (0x10000 | keycode)


# Proportions adapted from the SP-404MKII front panel, scaled to 496 x 696 so
# every primary cap label and SHIFT silkscreen sub-label fits without clipping.
# Each tuple is kind, center X/Y, width and height.
PANEL_WIDTH, PANEL_HEIGHT = 496, 696
PANEL_LAYOUT = {
    'VOLUME': ('knob', 80.0, 50.0, 44.0, 44.0),
    'CTRL1': ('knob', 190.0, 50.0, 44.0, 44.0),
    'CTRL2': ('knob', 306.0, 50.0, 44.0, 44.0),
    'CTRL3': ('knob', 416.0, 50.0, 44.0, 44.0),
    'OLED': ('oled', 248.0, 184.0, 128.0, 64.0),
    'FILTER+DRIVE': ('key', 88.0, 136.0, 102.0, 34.0),
    'RESONATOR': ('key', 80.0, 184.0, 102.0, 34.0),
    'DELAY': ('key', 88.0, 232.0, 102.0, 34.0),
    'ISOLATOR': ('key', 408.0, 136.0, 102.0, 34.0),
    'DJFX LOOPER': ('key', 416.0, 184.0, 102.0, 34.0),
    'MFX': ('key', 408.0, 232.0, 102.0, 34.0),
    'VALUE': ('value', 442.0, 288.0, 40.0, 40.0),
    'PATTERN SELECT': ('key', 51.0, 288.0, 54.0, 28.0),
    'PATTERN EDIT': ('key', 114.0, 288.0, 54.0, 28.0),
    'RECORD SETTING': ('key', 177.0, 288.0, 54.0, 28.0),
    'START/END': ('key', 246.0, 288.0, 54.0, 28.0),
    'PITCH/SPEED': ('key', 309.0, 288.0, 54.0, 28.0),
    'MARK': ('key', 372.0, 288.0, 54.0, 28.0),
    'DEL': ('key', 51.0, 340.0, 54.0, 28.0),
    'REC': ('key', 114.0, 340.0, 54.0, 28.0),
    'RESAMPLE': ('key', 177.0, 340.0, 54.0, 28.0),
    'BPM SYNC': ('key', 242.0, 340.0, 45.0, 28.0),
    'GATE': ('key', 294.0, 340.0, 45.0, 28.0),
    'LOOP': ('key', 346.0, 340.0, 45.0, 28.0),
    'REVERSE': ('key', 398.0, 340.0, 45.0, 28.0),
    'ROLL': ('key', 450.0, 340.0, 45.0, 28.0),
    'EXIT': ('key', 51.0, 392.0, 54.0, 28.0),
    'COPY': ('key', 114.0, 392.0, 54.0, 28.0),
    'REMAIN': ('key', 177.0, 392.0, 54.0, 28.0),
    'BANK A/F': ('key', 238.0, 392.0, 37.0, 28.0),
    'BANK B/G': ('key', 281.0, 392.0, 37.0, 28.0),
    'BANK C/H': ('key', 324.0, 392.0, 37.0, 28.0),
    'BANK D/I': ('key', 367.0, 392.0, 37.0, 28.0),
    'BANK E/J': ('key', 410.0, 392.0, 37.0, 28.0),
    'SHIFT': ('key', 453.0, 392.0, 37.0, 28.0),
    'PAD1': ('pad', 60.0, 464.0, 72.0, 42.0),
    'PAD2': ('pad', 148.0, 464.0, 72.0, 42.0),
    'PAD3': ('pad', 236.0, 464.0, 72.0, 42.0),
    'PAD4': ('pad', 324.0, 464.0, 72.0, 42.0),
    'BUS FX': ('key', 436.0, 464.0, 72.0, 42.0),
    'PAD5': ('pad', 60.0, 522.0, 72.0, 42.0),
    'PAD6': ('pad', 148.0, 522.0, 72.0, 42.0),
    'PAD7': ('pad', 236.0, 522.0, 72.0, 42.0),
    'PAD8': ('pad', 324.0, 522.0, 72.0, 42.0),
    'HOLD': ('key', 436.0, 522.0, 72.0, 42.0),
    'PAD9': ('pad', 60.0, 580.0, 72.0, 42.0),
    'PAD10': ('pad', 148.0, 580.0, 72.0, 42.0),
    'PAD11': ('pad', 236.0, 580.0, 72.0, 42.0),
    'PAD12': ('pad', 324.0, 580.0, 72.0, 42.0),
    'EXT SOURCE': ('key', 436.0, 580.0, 72.0, 42.0),
    'PAD13': ('pad', 60.0, 638.0, 72.0, 42.0),
    'PAD14': ('pad', 148.0, 638.0, 72.0, 42.0),
    'PAD15': ('pad', 236.0, 638.0, 72.0, 42.0),
    'PAD16': ('pad', 324.0, 638.0, 72.0, 42.0),
    'SUB PAD': ('key', 436.0, 638.0, 72.0, 42.0),
}

# Hardware silkscreen secondary labels (SHIFT and control parameters) printed below controls.
SUB_LABELS = {
    'CTRL1': 'CUTOFF', 'CTRL2': 'RESONANCE', 'CTRL3': 'DRIVE',
    'PATTERN SELECT': 'UNDO', 'START/END': 'CHOP', 'PITCH/SPEED': 'ENVELOPE',
    'LOOP': 'PING-PONG', 'ROLL': 'ROLL SET', 'EXIT': 'PATTERN STOP', 'REMAIN': 'CURRENT PAD',
    'BUS FX': 'MUTE BUS', 'HOLD': 'PAUSE', 'EXT SOURCE': 'INPUT SETTING', 'SUB PAD': 'PROJECT',
    'PAD1': 'FIXED VELOCITY', 'PAD2': '16 VELOCITY', 'PAD3': 'CUE', 'PAD4': 'CHROMATIC',
    'PAD5': 'EXCHANGE', 'PAD6': 'INIT PARAM', 'PAD7': 'PAD LINK', 'PAD8': 'MUTE GROUPS',
    'PAD9': 'METRONOME', 'PAD10': 'COUNT-IN', 'PAD11': 'TAP TEMPO', 'PAD12': 'GAIN',
    'PAD13': 'UTILITY', 'PAD14': 'IMPORT/EXPORT', 'PAD15': 'PAD SETTING', 'PAD16': 'EFX SETTING',
}

BG = '#0F1116'
CASE = '#171A21'
WELL = '#0D0F14'
CONTROL = '#242934'
EDGE = '#3A4150'
LIGHT = '#EEF2FA'
MUTED_TEXT = '#94A0B5'
SILK = '#8F9BB0'
ACCENT = '#E8743B'
BLACK = '#05070B'
AMBER = '#FFCB73'
BLUE = '#9AD8FF'


def _ui_font(root=None):
    if root is not None:
        try:
            from tkinter import font as tkfont
            families = set(tkfont.families(root))
            for candidate in ('SF Pro Text', 'Segoe UI', 'Noto Sans', 'Adwaita Sans', 'Liberation Sans', 'DejaVu Sans'):
                if candidate in families:
                    return candidate
        except Exception:
            pass
    return 'TkDefaultFont'


def label_for(name):
    if name.startswith('PAD') and name[3:].isdigit():
        return f'PAD {name[3:]}'
    if name in KNOBS:
        return f'CTRL {name[-1]}'
    return name


class ControlState:
    """Combine physical contacts, latches and timed holds into firmware button edges."""

    def __init__(self, send):
        self.send = send
        self.physical = {}
        self.latched = {}
        self.timed = {}
        self.mode = 'Off'
        self._chord = None

    @property
    def active(self):
        return self.physical.keys() | self.latched.keys() | self.timed.keys()

    def _edge(self, name, was_down):
        down = name in self.active
        if down == was_down:
            return
        self.send(name, down)
        if down and name not in MODIFIERS and self._chord is None and 'One-shot' in self.latched.values():
            self._chord = name
        elif not down and self._chord == name:
            self._chord = None
            for modifier in tuple(self.latched):
                if self.latched[modifier] == 'One-shot':
                    self.toggle_latch(modifier)

    def press(self, name, source):
        was_down = name in self.active
        self.physical.setdefault(name, set()).add(source)
        self._edge(name, was_down)

    def release(self, name, source):
        if name not in self.physical:
            return
        self.physical[name].discard(source)
        if not self.physical[name]:
            del self.physical[name]
            self._edge(name, True)

    def mouse_press(self, name):
        if name in self.latched or (self.mode != 'Off' and name in MODIFIERS):
            self.toggle_latch(name, self.mode)
        else:
            self.press(name, 'mouse')

    def toggle_latch(self, name, mode='Lock'):
        was_down = name in self.active
        if name in self.latched:
            del self.latched[name]
        else:
            self.latched[name] = mode
        self._edge(name, was_down)

    def release_all(self):
        for name in tuple(self.latched):
            if name in self.latched:
                self.toggle_latch(name)

    def timed_hold(self, name, now):
        if name not in self.timed:
            was_down = name in self.active
            self.timed[name] = now + 3.2
            self._edge(name, was_down)

    def expire(self, now):
        for name, deadline in tuple(self.timed.items()):
            if now >= deadline:
                del self.timed[name]
                self._edge(name, True)

    def clear_physical(self):
        for name in tuple(self.physical):
            del self.physical[name]
            self._edge(name, True)

    def reset(self):
        active = self.active
        self._chord = None
        self.physical.clear()
        self.latched.clear()
        self.timed.clear()
        for name in sorted(active, key=lambda name: name in MODIFIERS):
            self.send(name, False)


class KeyboardState:
    """Keep one contact per physical key, including both Shift keys."""

    def __init__(self, controls, turn, cycle, release_all, *, positions=None):
        self.controls = controls
        self.turn, self.cycle, self.release_all = turn, cycle, release_all
        self.down = {}
        self.pending = {}
        self.positions = positions or {}

    def symbol(self, keycode, keysym):
        key = self.positions.get(keycode, SHIFTED_KEYS.get(keysym, keysym))
        return key.lower() if len(key) == 1 else key

    def press(self, keycode, keysym, stamp):
        if keycode in self.pending and self.pending[keycode] == stamp:
            del self.pending[keycode]
            return True
        self.flush()
        if keycode in self.down:
            return True
        key = self.symbol(keycode, keysym)
        name = KEYMAP.get(key)
        if name:
            self.controls.press(name, ('key', keycode))
        elif key in TURNS:
            self.turn(TURNS[key])
        elif key == 'F2':
            self.cycle()
        elif key == 'F3':
            self.release_all()
        else:
            return False
        self.down[keycode] = name
        return True

    def defer_release(self, keycode, stamp):
        if keycode in self.down:
            self.pending[keycode] = stamp
            return True
        return False

    def release(self, keycode):
        if keycode not in self.down:
            return False
        name = self.down.pop(keycode)
        if name:
            self.controls.release(name, ('key', keycode))
        return True

    def flush(self):
        for keycode in self.pending:
            self.release(keycode)
        self.pending.clear()

    def clear(self):
        self.down.clear()
        self.pending.clear()
        self.controls.clear_physical()


def _box(x, y, w, h):
    return x-w/2, y-h/2, x+w/2, y+h/2


def _knob_marker(x, y, width, angle):
    inner, outer = width/2-12, width/2-4
    dx, dy = math.sin(angle), -math.cos(angle)
    return x+dx*inner, y+dy*inner, x+dx*outer, y+dy*outer


def _key_label(name):
    if name.startswith('BANK '):
        return name[5:]
    return {'PATTERN SELECT': 'PATTERN\nSELECT', 'PATTERN EDIT': 'PATTERN\nEDIT',
            'RECORD SETTING': 'RECORD\nSETTING', 'START/END': 'START/\nEND', 'PITCH/SPEED': 'PITCH/\nSPEED',
            'BPM SYNC': 'BPM\nSYNC', 'EXT SOURCE': 'EXT\nSOURCE',
            'DJFX LOOPER': 'DJFX\nLOOPER', 'FILTER+DRIVE': 'FILTER+\nDRIVE'}.get(name, name)


FX_TOP, FX_BOTTOM, PADS_TOP = 108, 262, 430


def _knob_ticks(x, y, width):
    radius = width / 2 + 5
    for step in range(9):
        angle = math.radians(-135 + step * 33.75)
        dx, dy = math.sin(angle), -math.cos(angle)
        inner, outer = radius, radius + (3 if step in (0, 4, 8) else 2)
        yield x + dx * inner, y + dy * inner, x + dx * outer, y + dy * outer


def _panel_shapes():
    """Shared vector primitives for the live Canvas and the neutral SVG."""
    yield '', 'body', 'rect', (0, 0, PANEL_WIDTH, PANEL_HEIGHT), CASE, EDGE, ''
    yield '', 'accent', 'line', (28, 12, 468, 12), ACCENT, '', ''
    for y in (FX_TOP, FX_BOTTOM, PADS_TOP):
        yield '', 'divider', 'line', (28, y, 468, y), '#272C37', '', ''
    for name, (kind, x, y, w, h) in PANEL_LAYOUT.items():
        if kind == 'oled':
            yield name, 'bezel', 'rect', _box(x, y, w+16, h+16), WELL, EDGE, ''
            yield name, 'cap', 'rect', _box(x, y, w, h), BLACK, '#2A3140', ''
            continue
        if kind in ('knob', 'value'):
            if kind == 'knob':
                for coords in _knob_ticks(x, y, w):
                    yield '', 'tick', 'line', coords, '#4C5568', '', ''
            yield name, 'rim', 'oval', _box(x, y, w+8, h+8), WELL, '#2B313E', ''
            yield name, 'cap', 'oval', _box(x, y, w, h), CONTROL, EDGE, ''
            angle = math.radians(135) if name == 'VOLUME' else 0
            yield name, 'marker', 'line', _knob_marker(x, y, w, angle), LIGHT, '', ''
            label_y = y + h/2 + 11
            yield name, 'label', 'text', (x, label_y, 9 if name == 'VALUE' else 10), LIGHT, '', label_for(name)
            if name == 'VOLUME':
                yield '', 'sub', 'text', (x-24, y+h/2+23, 7), SILK, '', 'MIN'
                yield name, 'percent', 'text', (x, y+h/2+23, 8), MUTED_TEXT, '', '100%'
                yield '', 'sub', 'text', (x+24, y+h/2+23, 7), SILK, '', 'MAX'
            elif name in SUB_LABELS:
                yield '', 'sub', 'text', (x, y+h/2+23, 8), SILK, '', SUB_LABELS[name]
            continue
        yield '', 'well', 'rect', _box(x, y, w+4, h+4), WELL, '', ''
        yield name, 'cap', 'rect', _box(x, y, w, h), CONTROL, EDGE, ''
        if kind == 'pad':
            yield name, 'light', 'rect', _box(x, y, w-8, h-8), CONTROL, '', ''
            yield name, 'label', 'text', (x, y, 16), LIGHT, '', name[3:]
            if name in SUB_LABELS:
                yield '', 'sub', 'text', (x, y+h/2+9, 8), SILK, '', SUB_LABELS[name]
        else:
            led_color = '#5C3A2B' if name == 'SHIFT' else '#383F4D'
            yield name, 'light', 'rect', _box(x, y-h/2+4, min(w-12, 22), 2.5), led_color, '', ''
            size = (7 if name in ('PATTERN SELECT', 'PATTERN EDIT', 'RECORD SETTING',
                                  'BPM SYNC', 'RESAMPLE', 'RESONATOR', 'REVERSE', 'SHIFT') else 8.5)
            yield name, 'label', 'text', (x, y+2, size), LIGHT, '', _key_label(name)
            if name in SUB_LABELS:
                yield '', 'sub', 'text', (x, y+h/2+9, 7), SILK, '', SUB_LABELS[name]
    yield '', 'bracket', 'line', (220, 414, 286, 414), '#3A4252', '', ''
    yield '', 'bracket', 'line', (362, 414, 428, 414), '#3A4252', '', ''
    yield '', 'sub', 'text', (324, 414, 7), SILK, '', 'BANK VOLUME'


def panel_svg():
    """Return the standalone English SVG used in the stand documentation."""
    svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg',
                             'viewBox': f'0 0 {PANEL_WIDTH} {PANEL_HEIGHT}'})
    ET.SubElement(svg, 'title').text = '404Lab emulator control panel'
    for name, role, shape, coords, fill, outline, copy in _panel_shapes():
        if shape in ('rect', 'oval'):
            x1, y1, x2, y2 = coords
            if shape == 'rect':
                values = dict(x=x1, y=y1, width=x2-x1, height=y2-y1)
            else:
                shape = 'ellipse'
                values = dict(cx=(x1+x2)/2, cy=(y1+y2)/2, rx=(x2-x1)/2, ry=(y2-y1)/2)
        elif shape == 'line':
            values = dict(zip(('x1', 'y1', 'x2', 'y2'), coords))
            outline, fill = fill, 'none'
        else:
            x, y, size = coords
            values = dict(x=x, y=y, **{'font-size': size})
        element = ET.SubElement(svg, shape, {key: f'{value:.2f}' for key, value in values.items()})
        element.set('fill', fill)
        if outline:
            element.set('stroke', outline)
        if role == 'cap':
            element.set('data-control', name)
            ET.SubElement(element, 'title').text = label_for(name)
        if shape == 'text':
            element.set('font-family', 'SF Pro Text, Segoe UI, Noto Sans, system-ui, sans-serif')
            element.set('font-weight', '500' if role == 'sub' else '600')
            element.set('text-anchor', 'middle')
            element.set('dominant-baseline', 'central')
            lines = copy.splitlines()
            for index, line in enumerate(lines):
                position = y + (index - (len(lines)-1)/2) * (size+1)
                ET.SubElement(element, 'tspan', x=f'{x:.2f}', y=f'{position:.2f}').text = line
    ET.indent(svg)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(svg, encoding='unicode') + '\n'


_DARK_RGB = bytes.fromhex(BLACK[1:])
_LIGHT_RGB = bytes.fromhex(LIGHT[1:])
_PIXELS = tuple(b''.join(_LIGHT_RGB if byte & (128 >> bit) else _DARK_RGB for bit in range(8))
                for byte in range(256))


def _ppm(frame):
    return f'P6\n{WIDTH} {HEIGHT}\n255\n'.encode('ascii') + b''.join(_PIXELS[byte] for byte in frame)


def _session_path():
    home = Path.home()
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA') or home/'AppData/Local')/'404Lab/session.json'
    if sys.platform == 'darwin':
        return home/'Library/Application Support/404Lab/session.json'
    state = Path(os.environ.get('XDG_STATE_HOME', ''))
    if not state.is_absolute():
        state = home/'.local/state'
    return state/'404lab/session.json'


def _read_session(path):
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(saved, dict):
        return {}
    return {key: saved[key] for key in ('app1', 'project')
            if isinstance(saved.get(key), str) and saved[key] and '\0' not in saved[key]}


def _startup_sources(state, app1, project):
    saved = _read_session(state)
    if project is None and saved.get('project'):
        remembered = Path(saved['project'])
        project = remembered if remembered.exists() else None
    if app1 is None and saved.get('app1'):
        remembered = Path(saved['app1'])
        app1 = remembered if remembered.is_file() else None
    return Path(app1) if app1 else None, Path(project) if project else None


def _remember_session(path, app1, project):
    saved = _read_session(path)
    saved['app1'] = str(app1.absolute())
    if project is not None:
        saved['project'] = str(project.absolute())
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
            pending = Path(output.name)
            json.dump(saved, output, ensure_ascii=False)
        pending.replace(path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def _load_app1(app1):
    if not app1.is_file():
        raise ValueError('Choose a regular SP404MKII_APP1.bin firmware file.')
    with app1.open('rb') as file:
        image = file.read(APP1_ROOM + 1)
    if len(image) > APP1_ROOM:
        raise ValueError('The file exceeds the SP-404MKII APP1 flash region.')
    # DM-404 takes the initial stack and reset vector from this offset.
    vector_offset = 0x6EC
    if len(image) < vector_offset + 8:
        raise ValueError('The file is missing the SP-404MKII APP1 boot vectors.')
    stack, reset = struct.unpack_from('<II', image, vector_offset)
    if stack % 4 or not (0x20000000 < stack <= 0x20080000 or 0x20200000 < stack <= 0x20300000
                         or 0x80000000 < stack <= 0x84000000):
        raise ValueError('Invalid initial stack in the SP-404MKII APP1 boot vectors.')
    if not reset & 1 or not FLASH <= (reset & ~1) < FLASH + len(image):
        raise ValueError('Invalid reset address in the SP-404MKII APP1 boot vectors.')
    if sum(size for _, _, size, _ in scatter(image)) > 64 * 1024 * 1024:
        raise ValueError('APP1 startup regions exceed emulated memory.')
    info = identify(image)
    if info['status'] == 'invalid':
        raise ValueError(f'Choose a usable APP1 firmware image. {info["structure"]}')
    return image, info


def _boot(app1, project, player, cancel):
    if app1 is None:
        with TemporaryDirectory(prefix='lab404-project-') as scratch:
            check_project_source(project, scratch, cancel=cancel)
        return None, None, None
    image, info = _load_app1(app1)
    qemu = find_qemu()
    if not qemu.is_file():
        raise RuntimeError('DM-404 QEMU was not found. Run lab404 doctor for setup instructions.')
    temp = TemporaryDirectory(prefix='lab404-project-') if project else None
    try:
        media = prepare_project_media(project, temp.name, cancel=cancel) if project else None
        drive = (media.drive if media else None) or find_blank_drive()
        if not drive.is_file():
            raise RuntimeError('No internal drive image. Open DM-404 once to create one.')
        if cancel.is_set():
            raise RuntimeError('Emulator start cancelled.')
        unit = Emulator(image, qemu=qemu, drive=drive, sd_card=media.sd_card if media else None,
                        audio_sink=player, cancel=cancel, fx=find_fx(qemu))
        unit.__enter__()
    except BaseException:
        if temp:
            temp.cleanup()
        raise
    firmware = f'{info["family"]} {info["version"]}' if info['family'] else app1.name
    if info['status'] == 'unknown':
        firmware += ' (unidentified)'
    return unit, temp, f'{firmware} {info["sha256"][:8]}'


class PreviewWindow:
    def __init__(self, tk, ttk, filedialog, root, no_audio, *, state_path=None):
        self.tk, self.ttk, self.dialog, self.root = tk, ttk, filedialog, root
        self.state_path = state_path
        self.closing = threading.Event()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lab404-gui')
        self.unit = self.media = self.player = self.job = self.picker = None
        self.app1 = self.project = None
        self.firmware = 'No APP1 loaded'
        self.project_message = 'No project loaded — click Import Project to test your own samples'
        self.notice = self.project_message
        self.volume, self.muted = 100, no_audio
        self.knobs = dict.fromkeys(KNOBS, 2048)
        self.detent = 0
        self.last_frame = self.mini_image = None
        self.mouse = self.drag = None
        self.key_timer = None
        self.hold_timer = None
        self.help = None
        self.palette = {}
        self.controls = ControlState(self._contact)
        self.windowing = root.tk.call('tk', 'windowingsystem')
        positions = {'x11': X11_KEYS, 'win32': PC_KEYS, 'aqua': MAC_KEYS}.get(self.windowing)
        self.keyboard = KeyboardState(self.controls, self._turn, self._cycle, self.controls.release_all,
                                      positions=positions)
        self.windows_scan = _windows_scan_code() if self.windowing == 'win32' else None
        self.font_family = _ui_font(root)
        self._widgets()
        self._bind()
        self._refresh_frame(bytes(FRAME_BYTES))
        self._update_inputs(time.monotonic())
        root.update_idletasks()
        width, height = root.winfo_reqwidth(), root.winfo_reqheight()
        root.minsize(width, height)
        root.geometry(f'{width}x{height}')
        self.root.after(30, self._tick)

    def _widgets(self):
        tk, ttk, root = self.tk, self.ttk, self.root
        root.title('404Lab — APP1 Preview')
        root.configure(background=BG)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(2, weight=1)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Preview.TButton', background=CONTROL, foreground=LIGHT, bordercolor=EDGE,
                        lightcolor=CONTROL, darkcolor=CONTROL, focuscolor=BLUE,
                        font=(self.font_family, 9), padding=(10, 5))
        style.map('Preview.TButton', background=[('pressed', '#343C4A'), ('active', '#2D3544')],
                  foreground=[('disabled', '#748093')])
        style.configure('Primary.Preview.TButton', font=(self.font_family, 9, 'bold'), padding=(12, 7))

        display_outer = tk.Frame(root, background='#262C39', padx=1, pady=1)
        display_outer.grid(row=0, column=1, padx=16, pady=(12, 6))
        display = tk.Frame(display_outer, background='#0B0D12', padx=6, pady=6)
        display.pack()
        self.display = tk.Label(display, background=BLACK, borderwidth=0, padx=0, pady=0, highlightthickness=0)
        self.display.pack()

        status = tk.Frame(root, background='#161A22', highlightbackground='#262C39',
                          highlightthickness=1, padx=12, pady=8)
        status.grid(row=1, column=1, sticky='ew', padx=16, pady=(2, 8))
        status.grid_columnconfigure(0, weight=1, uniform='status')
        status.grid_columnconfigure(1, weight=1, uniform='status')
        self.pressed = self._label(status, '', background='#161A22', foreground=BLUE, wraplength=240)
        self.pressed.grid(row=0, column=0, sticky='ew')
        self.latched = self._label(status, '', background='#161A22', foreground=AMBER, wraplength=240)
        self.latched.grid(row=1, column=0, sticky='ew', pady=(2, 0))
        self.status = self._label(status, self.firmware, background='#161A22', foreground=LIGHT,
                                  font=(self.font_family, 9, 'bold'),
                                  justify='right', anchor='e', wraplength=240)
        self.status.grid(row=0, column=1, rowspan=2, sticky='ew')

        self.panel = tk.Canvas(root, bg=BG, borderwidth=0, highlightthickness=0,
                               takefocus=True, width=PANEL_WIDTH, height=math.ceil(PANEL_HEIGHT)+1)
        self.panel.grid(row=0, column=0, rowspan=4, padx=(14, 10), pady=10)
        self._draw_panel()

        footer = tk.Frame(root, background=BG)
        footer.grid(row=3, column=1, sticky='ew', padx=16, pady=(8, 10))
        primary = tk.Frame(footer, background=BG)
        primary.pack(fill='x')
        specifications = (('Restart', self._restart), ('Import Project', self._import), ('Load APP1', self._load))
        for i, (label, command) in enumerate(specifications):
            primary.grid_columnconfigure(i, weight=1, uniform='primary')
            btn = ttk.Button(primary, text=label, command=command, style='Primary.Preview.TButton')
            btn.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 4, 0))
            if label == 'Restart':
                self.restart = btn
                btn.state(['disabled'])
            elif label == 'Import Project':
                self.import_button = btn
            else:
                self.load_button = btn
        secondary = tk.Frame(footer, background=BG)
        secondary.pack(fill='x', pady=(5, 0))
        for i, (label, command) in enumerate((
                ('Latch: Off', self._cycle), ('Release All', self.controls.release_all),
                (self._audio_label(), self._toggle_audio), ('? Keys', self._show_keys))):
            secondary.grid_columnconfigure(i, weight=1)
            btn = ttk.Button(secondary, text=label, command=command, style='Preview.TButton')
            btn.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 4, 0))
            if i == 0:
                self.latch_button = btn
            elif i == 2:
                self.audio_button = btn
        self.notice_label = self._label(status, self.notice, background='#161A22', wraplength=490)
        self.notice_label.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(4, 0))

    def _label(self, parent, text, **options):
        style = dict(background=BG, foreground=MUTED_TEXT, font=(self.font_family, 9), anchor='w', justify='left')
        return self.tk.Label(parent, text=text, **(style | options))

    def _draw_panel(self):
        canvas = self.panel
        canvas.delete('panel')
        self.items = {}
        self.hit_boxes = {}
        self.palette.clear()
        primitives = {'rect': canvas.create_rectangle, 'oval': canvas.create_oval,
                      'line': canvas.create_line, 'text': canvas.create_text}
        for name, role, shape, coords, fill, outline, copy in _panel_shapes():
            options = {'fill': fill, 'tags': ('panel',)}
            if shape in ('rect', 'oval'):
                options['outline'] = outline
            if shape == 'text':
                x, y, size = coords
                coords = x, y
                weight = 'normal' if role == 'sub' else 'bold'
                options.update(text=copy, justify='center', font=(self.font_family, -round(size), weight))
            self.items[name, role] = primitives[shape](*coords, **options)
            if role == 'cap' and name != 'OLED':
                self.hit_boxes[name] = coords
        _, x, y, _, _ = PANEL_LAYOUT['OLED']
        self.mini = canvas.create_image(round(x), round(y), image=self.mini_image, tags=('panel',))
        for name in (*KNOBS, 'VOLUME', 'VALUE'):
            self._draw_knob(name)

    def _bind(self):
        panel, root = self.panel, self.root
        right, middle = (2, 3) if self.windowing == 'aqua' else (3, 2)
        panel.bind('<ButtonPress-1>', self._left)
        panel.bind('<Control-ButtonPress-1>', lambda event: self._special_click(event, timed=True))
        panel.bind(f'<ButtonPress-{right}>', self._special_click)
        panel.bind(f'<ButtonPress-{middle}>', lambda event: self._special_click(event, timed=True))
        panel.bind('<Double-ButtonPress-1>', self._double)
        panel.bind('<B1-Motion>', self._motion)
        panel.bind('<ButtonRelease-1>', self._left_up)
        panel.bind('<MouseWheel>', self._wheel)
        if self.windowing == 'x11':
            panel.bind('<Button-4>', lambda event: self._wheel(event, 1))
            panel.bind('<Button-5>', lambda event: self._wheel(event, -1))
        # Put the window's input bindings first so Tab cannot move focus away
        # when it is a REMAIN contact, even if a toolbar button has focus.
        self.input_tag = 'Lab404Input'
        root.bind_class(self.input_tag, '<KeyPress>', self._key_down)
        root.bind_class(self.input_tag, '<KeyRelease>', self._key_up)
        for widget in (root, *self._descendants(root)):
            widget.bindtags((self.input_tag, *widget.bindtags()))
        root.bind('<FocusOut>', self._focus_out)
        root.protocol('WM_DELETE_WINDOW', self.close)
        panel.focus_set()

    def _descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._descendants(child)

    def _focus_out(self, _event):
        self.root.after_idle(self._release_unfocused)

    def _release_unfocused(self):
        widget = self.root.focus_get()
        if widget is None or widget.winfo_toplevel() != self.root:
            self.mouse = self.drag = None
            self.keyboard.clear()

    def _keycode(self, event):
        if event.keysym in ('Shift_L', 'Shift_R'):
            return event.keysym
        if self.windowing == 'aqua':
            # Tk Aqua packs the physical key in the high byte, above the
            # modifiers and character. The rest can change before KeyRelease.
            return (event.keycode >> 24) & 0xff
        return self.windows_scan(event.keycode) if self.windows_scan else event.keycode

    def _key_down(self, event):
        code = self._keycode(event)
        if event.state & 0x0004 and self.keyboard.symbol(code, event.keysym) == 'c':
            self.closing.set()
            return 'break'
        if self.keyboard.press(code, event.keysym, event.time):
            return 'break'
        return None

    def _key_up(self, event):
        code = self._keycode(event)
        if self.windowing != 'x11':
            return 'break' if self.keyboard.release(code) else None
        if self.keyboard.defer_release(code, event.time):
            if self.key_timer is None:
                # X11 can queue a synthetic release and press with equal timestamps.
                self.key_timer = self.root.after(12, self._flush_keys)
            return 'break'
        return None

    def _flush_keys(self):
        self.key_timer = None
        self.keyboard.flush()

    def _hit(self, event):
        for name, (left, top, right, bottom) in self.hit_boxes.items():
            if left <= event.x <= right and top <= event.y <= bottom:
                return name
        return None

    def _left(self, event):
        if event.state & 0x0004:
            return self._special_click(event, timed=True)
        self.panel.focus_set()
        name = self._hit(event)
        if name and PANEL_LAYOUT[name][0] == 'knob':
            self.drag = (name, event.y, self._knob_value(name))
        elif name:
            self.mouse = name
            self.controls.mouse_press(name)
        return 'break'

    def _left_up(self, _event):
        if self.mouse:
            self.controls.release(self.mouse, 'mouse')
        self.mouse = self.drag = None
        return 'break'

    def _special_click(self, event, timed=False):
        self.panel.focus_set()
        name = self._hit(event)
        if name and PANEL_LAYOUT[name][0] != 'knob':
            if timed:
                self.controls.timed_hold(name, time.monotonic())
                self._schedule_timed_holds()
            else:
                self.controls.toggle_latch(name)
        return 'break'

    def _schedule_timed_holds(self):
        if self.hold_timer is not None:
            self.root.after_cancel(self.hold_timer)
        now = time.monotonic()
        self.controls.expire(now)
        self.hold_timer = None
        if self.controls.timed:
            delay = min(self.controls.timed.values()) - now
            self.hold_timer = self.root.after(max(1, math.ceil(delay*1000)), self._schedule_timed_holds)

    def _double(self, event):
        name = self._hit(event)
        if name in KNOBS:
            self.drag = None
            self._set_knob(name, 2048)
            return 'break'
        return self._left(event)

    def _motion(self, event):
        if self.drag:
            name, start, value = self.drag
            self._set_knob(name, value + (start-event.y)*(1 if name == 'VOLUME' else 28))

    def _wheel(self, event, direction=None):
        direction = direction if direction is not None else (1 if event.delta > 0 else -1 if event.delta < 0 else 0)
        if not direction:
            return 'break'
        name = self._hit(event)
        if name == 'VALUE':
            self._turn(direction)
        elif name and PANEL_LAYOUT[name][0] == 'knob':
            self._set_knob(name, self._knob_value(name)+direction*(2 if name == 'VOLUME' else 64))
        return 'break'

    def _contact(self, name, down):
        if self.unit and not self.unit.disconnected.is_set():
            try:
                (self.unit.hold if down else self.unit.release)(name)
            except OSError:
                self.notice = 'Connection to DM-404 lost. Click Restart to try again.'

    def _turn(self, step):
        self.detent = (self.detent+step) % 24
        self._draw_knob('VALUE')
        if self.unit and not self.unit.disconnected.is_set():
            try:
                self.unit.turn(step, settle=0)
            except OSError:
                self.notice = 'Connection to DM-404 lost. Click Restart to try again.'

    def _knob_value(self, name):
        return self.volume if name == 'VOLUME' else self.knobs[name]

    def _set_knob(self, name, value):
        value = max(0, min(100 if name == 'VOLUME' else 4095, value))
        if name == 'VOLUME':
            self.volume = value
            if self.player:
                self.player.volume = value
        elif self.knobs[name] != value:
            self.knobs[name] = value
            if self.unit and not self.unit.disconnected.is_set():
                try:
                    self.unit.set_knob(name, value)
                except OSError:
                    self.notice = 'Connection to DM-404 lost. Click Restart to try again.'
        self._draw_knob(name)

    def _draw_knob(self, name):
        _, x, y, width, _ = PANEL_LAYOUT[name]
        if name == 'VALUE':
            angle = self.detent * math.tau / 24
        else:
            ratio = self._knob_value(name)/(100 if name == 'VOLUME' else 4095)
            angle = (ratio-0.5) * math.radians(270)
        marker = _knob_marker(x, y, width, angle)
        self.panel.coords(self.items[name, 'marker'], *marker)
        if name == 'VOLUME':
            self.panel.itemconfigure(self.items[name, 'percent'], text=f'{self.volume}%')

    def _cycle(self):
        self.controls.mode = LATCH_MODES[(LATCH_MODES.index(self.controls.mode)+1) % len(LATCH_MODES)]
        self.latch_button.configure(text=f'Latch: {self.controls.mode}')

    def _audio_label(self):
        return 'Audio: Muted' if self.muted else 'Audio: On'

    def _toggle_audio(self):
        self.muted = not self.muted
        if self.player:
            self.player.muted = self.muted
        self.audio_button.configure(text=self._audio_label())

    def _load(self):
        self._pick_path('app1', 'Load APP1 firmware', ('APP1 firmware', '*.bin *.BIN'))

    def _import(self):
        self._pick_path('project', 'Import project folder')

    def _pick_path(self, target, title, file_filter=None):
        if self.picker or self.job or self.closing.is_set():
            return
        current = self.app1 if target == 'app1' else self.project
        initial = (current if current and current.is_dir() else
                   current.parent if current and current.parent.is_dir() else Path.home())
        if sys.platform.startswith('linux'):
            self._set_actions(False)
            future = self.worker.submit(pick_linux_path, title, initial, file_filter, cancel=self.closing)
            self.picker = (future, target)
            return
        options = dict(parent=self.root, title=title, initialdir=str(initial))
        if file_filter:
            label, patterns = file_filter
            path = self.dialog.askopenfilename(filetypes=[(label, tuple(patterns.split())), ('All files', '*')],
                                               **options)
        else:
            path = self.dialog.askdirectory(mustexist=True, **options)
        self._path_selected(target, path)

    def _complete_picker(self):
        future, target = self.picker
        self.picker = None
        self._set_actions(True)
        try:
            path = future.result()
        except (OSError, RuntimeError) as error:
            self.notice = str(error)
            self.panel.focus_set()
        else:
            self._path_selected(target, path)

    def _path_selected(self, target, path):
        if path:
            if target == 'app1':
                self._request_boot(Path(path), self.project)
            else:
                self._request_boot(self.app1, Path(path))
        self.panel.focus_set()

    def _set_actions(self, enabled):
        state = '!disabled' if enabled else 'disabled'
        self.import_button.state([state])
        self.load_button.state([state])
        self.restart.state([state if self.app1 else 'disabled'])

    def _restart(self):
        self._request_boot(self.app1, self.project)

    def _request_boot(self, app1, project):
        if self.job or self.closing.is_set():
            return
        self._set_actions(False)
        self.notice = ('Checking project…' if app1 is None else
                       'Preparing project and starting DM-404…' if project else 'Starting DM-404…')
        player = NativeAudioPlayer()
        # Playback starts only after this session takes over the window.
        player.muted = True
        player.volume = self.volume
        self.job = (self.worker.submit(_boot, app1, project, player, self.closing), app1, project, player)

    def _complete_boot(self):
        future, app1, project, player = self.job
        self.job = None
        try:
            unit, temp, firmware = future.result()
        except (OSError, RuntimeError, ValueError) as error:
            self.notice = f'Could not {"start preview" if app1 else "open project"}. {error}'
        else:
            self._activate_session(app1, project, player, unit, temp, firmware)
        self._set_actions(True)

    def _activate_session(self, app1, project, player, unit, temp, firmware):
        if unit is None:
            self.project = project
            self.notice = 'Project selected. Click Load APP1 to start.'
            return
        self._stop_unit()
        self.unit, self.media, self.player = unit, temp, player
        self.player.muted, self.player.volume = self.muted, self.volume
        self.app1, self.project, self.firmware = app1, project, firmware
        self.notice = ('Use the firmware’s Import/Export menu for files on the SD card.'
                       if unit.sd_card else '' if project else self.project_message)
        if self.state_path is not None:
            try:
                _remember_session(self.state_path, app1, project)
            except OSError:
                self.notice = 'Could not save the last session.'
        for name, value in self.knobs.items():
            try:
                unit.set_knob(name, value)
            except OSError:
                break

    def _stop_unit(self):
        unit, self.unit = self.unit, None
        self.mouse = self.drag = None
        self.controls.reset()
        self.keyboard.clear()
        if unit:
            unit.__exit__()
        if self.media:
            self.media.cleanup()
            self.media = None
        self.player = None

    def _show_keys(self):
        if self.help is not None and self.help.winfo_exists():
            self.help.lift()
            return
        top = self.help = self.tk.Toplevel(self.root, background=BG)
        top.title('404Lab — Keys')
        top.transient(self.root)
        top.bind('<Escape>', lambda _event: top.destroy())
        self._label(top, 'Keyboard and mouse', font=(self.font_family, 13, 'bold'),
                    foreground=LIGHT).pack(fill='x', padx=16, pady=(14, 6))
        text = ('Pads 1–16: 1 2 3 4 / Q W E R / A S D F / Z X C V\n'
                'Banks A/F–E/J: 5 6 7 8 9\n'
                'SHIFT: Shift   REMAIN: Tab   SUB PAD: Space   EXIT: Esc\n'
                'VALUE: Enter   Turn: Arrows or [ ]\n'
                'H HOLD   J ROLL   K MARK   L LOOP   N REVERSE\n'
                'B BUS FX   M MFX   U COPY   I / Backspace / Delete DEL\n'
                'O REC   P RESAMPLE   Y RECORD SETTING\n'
                'T PATTERN SELECT   G PATTERN EDIT\n'
                'F2 Cycle latch mode   F3 Release all latches\n\n'
                'Left mouse: Press and hold. Right mouse: Toggle a latch.\n'
                'Middle mouse or Ctrl + click: Hold for 3.2 seconds.\n'
                'Knobs: Drag vertically or scroll. Double-click CTRL to center.\n'
                'VALUE: Scroll to turn, click to press.')
        self._label(top, text, foreground=LIGHT).pack(fill='x', padx=16, pady=(0, 10))
        self.ttk.Button(top, text='Close', command=top.destroy, style='Preview.TButton').pack(pady=(0, 12))

    def _refresh_frame(self, frame):
        if self.last_frame != frame:
            self.last_frame = frame
            self.mini_image = self.tk.PhotoImage(master=self.root, data=_ppm(frame), format='PPM')
            self.large_image = self.mini_image.zoom(4, 4)
            self.display.configure(image=self.large_image)
            self.panel.itemconfigure(self.mini, image=self.mini_image)

    def _paint(self, item, **colors):
        identity = self.items[item]
        if self.palette.get(identity) != colors:
            self.panel.itemconfigure(identity, **colors)
            self.palette[identity] = colors

    def _update_inputs(self, now, leds=None):
        leds = leds or {}
        physical, latched, timed = self.controls.physical, self.controls.latched, self.controls.timed
        held = [label_for(name) for name in physical]
        held.extend(f'{label_for(name)} ({max(0, deadline-now):.1f}s)' for name, deadline in timed.items())
        self.pressed.configure(text='Pressed: '+(' + '.join(held) or '—'))
        self.latched.configure(text='Latched: '+(' + '.join(map(label_for, latched)) or '—'))
        for name, (kind, _, _, _, _) in PANEL_LAYOUT.items():
            if kind in ('oled', 'knob'):
                continue
            outline = AMBER if name in latched else BLUE if name in physical or name in timed else EDGE
            self._paint((name, 'cap'), outline=outline, width=1 if outline == EDGE else 2)
            label_color = LIGHT
            if kind == 'pad':
                base = 3*(int(name[3:])-1)
                r, g, b = (leds.get(base+i, 0) for i in range(3))
                color = '#%02x%02x%02x' % (r, g, b) if r or g or b else CONTROL
                self._paint((name, 'light'), fill=color)
                label_color = BLACK if 0.21*r+0.72*g+0.07*b > 130 else LIGHT
            elif name in KEY_LEDS:
                level = leds.get(KEY_LEDS[name], 0)
                color = '#%02x%02x%02x' % (level, level, level) if level else '#383F4D'
                self._paint((name, 'light'), fill=color)
            label = (f'{max(0, timed[name]-now):.1f}s' if name in timed else
                     name[3:] if kind == 'pad' else name if kind == 'value' else _key_label(name))
            self._paint((name, 'label'), text=label, fill=label_color)

    def _tick(self):
        if self.closing.is_set():
            self.close()
            return
        if self.picker and self.picker[0].done():
            self._complete_picker()
        if self.job and self.job[0].done():
            self._complete_boot()
        now = time.monotonic()
        frame, leds = self.unit.panel_snapshot(now) if self.unit else (bytes(FRAME_BYTES), {})
        if self.unit and self.unit.disconnected.is_set() and not self.job:
            self.notice = 'DM-404 stopped. Click Restart to try again.'
        self._refresh_frame(frame)
        self._update_inputs(now, leds)
        fx = 'sp404fx' if self.unit and self.unit.fx_active else 'dry' if self.unit else '—'
        project = self.project.name if self.project else 'No project loaded'
        self.status.configure(text=f'{self.firmware}\nFX: {fx}  |  {project}')
        error = self.player.error if self.player and not self.muted else None
        self.notice_label.configure(text='  '.join(filter(None, (self.notice, error))))
        self.root.after(30, self._tick)

    def close(self):
        self.closing.set()
        self._stop_unit()
        self.worker.shutdown(wait=True, cancel_futures=True)
        if self.job:
            future = self.job[0]
            self.job = None
            if not future.cancelled() and future.exception() is None:
                unit, temp, _ = future.result()
                if unit:
                    unit.__exit__()
                if temp:
                    temp.cleanup()
        self.root.destroy()


def run(app1=None, project=None, no_audio=False):
    """Start Tk on the main thread, with lazy toolkit imports for headless commands."""
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except ImportError:
        raise RuntimeError('Tk is unavailable. Install Tk support for your Python distribution.') from None
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(f'Could not open the desktop preview. {error}') from None
    root.tk.call('::msgcat::mclocale', 'en')
    state = _session_path()
    window = PreviewWindow(tk, ttk, filedialog, root, no_audio, state_path=state)
    previous = signal.signal(signal.SIGINT, lambda *_: window.closing.set())
    try:
        app1, project = _startup_sources(state, app1, project)
        if app1 or project:
            window._request_boot(app1, project)
        root.mainloop()
    finally:
        signal.signal(signal.SIGINT, previous)
        if not window.closing.is_set():
            window.close()
    return 0
