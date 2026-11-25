# APP0

Facts: `knowledge/facts/app0.json`. See [BMC across Roland devices](bmc-cross-device.md) for stock image comparisons, published DSP tools and the offline tests. The [APP0 update and recovery study](app0-update-safety.md) traces the stock updater. The [USB study](app0-live-observation.md) compares the editor port, the internal BMC log and SYSTEM-8 live readback. The [research credits](../../docs/SOURCES.md#roland-bmc-and-dsp-research) identify the projects behind those findings.

## What it is

The firmware of the second processor, the Roland BMC (`app0.what`). It ships beside APP1 in Roland update packages. The label
`App1_Main` inside the file does not make it main processor code. Known versions and hashes: `app0.versions`.

## What it does

Runs the built-in MFX effects: type numbers 0-48 in 5 slots, Input FX and BUS 1-4 (`app0.role`). APP1 selects a type and sends
parameters (`hw.bmc.sysex`). Parameter tables in APP1: `app0.params`. No program load was seen on an effect change
(`app0.no-runtime-load`).

## Hidden effects in stock 5.52

The stock APP1 has names and parameter records for both effects, and omits
both from its selection lists (`app0.hidden-types`).

| Effect | What the research established |
|---|---|
| COMPRESSOR 2 (type 29) | The maintainer used the findings documented in 404Lab to expose type 29 in the MFX grid of an experimental APP1 build. On one SP-404MKII, selecting it on BUS 1 produced audible changes with SUSTAIN, ATTACK and RATIO. APP1 selects the effect and supplies its parameters. The BMC runs the factory DSP program in APP0. See [the hardware record](../../docs/ON_A_UNIT.md) and `app0.type29-on-unit`. |
| Sub Sonic (type 45) | Stock APP0 5.52 stores its program and companion block at their own offsets. Both are byte-identical to Bypass (type 0). A separate sub-bass algorithm has not been identified for this slot. The file comparison leaves runtime parameter handling open. See `app0.pairs`. |

The first test of type 29 sent a type change alone and left the previous
effect's parameters active. The test recording matched the dry input.
The later grid test let the stock selection path send type 29's own
parameters. The grid and parameter paths are documented in `st.mfx.grid`,
`hk.recipe.mfx-grid-entry` and `app0.comp2-params`.

## How it reaches the chip

During a firmware update, the resident NXP updater UPD1 reads APP0 from the SD
root and forwards it over LPUART3. The host transfer is present in the UPD1
dump (`app0.upd1-transfer`) and in a service path in APP1 (`app0.transfer`).
In the UPD1 1.10 dump, the host forwards bytes on request and displays
`APP0 UPDATER OK` after the BMC completion reply. The receiver's checks and
persistent writes remain on the BMC side. See the
[UPD1 trace](app0-update-safety.md#what-the-stock-nxp-updater-checks).

## What is in the file

Map in `app0.layout`:

| Offset | Content |
|---|---|
| `0x000000` | readable header and descriptor |
| `0x000060` | opaque block, 310,160 bytes in 5.52, with matching 3DES metadata on related devices |
| `0x04BBF0` | tail with a version string |
| `0x140000` | readable program data and catalogue |
| `0x1F0000` | readable tables |
| rest | empty, all FF |

Evidence and uncertainty about encryption: `app0.encrypted`. Readable parts: `app0.readable`.

The header block carries a CRC-32 anyone can recompute (`app0.crc`). The catalogue and its descriptors: `app0.pairs`.

### Decryption attempt

Both published parsers located the same 310,160-byte block in SP 5.52.
Its header matches the documented 3DES mode and key slot `0xB6` in
MC-101 and SYSTEM-8. Both tools stopped for lack of compatible key
material and produced no validated SP plaintext. The published 238-byte
SYSTEM-8 startup excerpt provided no matching ciphertext blocks on the
SP's eight-byte grid. The APP0 header points to Thumb code as the likely
contents. The readable MFX programs lie beyond the closed block.
[MC-101 parser](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/tools/decrypt_c0a.py),
[SYSTEM-8 container reference](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol4_firmware_container_protocol/container_formats.md).

## For a mod author

- Read-only research can extend these findings. The current builder does not modify APP0; a recovery procedure after damaged APP0 is not established (`app0.recovery`). Keep APP0 writes out of ordinary mod experiments.
- Published tools for related Roland devices can decode much of the SP MFX catalogue. A local Bypass experiment ran in an adapted DSP model. Custom MFX on the SP itself remains unverified (`app0.dsp-sdk-roundtrip`, `app0.dsp-sdk-bypass`, `app0.own-effects`).
