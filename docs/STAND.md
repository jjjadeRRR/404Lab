# Emulation Stands: Capabilities and Limits

404Lab uses two emulation levels. A pass on either stand verifies behaviour only within that emulator's model and is never proof of hardware operation.

## Instruction-Exact Stand (`lab404/stand.py`)

Unicorn executes individual Cortex-M7 firmware functions starting from scatter-table-initialized memory. Attempting to boot full stock firmware from reset on Unicorn traps at `0x800022C8` due to unmodelled peripherals and the lack of an interrupt controller, so full-firmware tests use DM-404.

### Modelled

| Aspect | Behaviour | Test |
|---|---|---|
| Startup memory | Scatter-load rows applied in order, including zero-initialized regions | `test_stand`, `test_review_findings` |
| Calling convention | AAPCS arguments, stack integrity, and callee-saved registers checked on return | `test_stand` |
| Unmodelled memory | Halts immediately with `Boundary` and reports the accessed address | `test_stand` |
| Execution budget | Bounded by instruction count, not wall-clock time | `test_stand` |
| Function stubs | Replaces target firmware calls, logs invocations, and records arguments | `test_stand` |
| Bit-exact comparison | Runs identical inputs against base and candidate builds | `test_demo_mod` |

### Not Modelled

| Aspect | Consequence | Verification Target |
|---|---|---|
| Timing, cycles, caches, SDRAM latency | Instruction counts do not reflect hardware cycles (Arm publishes no Cortex-M7 cycle tables `[DOC]`) | Physical unit only |
| Peripherals | Reads of unmodelled registers halt execution | DM-404 or physical unit |
| Interrupts and RTOS | No NVIC, preemption, or task switching | DM-404 |
| Second processor (BMC/DSP) | Encrypted `APP0` does not run; hardware effects are absent | Physical unit only |
| FAT and SD storage | Filesystem calls are not modelled | DM-404 or physical unit |

## Whole-Firmware Stand (`lab404/emulator.py`)

DM-404 is an external QEMU machine with peripheral models, interrupts, and micro T-Kernel RTOS scheduling. `tools/setup_dm404.sh` builds DM-404 outside this repository. Runs use temporary flash images and copy-on-write drive overlays. The link uses Unix sockets on Linux and macOS and two loopback TCP ports on Windows.

| Verified Behaviour (`tests/test_emulator.py`) `[EMULATOR]` | Test |
|---|---|
| Stock 5.52 boots to main screen and streams audio blocks | `test_stock_boots_and_keys_work` |
| Key inputs switch screens and `EXIT` returns | `test_stock_boots_and_keys_work` |
| Candidate matches base screen-for-screen on stock 5.52 and DOOM OS 0.7.3 | `test_candidate_matches_its_base_screen_for_screen` |
| Entry hooks fire via firmware event dispatch | `test_a_hook_fires_in_the_running_firmware` |
| DOOM OS opens its UI on `REMAIN + SUB PAD` | `test_doom_opens_its_own_screen_and_stock_does_not` |
| With project drive: pads produce audio, voice-renderer hooks fire, peaks match base | `test_a_hook_in_the_voice_renderer_fires_and_pads_sound_the_same` |
| Mixer helper `0x15FEE` is unused on ordinary pad playback | `test_the_mixer_helper_is_not_on_the_ordinary_pad_path` |
| Boot readiness requires reaching the main-screen page word under load | `test_ready_means_the_main_screen_even_under_load` |
| Documented screen navigation routes reach expected pages | `test_every_route_arrives` |
| Recorded key verdicts hold across sampled controls | `test_recorded_verdicts_still_hold` |
| End-to-end `APP1` to `package` flow on stock and DOOM OS | `test_a_whole_task_from_app1_to_package_on_two_bases` |
| Replay catches mods altering existing stock keys | `test_replay_catches_a_mod_that_changes_something_existing` |
| Replay catches chords firing on undeclared screens | `test_replay_catches_a_chord_that_also_fires_on_screens_it_was_not_declared_for` |
| DOOM OS screen retains its own key bindings | `test_on_doom_os_its_own_screen_keeps_the_keys` |

DM-404 limits:
- Audio tests require `inputs/project-drive.img`; peak comparisons are coarse, not bit-exact.
- The optional DaisySP-based FX engine models 48 effects. Its output can differ from hardware.
- Execution timing does not match physical hardware.

### Native 2D preview

The preview requires a desktop session, Python with Tk support, DM-404, and a local `SP404MKII_APP1.bin`. Run `python -m lab404 doctor` to check for Tk, QEMU, the internal drive, fatimg, and the FX library.

- **Linux.** Run `tools/setup_dm404.sh`. It builds QEMU, fatimg, a blank internal drive, and the FX library under `~/lab404-deps/dm-404` by default. The build requires Git, a C/C++ toolchain, Ninja, pkg-config, GLib, and Pixman. Set `LAB404_DEPS` to use a different parent directory. Install KDialog, Zenity, or YAD for the file and folder pickers.
- **macOS (experimental).** Run the same setup script with the build dependencies and a Tk-enabled Python.
- **Windows (experimental).** Extract a [DM-404 win64 release](https://github.com/nickpetty/dm-404/releases) under `%USERPROFILE%\lab404-deps\dm-404`. If you set `LAB404_DEPS`, extract it under that directory's `dm-404` folder. Run the upstream app once to create its internal image. Folder import and `--project` `.img` validation require `fatimg.exe`, which can be built with the upstream `tools/build_fatimg.sh` in MSYS2.

```bash
python -m lab404 gui [APP1] [--project PATH] [--no-audio]
```

Use **Load APP1** to choose an image from the window. **Restart** boots the current APP1 again with the selected media. The preview remembers the last APP1 and project independently. Supplying a different APP1 keeps the remembered project unless you pass `--project`.

**Import Project** opens a folder. A folder containing `PADCONF.BIN` is mounted as the active project in temporary internal storage. Loose WAV files, `PROJECT_*` folders, and projects from a selected `EXPORT` or app export folder go into `IMPORT` on a temporary SD card. A copied SD root keeps its `IMPORT` and `EXPORT` directories. Use the firmware's Import/Export menu to load SD content onto pads. [Hardware project import](https://static.roland.com/manuals/sp-404mk2_reference_v4/en-US/7960231578539403.html) · [App export folders](https://static.roland.com/manuals/sp-404mk2_app_v4/en-US/8032372378658955.html)

Pass an existing `.img` with `--project PATH`. FAT32 and partitioned card images mount in the SD slot. DM-404 internal images mount in the internal slot. Writes go to temporary overlays and are discarded on restart or exit.

The [control panel](panel-layout.svg) shows live LED levels and the OLED at its original size. The larger OLED view uses 4× scaling. **? Keys** opens the keyboard and mouse reference. Shortcuts follow physical key positions. Right-click latches a button, F2 cycles latch modes, and F3 clears latches. Middle-click or Ctrl-click holds a button for 3.2 seconds.

VOLUME controls local playback gain. `--no-audio` starts muted. Linux uses PipeWire, PulseAudio, or ALSA for playback. The macOS and Windows backends use AudioToolbox and waveOut respectively. **FX: sp404fx** indicates that QEMU loaded the effects library. **FX: dry** indicates dry playback. Set `SP404_FX` to a library path or to `off`.

### Debugging with GDB

Pass QEMU arguments via `Emulator(..., extra_args=['-gdb', 'unix:PATH,server=on,wait=off'])`, then attach with `gdb` using `set architecture arm` and `target remote PATH` (unix sockets work in restricted environments where `-s` TCP stubs may fail). Hardware breakpoints and read/write watchpoints are supported. If `bt` stops early without symbols, inspect `$lr` and odd `0x80xxxxxx` return addresses on the stack; a Python breakpoint whose `stop()` returns `False` can count calls without halting.

## Key Binding Sweeps (`sweep`)

`python -m lab404 sweep` exercises recorded bindings across fresh boots, and `record-sweep` saves results to `knowledge/observations/<firmware>.json`. Import requires a log matching a known image profile and the current binding definitions (citation updates leave the definition fingerprint unchanged).

| Verdict | Meaning |
|---|---|
| `confirmed` | Declared page, key LED, or audio output appeared on the emulator |
| `reacted` | Observable state changed without matching a declared control expectation |
| `no-reaction` | No observable change (may require missing preconditions such as a playing sample or loaded deck) |
| `unobserved` | The run or its control lacked a confirmed screen or stable starting state, or could not be compared |
| `contradicted` | Transitioned to a different page than declared; requires manual inspection |

Only `confirmed` and `reacted` become `[EMULATOR]` evidence. Verdicts depend on the mounted project drive and never establish that a key is `free`. On stock 5.52, a sweep tested 784 bindings (3 skipped for audio/power-on preconditions), with 119/120 verdict matches and 120/120 final page matches on random repeats; 47 entries are classified as `unobserved` where logs lacked a confirmed starting state.

## Choosing a Stand

| Question | Stand |
|---|---|
| Exact register, stack, memory, and sample math for a function | Unicorn (`lab404/stand.py`) |
| Full boot, RTOS tasks, screens, keys, and regression replay | DM-404 (`lab404/emulator.py`) |
| Real-time audio deadlines, BMC DSP sound, SD cards, hardware faults | Physical unit |
