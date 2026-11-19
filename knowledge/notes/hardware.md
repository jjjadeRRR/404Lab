# Hardware

Facts: `knowledge/facts/hardware.json`. Ask with `python -m lab404 ask TERM`. Firmware addresses are for stock 5.52 and hold on
DOOM OS 0.7.2 and 0.7.3 where the fact says so. Nothing here came from measuring timing on a unit.

## Chips

| What | Value | Fact |
|---|---|---|
| Main CPU | i.MX RT1062, Cortex-M7, FPU single and double | `hw.cpu.family`, `hw.cpu.part`, `hw.cpu.fpu` |
| Marking on one unit | DVJ6B: consumer, 12 x 12 mm, 600 MHz rating, silicon A1 | `hw.cpu.marking` |
| Silicon revision elsewhere | unknown | `hw.cpu.silicon` |
| Core clock | 600 MHz believed, not measured | `hw.cpu.clock` |
| Clock tree, SDRAM bus | unknown | `hw.clocks.tree` |
| Memory | 64 MB SDRAM, BMC 32 MB, eMMC 16 GB, two 4 MB NOR | `hw.mem.chips`, `hw.mem.nor-owner` |
| Second processor | Roland BMC, runs APP0 | `hw.bmc.chip`, notes/app0.md |

## Memory map and caching (`hw.mem.map`, `hw.mpu.table`)

| Range | MPU attributes | Holds |
|---|---|---|
| `0x00000000-0x00020000` ITCM | TCM | vectors, fast code, audio loop |
| `0x20000000-0x20020000` DTCM | TCM | data, audio output banks |
| `0x20200000-0x202C0000` OCRAM | write-back | data, mix buffer `0x202AD3A0` |
| `0x60000000-0x60400000` flash | write-back, read-only | APP1 from `0x60080000`, XIP code |
| `0x80000000-0x84000000` SDRAM | write-back, executable | main code, heap, samples |
| `0x83FF0000-0x84000000` SDRAM | not cached | transfer buffers, top data |

- Regions 0, 1, 3 are Device background ranges, and older notes omit them.
- Region 2 is written with an unaligned base (`hw.mpu.flash-base`). Arm pseudocode gives the range above. Not measured.
- `MPU_CTRL=5`: in HardFault and NMI the default map applies, SDRAM write-through (`hw.mpu.ctrl`).
- Caches: 32 KB each, 32 byte lines, enabled by APP1 itself (`hw.cache.geometry`, `hw.cache.enable`). Stock helpers in `hw.cache.ops`.
- DMA does not see the cache (`hw.cache.dma-coherency`). Uncached SDRAM reads about 4 times slower by NXP figures (`hw.cache.speed`).

For what is free inside this map see notes/stock.md and `st.mem.free`.

## Timing

- Audio deadline is 1.333 ms per block, see notes/stock.md.
- There are no cycle tables and no measured costs (`hw.cycles.cost`). Instructions are not cycles.
- The DWT counter does not run by itself on stock (`hw.dwt.stock`). DOOM OS turns it on only sometimes (`hw.dwt.doom`). The lock is
  unknown (`hw.dwt.lock`). Order that is safe in both cases: TRCENA, unlock, CYCCNTENA, then verify the count moves.

## Peripherals

| Peripheral | Use | Fact |
|---|---|---|
| LPUART3 `0x4018C000`, 1 Mbaud | link to BMC: effects, LEDs | `hw.periph.lpuart3`, `hw.periph.send` |
| SAI1 `0x40384000`, eDMA | audio to BMC | `hw.periph.sai` |
| GPIO2, ADC, ADC_ETC | panel scan | `hw.panel.scan` |
| LPSPI, uSDHC, FlexSPI | display, card, eMMC, flash; only partly confirmed | `hw.periph.spi-sd` |
| USB | hub with an audio and MIDI device and a serial port; the serial link carries files and parameters; APP1's USB stack not read | `hw.usb`, `hw.usb.link` |

A complete peripheral register map does not exist yet.

## Panel, LEDs, display

- Input is scanned by the main CPU, in the panel tick. The older claim of a separate panel controller on a UART is disputed
  (`hw.panel.scan`, `hw.panel.uart-claim`).
- LED path and message format: `hw.leds.path`. One pad costs 120 microseconds of blocking UART, all 16 about 1.92 ms (`hw.leds.budget`).
  LED sends share a mutex and wire with effect parameters.
- Modes: `hw.leds.modes`. Display: 128 x 64, left pixel in bit 31 (`hw.display`).

## Second processor link

- Effect parameters: Roland DT1 packets, address rules in `hw.bmc.sysex`. Sent with `0x800CD3A0`.
- From the BMC: 4 byte frames on LPUART3, see `hw.bmc.rx`.
- SAI and frame slots: `hw.periph.sai`, `st.audio.pack`, `st.audio.routes`.

## Faults and resets

- Fault vectors are `bx lr`, so a crash looks like a hang (`hw.faults.vectors`).
- SDRAM across reset: not guaranteed (`hw.reset.sdram`).
- Errata to know: `hw.errata.relevant`.
- ROM and flash start: `hw.boot.rom`.

## The loader and what can brick a unit

Read from a dump of one unit's loader (version 1.10); the dump itself is Roland's code and is not kept here.

- What the loader is and how it is laid out: `hw.boot.loader-image`.
- One pin decides between APP1 and the update screen, before APP1 runs: `hw.boot.select-pin`. Who drives it is unknown: `hw.boot.select-pin-driver`.
- The loader checks nothing in APP1 and verifies nothing after writing: `hw.boot.no-app1-check`, `hw.update.no-verify`.
- A normal update erases only the APP1 area; APP1 must not exceed 0x37F000 bytes: `hw.update.app1-range`.
- Files that must never be on a card: `hw.update.whole-files`. Service code in APP1 that erases the loader: `hw.service.loader-erase`.

## Open gaps worth filling

Silicon revision per unit, clock tree, real cycle counts, panel wiring, USB stack, role of each NOR chip, who drives the loader's select pin, the BMC's own loader, and a full peripheral map.
