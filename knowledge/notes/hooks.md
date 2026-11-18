# How mods hook stock

Facts: `knowledge/facts/hooks.json`. Tools: `lab404 check-hook`, `lab404 build`. Smallest example: `mods/demo_counter`.
Addresses belong to one exact image (`hk.guard`).

## Method

Small patch, big payload elsewhere, nothing moved (`hk.method`). A new COPY row goes at the end of a table moved to the end of the
file (`hk.scatter.order`). Decompressed data cannot be patched in the file; set it from code (`hk.patch.decompressed`).

Cheapest hooks, in order:

1. Change a data word: vtable or pointer (`hk.site.tick`, `hk.site.saver`).
2. Retarget a veneer (`hk.pattern.veneer`).
3. Function entry jump, checked by `check-hook`.

## Where to put things

| Place | Use | Fact |
|---|---|---|
| `0x83F7A424-0x83FF0000` SDRAM | code and data; demo uses `0x83FD0000` | `hk.region.sdram`, `st.mem.free` |
| flash after the image, below `0x603FF000` | art, tables, slower code | `hk.region.flash` |
| ITCM `0x1FC00-0x20000` | 1 KB, tiny fast stub | `hk.region.itcm` |
| DTCM, OCRAM | unknown, do not guess | `hk.region.tcm-ocram` |

Mods can collide in the SDRAM area: `hk.region.sdram`.

## Sites

| Purpose | Site | Fact |
|---|---|---|
| Per voice audio | `0x1008E` | `hk.site.audio-voice` |
| Per block audio | `0x1C2D0`, `0x1C766`, `0x1CA74`; IRQ vector `0x4C` | `hk.site.audio-frame` |
| Buttons on stock | `0x800A80A8`, 98 vtable words | `hk.site.button.stock` |
| Event format and key codes | see the facts | `hk.key-event`, `hk.key-codes` |
| Open an existing screen | call `0x800DA598` | `hk.open-screen` |
| Buttons on DOOM OS | `0x802097CC` | `hk.site.button.doom` |
| Project LOAD | `0x8018AE68`, chain word differs by version | `hk.site.load` |
| SAVE, IMPORT, COPY, BACKUP, EXPORT | see the fact | `hk.site.project-ops` |
| Draw | `0x8006FD48` | `hk.site.draw` |
| 1 ms timer | word `0x8021D018`, check `this` | `hk.site.tick` |
| LEDs | `0x800A7DB0` | `hk.site.led` |
| Screensaver | word `0x8022C454` | `hk.site.saver` |

No universal hook exists before or after the BUS effects, which run on the second processor.

## Context rules

| Context | Do | Do not | Fact |
|---|---|---|---|
| Audio, priority 1, 1.333 ms | math on prepared memory | malloc, files, waits, mutex, LED or sysex send | `hk.ctx.audio` |
| Float in audio | check live FP registers per site | assume safe everywhere | `hk.ctx.audio-fpu`, `st.rtos.fpu` |
| Draw | draw only | files, malloc | `hk.ctx.draw` |
| Files | button or LOAD chain, idle states | during REC, dialog, screensaver | `hk.ctx.files` |
| Interrupt | short, no blocking | task-only kernel calls | `hk.ctx.irq` |
| Scheduler locked | very short | long copies | `hk.ctx.lock` |

Many of these rules are judgment from structure and a few unit reports. Only `hk.ctx.audio` and `hk.ctx.irq` rest on read code.

## Living with DOOM OS

Layout: `hk.doom.layout`. Size of its changes: `hk.doom.diff`. It has no direct reference to the payload area: `hk.doom.free`.
Its files: `hk.doom.files`. Do not imitate its screens (`docs/LEGAL_NOTES.md`).

## Storing settings

Own file, not PADCONF (`hk.storage.sidecar`). Save order: `hk.storage.order`. Never require an SD card (`hk.lesson.sd`).

## Lessons from crashes and bad builds

| Lesson | Fact |
|---|---|
| A hole in the scatter table is not free | `st.mem.gap-trap` |
| A stopped counter looked like a frozen feature, and the stand hid it | `hk.lesson.counter` |
| File and malloc work from drawing: crashes, probable cause | `hk.ctx.draw` |
| Stock must keep working, events outside your screen pass through | `hk.lesson.stock-first` |
| Background work starves the sequencer, guards that cut tails are disliked | `hk.lesson.overload` |
| Piled-up changes gave hangs and a loud squeal; one change per test | `hk.lesson.changes` |
| SD faults look like firmware faults | `hk.lesson.sd` |
| A crash shows as a hang, with no log | `hk.fault-visibility` |
| Stand pass is no proof of timing | `hk.stand-limits` |
| Code loaded at run time needs cache maintenance | `hk.loaded-code` |
