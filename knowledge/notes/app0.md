# APP0

Facts: `knowledge/facts/app0.json`. Read-only investigation and documentation are in scope. Hardware writes and recovery are separate questions; see [hardware hazards](../../docs/SAFETY.md).

## What it is

The firmware of the second processor, the Roland BMC (`app0.what`). It ships beside APP1 in Roland update packages. The label
`App1_Main` inside the file does not make it main processor code. Known versions and hashes: `app0.versions`.

## What it does

Runs the built-in MFX effects: type numbers 0-48 in 5 slots, Input FX and BUS 1-4 (`app0.role`). APP1 selects a type and sends
parameters (`hw.bmc.sysex`). Parameter tables in APP1: `app0.params`. No program load was seen on an effect change
(`app0.no-runtime-load`).

Stock selection lists omit types 29 (Compressor 2) and 45 (Sub Sonic).
Compressor 2 has its own program and worked on one unit once an experimental
APP1 offered it with its own parameters (`app0.type29-on-unit`).
Sub Sonic stores a separate copy of the Bypass program and companion data.
An [APP1 test](app1-sub-sonic-grid.md) exposed it in the grid and verified
selection on an emulator. Its sound on hardware remains untested.

## How it reaches the chip

The resident UPD1 updater forwards APP0 from the SD root in 4,096-byte
blocks (`app0.upd1-transfer`). APP1 has a separate service path that
also forwards the file over LPUART3 (`app0.transfer`). BMC-side
validation and recovery remain open. See [hardware hazards](../../docs/SAFETY.md).

## What is in the file

Map in `app0.layout`:

| Offset | Content |
|---|---|
| `0x000000` | readable header and descriptor |
| `0x000060` | opaque block, 310,160 bytes in 5.52, with 3DES metadata shared by related devices |
| `0x04BBF0` | tail with a version string |
| `0x140000` | readable program data and catalogue |
| `0x1F0000` | readable tables |
| rest | empty, all FF |

Evidence and uncertainty about encryption: `app0.encrypted`. Readable parts: `app0.readable`.

The known outer CRC-32 ends before the MFX catalogue (`app0.crc`).
See `app0.pairs` for catalogue descriptors.

## Research notes

- [Decryption report](APP0_DECRYPTION_REPORT.md) compares aligned ciphertext with four related Roland devices. Published MC-101 plaintext identifies 2,960 bytes of zeros. The SP ARM code remains unread.
- [Factory MFX updates](app0-factory-mfx-update.md) compares changes to APP0 and APP1 when Roland added DJFX Delay. An original replacement for the type 45 DSP program ran in the SDK reference model.
- [MFX selection trace](app0-mfx-selection-trace.md) compares the parameter map across both processors and identifies candidate Thumb function tables.
- [DSP prototype](app0-dsp-prototype.md) and [DSP audio addresses](app0-dsp-interface-trace.md) describe the Bypass control, the stereo saturation program and its gain behavior. The SP selector, signal routing and execution of custom DSP code remain unverified.
