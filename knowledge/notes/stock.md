# Stock 5.52 internals

Facts: `knowledge/facts/stock.json`. Most hold on DOOM OS 0.7.2 and 0.7.3 too, and those carry byte checks for all three.
`python -m lab404 verify-knowledge FILE` runs them on an image.

## Image layout

- Flash base, sizes, hash: `st.image.file`. Table pointers at file offset 0x80: `st.image.header`.
- Rows and handlers: `st.image.scatter`, `st.image.handlers`. Run `python -m lab404 map FILE`.
- File offset of main code = address - `0x80000000` + `0x21AC0`. Decompressed data has no file offset (`st.image.offset`).
- Boot path: `st.boot.chain`. Constructor list: `st.mem.ctors`.

## SDRAM use

| Range | Use | Fact |
|---|---|---|
| `0x80000000-0x80245740` | main code, constants | `st.image.scatter` |
| `0x80245740-0x802E7800` | initialised data | `st.image.scatter` |
| `0x802E7800-0x8353A30C` | bss, samples (split unknown) | `st.mem.samples` |
| `0x8353A30C-0x8383A30C` | malloc pool, 3 MB, in no row | `st.mem.heap` |
| `0x8383A30C-0x8383A424` | constructor list | `st.mem.ctors` |
| `0x8383A424-0x83F7A424` | one large buffer, likely looper | `st.mem.big-buffer` |
| `0x83F7A424-0x83FF0000` | no references: the place for mods | `st.mem.free` |
| `0x83FF0000-0x84000000` | non-cacheable data and buffers | `st.mem.top` |

Older notes had the heap wrong. The lesson is `st.mem.gap-trap`: a hole in the table is not free memory.
Flash page `0x603FF000` belongs to stock (`st.flash.config`).

## OS and tasks

- micro T-Kernel 2.00.44, veneers to kernel calls: `st.rtos`. Critical sections and scheduler lock: `st.rtos.critical`.
- Task table with priority and stack: `st.tasks.list`. The rest: `st.tasks.others`.
- FP registers are kept per task by attribute bit 0x1000: `st.rtos.fpu`.

Rough order: audio render 1, MIDI sync 2, sample tasks 3-6, MIDI RX 8, sample record 10, looper 12, PlayTask 13, file 20, panel 29, param 31.

## Audio

```
DMA3 IRQ -> flag + music clock -> inittsk (priority 1) -> 0x1C2D0 one block
   clear mix -> 32 voices (0x1C71E -> 0x1008E -> 0x80005870 -> 0x14B88)
   -> 0x1E248 -> 0x1CB84 -> clamp to 20 bits -> pack into DTCM -> DMA -> SAI1 -> BMC
```

- Chain: `st.audio.chain`. Block size and deadline: `st.audio.block`. Headroom unknown: `st.audio.headroom`.
- Render: `st.audio.render`. Voice call: `st.audio.voice`. Voice internals not mapped: `st.audio.voice-struct`.
- Frame layout and DMA banks: `st.audio.pack`. Channel meaning: `st.audio.routes`.
- Clamp prints per clipped sample: `st.audio.clip-log`.
- Transport structure: `st.transport`, `st.transport.end`. Recorder: `st.rec`.

## UI and input

```
1 ms cyclic -> PANEL TASK method 0x80072CF0 code 0 -> scan 0x80046E90, encoder
   -> ring 0x80B5E7A4 -> router 0x8003B530 -> page object -> handler 0x800A80A8 -> virtual method
```

- Tick: `st.input.tick`. Ring and event layout: `st.input.ring`. Handler and method offsets: `st.input.handler`.
- Pressed keys bit map and known codes: `st.input.keys`.
- Page number and SYSTEM tab: `st.ui.page`. Draw commit: `st.ui.commit`. Screensaver: `st.ui.saver`; its Custom mode leaks ~65 KB a start: `st.ui.saver-leak`.
- Modal and screensaver flags are not settled: `st.ui.flags`. No screen map yet: `st.ui.map`.
- Commands to SMPL TASK: `st.queue.smpl`.
- Frame output only reaches the display in the page loop, not while PANEL TASK is busy: `st.ui.commit`.
- CHOP, AUTO MARK and the marker screen: [chop.md](chop.md).
- Effect knob pages and EFX SET rows: `st.efx.knob-pages`.

## Storage

- Drives: `st.storage.drives`. Project folder: `st.storage.project`.
- `PADCONF.BIN` layout, and why it has no room for extra data: `st.storage.padconf`. Formats: `st.storage.formats`, with samples `st.storage.smp`, patterns `st.storage.ptn`, pictures `st.storage.picture`.
- From a computer over USB: files on both drives and the unit's status, `hw.usb.link`. A host tool could write update files to the card: `hw.update.usb-card-path`.
- What each operation does to files: `st.storage.ops`. PTN name check: `st.storage.ptn-filter`.
- File call addresses: `st.storage.api`. Save is not atomic as far as known: `st.storage.atomic`.

## Limits of this page

Other stock versions have not been compared (`st.versions`). No full boot has run on the stand.
