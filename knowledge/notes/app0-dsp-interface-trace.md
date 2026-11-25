# SP-404MKII DSP audio addresses and open APP0 references

Recorded 2026-11-25. Read stock APP0 3.02, 4.04, 5.01, 5.50 and 5.52
(`app0.versions`). Used the Roland Plug-Out SDK reference decoder at
`83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2`. All experiments ran on a computer.

## Direct audio accesses in the stock programs

All catalogue programs in the five releases contain these direct DSP
memory transfers.

| Access | DSP word addresses |
|---|---|
| Read the pair used as input in the model | `0x2C00`, `0x2C01` |
| Write the first output pair | `0x0C00`, `0x0C01` |
| Write the second output pair | `0x2C02`, `0x2C03` |

This covers 50 entries in 3.02 and all 49 in each later image. It checks
that those instructions exist, with no inference about which transfers
execute on each branch or where the physical signals go. For each image
use the catalogue offset in the
[factory MFX comparison](app0-factory-mfx-update.md#reproduce-the-factory-comparison).
Read upper halfwords first within each little-endian 32-bit word and
split instructions by the low five header bits. Use `dspref.layout`.
For a `T` unit with transfer mode FE or FF, use its slot selector to
resolve the address, and distinguish load from store using its register
selector. Undecoded layouts are skipped. In 5.52, this skipped 120 of
5,249 instruction layouts. The six required transfers were found in
the decoded portion of every program. The first shared DSP4 program
in each release yielded no direct FE/FF transfers at those six addresses.
That search leaves the scheduler's and main program's signal routing open.
[SDK transfer rules](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol2_dsp_core_isa/instruction_set_reference.md#9-transfers-and-memory).

Forty-five of the 49 stock 5.52 entries directly read word `0xC800`,
including Bypass and its duplicate Sub Sonic. The four without a
decoded direct read are types 2, 18, 29 and 36. The same four exceptions
occur in the earlier releases. The Bypass model scales its outputs by
the value at this word (`app0.dsp-sdk-bypass`). This leaves the APP1
parameter, if any, that sets this word on the SP unverified.

## Saturation with the factory Bypass scaling behavior

The existing [model replacement](app0-factory-mfx-update.md#an-experimental-update-in-the-dsp-model)
treated the gain as unity. For the follow-up, insert the following
two instructions before its first store.

```text
ld r4, [c800]
mul r0, r0, r4 | mul r2, r2, r4
```

With factory instruction framing, the result is 84 bytes. In the SDK
C interpreter, run stock type 45 and the new program separately at
gains 0, 0.5 and 1. Use all 49 stereo combinations of the values
−1, −0.5, 0, 0.125, 0.5, 0.75 and 1. Both output pairs agreed in all
147 cases per program. The original matched `gain × x` exactly. The
new program matched `gain × (x − x³/3)` to within `3.73e-9`.
This protects the observed gain behavior in the model, including silence
at zero gain. No route from the SP's controls to this word was tested.

## Addressing the open ARM data and looking for the selector

In 5.52, subtracting `0x00F10000` from stored words such as
`0x01100100` maps them to nearby open file data. For example, the word
stored at file `0x1F0120` points back to file `0x1F0100` under
that mapping. Require an aligned word in the readable data between
`0x1F0000` and the start of the function groups in the
[selection trace](app0-mfx-selection-trace.md#candidate-thumb-tables-on-the-bmc-side).
Count only words that map to a prior offset within that range by
exactly 20, 32 or 36 bytes. This gives 511 in 3.02 and 512 in each
later image. These self-relative records support the data base
`0x01100000` for file `0x1F0000` in the region tested. They leave
the complete runtime mapping open.

An aligned word search over the two open file regions looked for literal
references to each candidate function-table start and to eight bytes
before it, using both this data bias and the DSP file bias `0xC0000`.
There were no hits in the five releases. This excludes those
specific literal representations in the scanned regions. Computed
addresses and code in the opaque block are outside the check.

The three clear Thumb routines at file `0x140000`–`0x14000E`
are identical across the five versions. Capstone decodes each as
one operation (REV16, REVSH or RRX) followed by return. This check
provides no evidence of a selector among those helpers. A separate
exact-byte comparison of the 5.52 Bypass, Reverb, Compressor 2,
Sub Sonic and DJFX Delay programs found no complete match in the
stock 1.82 C1A archives of MC-101, MC-707 or VERSELAB MV-1. The
MC-101 driver study found a reference to the matching DSP register
table. See [references to the DSP lists](app0-dsp-prototype.md#references-to-the-dsp-lists-and-closed-code).

The direct DSP interface is now grounded in the factory programs.
The missing SP evidence is still the BMC ARM code that maps a type
number to a catalogue entry, installs it and schedules its execution.
