# Factory MFX updates and a model replacement

Recorded 2026-11-25. Compared the stock SP-404MKII APP0 catalogues in
3.02, 4.04, 5.01, 5.50 and 5.52 and the APP1 name and parameter tables
in 3.02 and 4.04. Then ran one catalogue replacement on a computer
with the Roland Plug-Out SDK reference model.

## How 4.04 introduced DJFX Delay

| Field | Stock 3.02 | Stock 4.04 |
|---|---|---|
| APP1 label for type 48 | Torcido | DJFX Delay |
| APP1 parameter records for type 48 | 528 only | 535–545 |
| APP0 type 48 program and companion data | 66 and 8 bytes, identical to factory Bypass | 1,398 and 48 bytes |
| Total APP0 catalogue pairs | 50, including type 49 Image with another Bypass pair | 49, ending at type 48 |
| First program in the shared DSP4 list | 1,122 bytes | 1,140 bytes |
| Closed APP0 payload length | 324,368 bytes | 306,560 bytes |

The update used an existing type number for a different effect.
Types 0–47 kept their program and companion bytes, including Filter+Drive,
TimeCtrlDly, Isolator, Resonator and DJFX Looper. Roland's release notes
also list those five as additions to the MFX menu. In the files they
already had effect catalogue entries in 3.02. The full stock 4.04 update
includes changes beyond that catalogue, including the shared DSP4 program
and the closed ARM payload. The comparison cannot isolate which of those
changes the new effect depends on.
[Roland's 4.04 release notes](https://tr.roland.com/support/by_product/sp-404mk2/updates_drivers/508400).

All 49 catalogue program and companion pairs are byte-identical in
4.04, 5.01, 5.50 and 5.52. The first shared DSP4 program increases to
2,338 bytes in 5.50, a release that also introduced side-chain compression.
This comparison does not assign a role to the newly added DSP instructions.
[Roland's 5.50 release notes](https://tw.roland.com/support/by_product/sp-404mk2/updates_drivers/511053).

### Reproduce the factory comparison

- Compare the extracted factory APP0 files identified in `app0.versions`.
  The catalogue starts at file offset `0x15CB24` in 3.02,
  `0x15D1E8` in 4.04/5.01, and `0x15D698` in 5.50/5.52. Read one pair
  of descriptors per type, apply the usual `0xC0000` bias, and compare
  the two payloads by ordinal. Account for the high halfword executing
  first when a DSP program ends on a partial 32-bit word.
- In the APP1 scatter-copy section mapped at `0x80000000`, follow the
  label pointers from `0x801D2250` in 3.02 and `0x801F7660` in
  4.04. The parameter-range lists start at `0x801F2A70` and
  `0x80219740` respectively for type 1. Read consecutive triples of
  little-endian halfwords (first, last, last) to type 48 and count
  the records in each inclusive interval.
- The shared DSP4 program list starts at `0x145B24`, `0x145B60`
  and `0x146010` in 3.02, 4.04 and 5.50 respectively. Its second
  word is the first descriptor address. The second word of that
  descriptor gives the first program's length.

## An experimental update in the DSP model

The test follows the factory precedent of reusing a type number.
In a copy of the parsed 5.52 catalogue in memory, entry 45 (Sub Sonic)
changes from its 66-byte Bypass duplicate to an original 72-byte stereo
saturation program with the stock instruction framing. The eight-byte
companion and all other 48 pairs remain byte-identical. The test selects
the entry by index and runs the code through the reference interpreter.
Both model output pairs match the expected signal for 49 stereo inputs
before and after the change. The maximum absolute error for saturation
against `y = x − x³/3` is `3.73e-9`.

The [DSP prototype note](app0-dsp-prototype.md#stereo-soft-saturation)
gives the saturation instructions and SDK revision. The framed test
starts and ends with the stock Bypass instructions and writes each
channel to both output pairs listed in the
[DSP audio address trace](app0-dsp-interface-trace.md#direct-audio-accesses-in-the-stock-programs).

## What a device update still needs

The model supplies its own catalogue selection and audio routing.
For a real SP update, the BMC's program-copy and scheduling paths must
be traced, along with the image checks and recoverability of the update.
In particular, the change in the closed block in Roland's update leaves
open whether keeping the stock block would suffice for a new program.
The known outer CRC excludes the MFX region. The stock comparison and
model give no proof about additional BMC validation or recovery.
See [hardware hazards](../../docs/SAFETY.md).
