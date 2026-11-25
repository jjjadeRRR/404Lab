# Hardware Findings

Observations recorded on a reference SP-404MKII unit across external firmware builds (DOOM OS 0.6.1–0.7.4) and `lab404 build` candidates. Each entry reflects behaviour observed on one tested unit under specific conditions and does not establish universal compatibility across all units or projects.

## Modified APP1 Hardware Verification

- **Full-mod `lab404 build` image (DOOM OS 0.7.4-651C, 2026-11-24):** Built with 13 jump hooks, 19 pointer replacements, 4 `disable` hooks, 71 byte patches, relocated AUTO MARK `TRANSIENT`/`LEVEL` copies, and a screensaver flash block. Verified SHA-256 on SD card: `c115a3ce6e76ad57e7b1d577e8c48d1634fc4806f0b6ec97d9a6dd8f0a925224`. Booted and operated normally during brief interactive testing. Compared to an earlier reference build (155-byte difference), DM-404 placed all 32 AUTO MARK LEVEL markers at identical sample positions on a 65-second stereo clip.
- **`mods/quick_system` (`lab404 build` on DOOM OS 0.7.4-651C, 2026-11-23):** Candidate `65eb1dfb…641d` booted on a physical unit (`hk.lab404-build-on-unit`); `HOLD + ROLL` opened `SYSTEM` on the main screen, `EXIT` returned, and basic playback, DOOM OS screens, and save/load functioned normally. Tested via `build` directly, not `package`.

## Verified Capabilities

| Feature | Observed Hardware Behaviour | Facts | Reference |
|---|---|---|---|
| Fault screen | Three hardware faults photographed with PC, LR, CFSR, and faulting address; each exposed a stock bug | `hk.fault-screen`, `hk.fault-visibility`, `hw.display.port` | [`mods/fault_screen`](../mods/fault_screen/mod.json) (DM-404 only so far) |
| Per-pad audio effects | Resonant LP/HP filter, sample-rate reducer, mono; settings persisted across `LOAD` and power cycles without an SD card | `hk.recipe.pad-effects`, `hk.site.audio-voice`, `hk.storage.sidecar` | |
| Output meter | Peak, CLIP, and M/S/I loudness matched an external DAW meter within rounding | `hk.recipe.output-meter`, `hw.bmc.rx-slots` | |
| 32-pad mute groups | Two pages of mute groups (up to 32 pads) functioned on hardware | `hk.recipe.mute-32`, `st.mute.groups`, `st.mute.screen` | |
| `COMPRESSOR 2` (stock MFX type 29) | On BUS 1, the BMC runs the factory DSP effect: `SUSTAIN`, `ATTACK`, and `RATIO` audibly alter the sound, `TONE` has minimal audible effect, and `MODE = LIMIT` mutes the bus | `hk.recipe.mfx-grid-entry`, `app0.type29-on-unit` | |
| System monitor screen | Measured 10% avg / 18% peak audio load, 599–600 MHz CPU clock, and ~2.2 MB free in the malloc pool | `hw.cycles.measured`, `st.mem.heap-measured`, `st.mem.heap-walk` | Pool walk implemented in `Emulator.malloc_pool` |
| Loader dump | Bootloader read out to SD card with identical bytes across two consecutive dumps | `hk.lesson.read-what-you-can`, `hw.boot.loader-image` | |
| Stock screen shortcut | `HOLD + ROLL` opened `SYSTEM`; `EXIT` returned cleanly | `hk.lab404-build-on-unit`, `hk.open-screen` | [`mods/quick_system`](../mods/quick_system/mod.json) |
| Flash screensavers | Animated screensaver frames executed from XIP flash block | `hk.region.flash`, `hk.site.saver` | |
| 32-pad CHOP | Multi-round sample chopping via reused stock CHOP screens; exposed null-pointer jump on failed pad copy | `st.chop.*`, `hk.recipe.automark-32`, `st.chop.copy-null-check` | |

A fix for `st.ui.saver-leak` has been integrated into external test builds on DOOM OS 0.7.4, though the leak reduction has not yet been re-measured on hardware.

## Engineering Pitfalls

| Pitfall | Technical Cause & Constraint | Facts |
|---|---|---|
| Per-pad delay and reverb | Exceeded CPU budget under polyphonic load, causing audio dropouts, metallic artifacts, and crackling with two active reverbs | `hk.lesson.overload` |
| File I/O or `malloc` in draw context | Caused hangs and crashes; resolved by moving file access and allocations out of display draw routines | `hk.ctx.draw`, `hk.ctx.files` |
| CPU guards cutting effect tails | Abruptly truncating active voices/tails degrades audio output, and inaccurate load estimates caused false triggers | `hk.lesson.overload` |
| Mandatory SD card for settings | Requiring SD presence during `LOAD` caused effects to lock up when no card was inserted; mod state must operate without an SD card | `hk.ctx.files`, `hk.lesson.sd` |
| Degrading SD card | Induced hangs, failed boots, and stalled updates even on unmodified DOOM OS, mimicking firmware bugs | `hk.lesson.sd`, `hw.update.stalled`, `hw.update.stalled-cause` |
| Custom CHOP UI rewrite | Reimplementing the marker UI from scratch introduced usability regressions; reusing stock CHOP screens proved more reliable | `st.chop.screens`, `st.chop.marker-screen` |
| Pad animation side effects | Early pad animation hooks caused `TRUNCATE` to fail intermittently even when animations were disabled (`stock-first` rule) | `hk.lesson.stock-first` |
| Sample-rate reducer clicks | Audible clicks observed around ~5 kHz settings; root cause remains open | |

## Stock 5.52 Bugs Found

- `st.import.malloc-unchecked`: sample import dereferences a null pointer when the 3 MB malloc pool is exhausted.
- `st.ui.saver-leak`: the Custom screensaver leaks ~66 KB from the malloc pool on each activation when 4 custom images are present (~6 KB once without them; 0 bytes for the default saver), confirmed on unmodified stock 5.52 in DM-404 (`StockSaverLeak`).
- `st.chop.copy-null-check`: when the initial pad copy in CHOP fails, stock firmware jumps through a null cancel-check callback (`PC = 0`, `LR = 0x8004A987`).
