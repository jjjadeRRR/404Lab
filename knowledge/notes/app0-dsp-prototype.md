# SP-404MKII DSP prototype and loader search

Recorded 2026-11-25. The experiment ran on a computer. It used the factory
Bypass program as a model calibration, rendered a new soft-saturation
program, and traced references in the stock APP0 files.

## Inputs

| Input | Version or SHA-256 |
|---|---|
| SP-404MKII stock APP0 | 5.52, `3e35ff30137f741a715566e205384f9b434ca7ac3847e247bad3f0c9c8a2bd23` |
| Other stock SP images used for the loader search | 3.02, 4.04, 5.01 and 5.50, identified in `app0.versions` |
| MC-101 `idm1.bin` | 1.82, `83405dd872528389ef95632c780bfab351c55e3186b3b8fb75e6eed73bdea37c` |
| Roland Plug-Out SDK | `83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2` |

[Stock SP update](https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/),
[MC-101 update](https://static.roland.com/assets/media/zip/mc101_sys_v182.zip),
[SDK revision](https://github.com/enorrmann/roland-plugout-reveng/tree/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2).

## Catalogue instruction encoding

All 49 stock 5.52 entries have the SDK's documented opening and closing
sequences. Follow each first descriptor from the catalogue at `0x15D698`
and read upper halfwords first in each little-endian word. Use the low
five header bits as the instruction length in halfwords. Compare
`disasm.disassemble_insn` and `disasm.assembles_to` with the original
instruction words. Count the documented NOP as exact and a final zero
halfword as filler. For the second pass, normalize only the FF transfer
mode to FE with `dspref.layout`.

Of 5,249 instructions, 1,781 reproduced the original words and 3,247
more matched after normalization. Four still differed and 217 remained
raw. This measures encoding agreement. Execution on the SP remains
unverified. [SDK instruction encoding](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol2_dsp_core_isa/instruction_word_encoding.md).

## Stereo soft saturation

Load the stock Bypass descriptor from the first pair of the 5.52
catalogue at file offset `0x15D698` using `app0.pairs`. Read each
little-endian 32-bit word in upper-halfword-first instruction order.
For model execution, use SDK `dspref.layout` to identify transfer operands
and normalize mode FF to FE in memory. Place the two input samples at
model words `0x2C00` and `0x2C01` and the gain at `0xC800`. For
Bypass, read left and right from both pairs `0x0C00`/`0x0C01` and
`0x2C02`/`0x2C03`. The unadapted model did no I/O on the FF transfers
in the earlier calibration.

The original saturation program loads one sample, multiplies twice to
form its cube, multiplies by `−1/3`, adds the result to the input and
stores it. Repeat for the other channel. On the interval `[-1, 1]`
this implements `y = x − x³/3`. The SDK assembler emitted 12 instructions
occupying 64 bytes. The same model inputs feed both tests. The saturation
program writes the first output pair.

```text
ld r0, [2c00]
mul r1, r0, r0
mul r1, r1, r0
mul r1, r1, #-0.3333333333333333:32
addxy r0, r0, r1
st r0, [0c00]
```

For the right channel repeat the block with input `2c01` and output
`0c01`. Assemble with the pinned SDK and execute one program pass per
stereo sample, then call `end_sample()` on the reference machine.

| Check | Result |
|---|---|
| Factory Bypass, six input values per channel and two gains (1 and 0.5) | Exact match for all 72 stereo cases, including the second output pair. |
| Saturation, 2,049 input levels tested left-only, right-only and as opposite-sign stereo | Maximum error `4.66e-9` against the formula, no signal on the idle channel and monotone, odd transfer. |
| Full-scale 1 kHz sine at 48 kHz | Fundamental amplitude `0.750000001`, third harmonic `0.083333330`, second harmonic below `1e-12`. |

The generated bass and percussion phrase repeats as Bypass, saturation,
Bypass, saturation. The saturated render was multiplied by `1.081932`
after DSP execution for RMS level matching. A second run produced the
same stereo 48 kHz, 16-bit, 9-second WAV byte for byte.

The generated WAV had SHA-256
`2ac6df2fabf8dafdf0c4651ad81cd1ee11058f0740db40b12d89873826916543`.
See `app0.dsp-sdk-bypass` and `app0.dsp-sdk-saturation`.
[SDK arithmetic and transfers](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol2_dsp_core_isa/instruction_set_reference.md).

## References to the DSP lists and closed code

In 5.52, little-endian words at file offsets `0x15D62C` and
`0x15D680` reference the DSP4 program and companion lists at
`0x146010` and `0x1460C8` using the `0xC0000` bias. They sit in
broader arrays just before the MFX catalogue. Searching the two readable
ranges `[0x140000, 0x15D828)` and `[0x1F0000, 0x237F48)` for
aligned literals for the MFX catalogue and register table with that
bias returned no hits. Computed references can fall outside this check.

Read the closed payload's length and destination from header offsets
`0x44` and `0x48`. In each of 4.04, 5.01, 5.50 and 5.52, the
39 little-endian words at `[0x205F78, 0x206014)` are distinct odd
values within that load interval. This is consistent with Thumb pointers
into the closed block. The latter two releases have identical entries.

| Stock version | Minimum pointer | Maximum pointer |
|---|---|---|
| 4.04 | `0x0101F321` | `0x0103C495` |
| 5.01 | `0x0101F32D` | `0x0103C4E5` |
| 5.50 and 5.52 | `0x0101F3F5` | `0x0103C635` |

In 3.02, a diagnostic string naming `bmc_dsp_drv.cpp` precedes the
matching register table at `0x205C5C`. In MC-101 1.82 the load
instruction at `0x0112C422` reads the literal at `0x0112C6A4`,
which points to the matching register table at `0x01138164` in
`idm1.bin`. This MC reference is a check that the compared table
belongs to a DSP driver there. The roles of the 39 SP addresses remain
unverified. See `app0.dsp-loader-trace`.
[MC-101 boot and memory study](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/docs/system_architecture_and_boot_flow.md).

The [MFX selection trace](app0-mfx-selection-trace.md#candidate-thumb-tables-on-the-bmc-side)
extends this check to the full set of groups preceding that register table.

The [DSP interface trace](app0-dsp-interface-trace.md) checks the input
and output addresses against all factory catalogue entries and adds
the Bypass gain operation to the model prototype.

## Open questions

The model runs the arithmetic in synthetic memory. The SP's routing,
timing and scheduling need direct SP evidence. The ARM routine that
selects the MFX descriptor and starts the DSP program remains unlocated.
The candidate Thumb addresses give specific places to check if the
closed block becomes readable. No temporary load path for a new MFX on
SP has been shown. See [hardware hazards](../../docs/SAFETY.md) for
the limits of APP0 recovery.
