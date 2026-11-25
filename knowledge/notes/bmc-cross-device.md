# Roland BMC across devices

Reviewed 2026-11-25. The comparisons below use public sources and unmodified Roland
updates. The local tests read files and run a DSP model on a computer.

## Which hardware matches?

| Device | Observation | What it establishes |
|---|---|---|
| SP-404MKII | One teardown shows `Roland BMC 5100040716 JAPAN` on IC3 and main-board marking `5100074762`. The maintainer's unit has the same board number. Its IC3 marking is partly covered. [SP teardown, 7:02](https://www.youtube.com/watch?v=wTqpxwjcDRg&t=422s) | The full BMC part marking on the filmed SP. The earlier 404Lab record attributed board number `5100074760` to this frame. |
| MC-101 | One teardown shows the same `5100040716` part number. [MC-101 teardown, 7:30](https://www.youtube.com/watch?v=gkUMut_N0N4&t=450s) | The two photographed boards share a Roland part number. Silicon stepping and board wiring need their own evidence. |
| BOSS GT-1000CORE | The teardown close-up also shows `5100040716`. [Board photo](https://kanengomibako.github.io/pages/img/09_346_08_gtsc_pic08.jpg) | A third product uses that part. |
| Roland AX-Edge | The teardown author identifies `5100040716` on the sound board. [Author's teardown](https://www.youtube.com/watch?v=4bR2XmzJY0A) | A fourth reported use, with its own memory and firmware. |
| TR-6S / TR-8S | Cowbell records 64 MB parallel NOR and 32 MB SDRAM on its TR-6S and leaves that unit's SoC ID open. The author's TR-8S teardown comparison gives a different part-number transcription. [Cowbell hardware notes](https://github.com/ajmwagar/cowbell/blob/38646c04851d30c49f777e6f7a9fef9810799f49/docs/hardware.md), [author's write-up](https://averywagar.com/post/tr6s-part1/) | The TR-6S is a useful format and storage comparison. Its exact part and a custom image running on it are open in the cited Cowbell revision. [Project status](https://github.com/ajmwagar/cowbell/tree/38646c04851d30c49f777e6f7a9fef9810799f49) |

## Boot and update paths

- **SP-404MKII.** The NXP host starts its resident `UPD1` from its own NOR. The
  dump from one unit shows both the branch to `APP1` and the update path that
  forwards `APP0` to the BMC. The BMC-side updater is called `UPD0`. Its image,
  acceptance checks for the MFX program area and recovery behavior after a bad
  write remain open. The NXP dump proves the host side of this path. See
  `hw.boot.loader-image`, `app0.upd1-transfer` and [recovery limits](../../docs/SAFETY.md).
- **MC-101.** The resident `App0` (`RPG69_C0L`) and the recovery updater
  `App0_UPD` live in the first part of Core 0 flash. The official SD archive
  carries four application and content files. Its `C0A` is the main ARM
  application and `C1A` contains the sound-engine ARM code. The MC-107 author
  reports a hardware run with an author-written startup layer in `C0A` and SD
  patches applied to both ARM cores in RAM. The stock `C1A` stayed in flash.
  The author verified eight-track playback and extended drum-pad editing and
  lists further hardware tests separately. This is a precedent for using a
  resident updater and leaving the factory sound-engine image in place.
  [MC-101 boot architecture](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/docs/system_architecture_and_boot_flow.md),
  [MC-107 hardware checklist](https://github.com/edco/mc-107/blob/62ee091bd04167a73874ca7fe3e53631be922dfe/ROADMAP.md).
- **SYSTEM-1 and SYSTEM-8.** The SDK authors ran their own DSP programs on both
  synths inside PLUG-OUTs, using the instruments' PLUG-OUT load paths. The ARM
  control code copies DSP instructions and registers the program to run.
  SYSTEM-8 slot/task controls and SYSTEM-1 section scheduling are documented
  separately. On SYSTEM-1, copying a test program without registering it left
  it inactive. This gives two models for finding the SP's internal MFX
  selection and scheduling path. SP firmware acceptance is a separate open
  question. [Hardware results](https://github.com/enorrmann/roland-plugout-reveng/tree/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2#31-verified-on-a-real-system-8-firmware-132),
  [slot and section tests](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol3_voice_allocation_scheduling/slot_program_model.md).

## Direct firmware comparisons

### APP0 and the groovebox C0A containers

The official 1.82 updates for [MC-101](https://static.roland.com/assets/media/zip/mc101_sys_v182.zip),
[MC-707](https://static.roland.com/assets/media/zip/mc707_sys_v182.zip) and
[VERSELAB MV-1](https://static.roland.com/assets/media/zip/mv1_sys_v182.zip) all
contain the same four partition types. Their C0A headers say `App1_Main` and
name destination `0x60000000`. The BMC container in
[SP stock 5.52](https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/)
also says `App1_Main` and names `0x01000000`. All 16 C1C files matched by
name and hash across the three grooveboxes. C0C had 12 matches between the
two MCs and 11 between MC-101 and MV-1. The two named C1A files had different
hashes in each comparison with MC-101.

On the 8-byte grid starting at file offset `0x60`, the opaque SP payload
shares the following distinct byte strings with each C0A payload. The byte
count comes from each file's little-endian word at `0x44`. Extra padding and
trailers are outside the comparison.

| Compared with SP 5.52 | 8-byte strings | 64-byte strings | 696-byte strings |
|---|---:|---:|---:|
| MC-101 1.82 | 2,839 | 899 | 1 |
| MC-707 1.82 | 1,708 | 388 | 1 |
| MV-1 1.82 | 2,995 | 1,002 | 1 |
| In all four | 1,008 | 294 | 1 |

The shared 696 bytes contain 239 distinct byte values. This supports a shared
firmware lineage and related container processing. The SP plaintext and the
BMC-side update checks were outside this comparison. For reproducibility,
use SP APP0 SHA-256 `3e35ff30137f741a715566e205384f9b434ca7ac3847e247bad3f0c9c8a2bd23`
and the three linked stock archives. Each archive contains an outer ZIP and
an inner update tar. For matching QSPI files, hash each directory entry's
payload by name. [Groovebox container layout](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/docs/firmware_format_and_contents.md).

### Shared DSP program memory

In stock MC-101 1.82, the ARM-side DSP copy routine at `0x0112C3D2` in
`idm1.bin` uses a literal at `0x0112C6A4` that points to a seven-entry
table at `0x01138164`. The entries match the independently documented
SYSTEM-8 program-memory windows for DSP0 through DSP5
(`0x41480000 + n * 0x100000`) and DSPM (`0x41260000`). The MC driver
also takes the upper halfword for a section whose byte length is 2 modulo
4. SYSTEM-8 readback and SP program storage show the same word order.
The SP ARM-side routine that consumes its catalogue remains open.
The MC `idm1.bin` SHA-256 is
`83405dd872528389ef95632c780bfab351c55e3186b3b8fb75e6eed73bdea37c`.
[SYSTEM-8 memory map](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol2_dsp_core_isa/memory_banks_dma.md),
[SYSTEM-8 program storage](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol4_firmware_container_protocol/plugout_virtual_machine.md#4-engine-region-1--dsp-programs).

### SP MFX with the DSP SDK

The SDK at revision `83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2` recognizes
the SYSTEM-1 opening marker in all 49 main SP 5.52 MFX programs. All 49 have
the closing sequence the SDK describes for SYSTEM-1 and SYSTEM-8. Reading to
the next 32-bit word exposes one trailing zero in 24 programs whose nominal
length is 2 modulo 4. The low five bits of each instruction header give its
length in 16-bit words. The test counted instructions across all catalogue
entries, including repetitions.

| Comparison of 5,249 instructions | Count |
|---|---:|
| Assemble back to original instruction words | 1,781 |
| Additional exact matches after normalizing memory transfer mode FF to FE | 3,247 |
| Still different after normalization | 4 |
| Kept as raw words by the disassembler | 217 |

The SDK documents FF and FE addressing as equivalent on its reference hardware,
and its assembler emits FE. The 5,028 matches after accounting for that
normalization are **95.8% under the comparison rule**. The byte-identical count
for original SP words is 1,781. To reproduce, follow the first descriptor of
each pair at `0x15D698` using `app0.pairs`. Interpret each little-endian
32-bit word in upper-halfword-first order, then compare each instruction with
`disasm.disassemble_insn` and `disasm.assembles_to` with its original class.
Count the documented one-word NOP as exact and the final zero as filler. In the
second pass use `dspref.layout` to identify transfer operands and normalize
the FF mode only in memory. [Instruction encoding](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol2_dsp_core_isa/instruction_word_encoding.md),
[transfer modes](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol2_dsp_core_isa/instruction_set_reference.md#9-transfers-and-memory).

With the same transfer alias in the in-memory DSP model, the stock SP Bypass
program passed isolated left and right test samples and scaled both by 0.5
when the test supplied that coefficient. The unadapted C model passed over
those transfers without doing I/O. For this test, inputs were model words
`0x2C00` and `0x2C01`, with the coefficient at `0xC800`. Output pairs
were read from model words `0x0C00`/`0x0C01` and `0x2C02`/`0x2C03`.
These are synthetic DSP memory locations used by the test. The SP's DSP
routing, sample scheduling, memory semantics and actual audio output need
their own observations.

### What Roland changed for DJFX Delay

Comparing stock SP 3.02 and 4.04 changed the two payloads for type 48 from
66/8 bytes to 1,398/48 bytes. The corresponding name in APP1 changed from
Torcido to DJFX Delay. Among types 0–48, only this pair changed. The stock
4.04 notes confirm the addition. The SP 3.02 catalogue scan also finds a
trailing pair beyond those 49 types. Across APP0 3.02, 4.04, 5.01, 5.50
and 5.52, the known CRC ends before the readable MFX region, as recorded in
`app0.crc`. The update may apply additional checks on the BMC side.
[Roland update history](https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/).

## What to trace on SP

The best leads are the SP ARM-side reader of the MFX descriptor, the copy
into DSP program memory, and the action that schedules the program. The
related devices give concrete signatures for the first two. Separate per-pad
processing also needs a route for each isolated signal and an independent
effect state. The current audio path mixes voices on the NXP before they reach
the BMC. Return slots that read zero on one unit provide no evidence of
assignable effect inputs or additional processing capacity. See
`st.audio.render`, `hw.periph.sai-dma` and `hw.bmc.rx-slots`.
An APP0 write, its acceptance on SP, and BMC recovery remain unverified.
