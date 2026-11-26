"""What this computer needs before the tools work, and how to get it on Linux, macOS or Windows. Changes nothing."""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HINTS = {
    'Linux': {'clang': 'install clang with your package manager, for example `sudo apt install clang` or `sudo pacman -S clang`',
              'git': '`sudo apt install git` or the same with your package manager', 'python': 'Python 3.10 or newer from your package manager'},
    'Darwin': {'clang': '`brew install llvm` and put it first on PATH as brew says (Apple\'s own clang may lack the Arm embedded target)',
               'git': '`xcode-select --install` or `brew install git`', 'python': '`brew install python`'},
    'Windows': {'clang': '`winget install LLVM.LLVM`, then open a new terminal so clang is on PATH',
                'git': '`winget install Git.Git`', 'python': '`winget install Python.Python.3.12`'},
}
SOURCE = 'int lab404_probe(int a) { return a + 1; }\n'
FLAGS = ('--target=arm-none-eabi', '-mcpu=cortex-m7', '-mthumb', '-mfloat-abi=soft', '-ffreestanding', '-c')


def _builds():
    with tempfile.TemporaryDirectory(prefix='lab404-doctor-') as tmp:
        src, obj = Path(tmp)/'p.c', Path(tmp)/'p.o'
        src.write_text(SOURCE, encoding='utf-8')
        r = subprocess.run(['clang', *FLAGS, str(src), '-o', str(obj)], capture_output=True, text=True, encoding='utf-8')
        return r.returncode == 0 and obj.exists(), (r.stderr.strip().splitlines() or [''])[-1]


def report(system=None, which=shutil.which, inputs=None):
    """[(what, state, hint)]. state: ok, missing, or optional, not found."""
    system = system or platform.system()
    hints = HINTS.get(system, HINTS['Linux'])
    root = Path(__file__).resolve().parents[1]
    rows = []
    ok = sys.version_info >= (3, 10)
    rows.append(('python', 'ok' if ok else 'missing', '' if ok else f'this is {platform.python_version()}; {hints["python"]}'))
    pip = 'run `python -m pip install -r requirements.txt` inside the virtual environment (README.md, Try it)'
    try:
        import capstone  # noqa: F401
        rows.append(('capstone', 'ok', ''))
    except ImportError:
        rows.append(('capstone', 'missing', pip))
    try:
        import unicorn  # noqa: F401
        rows.append(('unicorn', 'ok', ''))
    except ImportError:
        rows.append(('unicorn', 'missing', pip))
    clang = which('clang')
    rows.append(('clang', 'ok' if clang else 'missing', '' if clang else hints['clang']))
    if clang:
        built, said = _builds()
        rows.append(('clang builds for the unit', 'ok' if built else 'missing', '' if built else f'this clang cannot build Arm Cortex-M7 code ({said}); {hints["clang"]}'))
    else:
        rows.append(('clang builds for the unit', 'missing', 'needs clang first'))
    rows.append(('git', 'ok' if which('git') else 'optional, not found', '' if which('git') else f'only used to stamp reports with the tool revision; {hints["git"]}'))
    inputs = Path(inputs or os.environ.get('LAB404_INPUTS', root/'inputs'))
    found = sorted(p.parent.name for p in inputs.glob('*/SP404MKII_APP1.bin')) if inputs.exists() else []
    rows.append(('firmware images', 'ok' if found else 'optional, not found',
                 ', '.join(found) if found else f'bring your own SP404MKII_APP1.bin: this project ships none. For the tests put it in {inputs}/stock-5.52/ (see AGENTS.md)'))
    from .emulator import find_blank_drive, find_fatimg, find_fx, find_qemu
    if system == 'Windows':
        setup = ('Extract DM-404-win64 under %USERPROFILE%\\lab404-deps\\dm-404 '
                 'or set LAB404_DEPS to the directory containing dm-404.')
    else:
        setup = 'Run tools/setup_dm404.sh on Linux or macOS.'
    qemu = find_qemu()
    drive = find_blank_drive()
    fx = find_fx(qemu)
    fatimg = find_fatimg()
    rows.append(('whole-firmware emulator', 'ok' if qemu.is_file() else 'optional, not found',
                 str(qemu) if qemu.is_file() else setup))
    rows.append(('internal drive', 'ok' if drive.is_file() else 'optional, not found',
                 ('Open DM-404 once or import an internal .img.' if system == 'Windows' else setup)
                 if not drive.is_file() else ''))
    rows.append(('sp404fx', 'ok' if fx else 'optional, not found',
                 str(fx) if fx else f'Dry audio when the FX engine is unavailable. {setup}'))
    rows.append(('fatimg', 'ok' if fatimg else 'optional, not found',
                 'Used to import folders and verify .img project media. Build fatimg from DM-404.'
                 if not fatimg else ''))
    try:
        import tkinter  # noqa: F401
    except ImportError:
        rows.append(('Tk (GUI)', 'optional, not found', 'Install Tk support for your Python distribution.'))
    else:
        rows.append(('Tk (GUI)', 'ok', ''))
    return rows
