# APP0

Facts: `knowledge/facts/app0.json`. See [BMC across Roland devices](bmc-cross-device.md) for stock image comparisons, published DSP tools and the offline tests. The [APP0 update and recovery study](app0-update-safety.md) traces the stock updater. The [USB study](app0-live-observation.md) compares the editor port, the internal BMC log and SYSTEM-8 live readback.

## What it is

The firmware of the second processor, the Roland BMC (`app0.what`). It ships beside APP1 in Roland update packages. The label
`App1_Main` inside the file does not make it main processor code. Known versions and hashes: `app0.versions`.

## What it does

Runs the built-in MFX effects: type numbers 0-48 in 5 slots, Input FX and BUS 1-4 (`app0.role`). APP1 selects a type and sends
parameters (`hw.bmc.sysex`). Parameter tables in APP1: `app0.params`. No program load was seen on an effect change
(`app0.no-runtime-load`).

Types 29 and 45 exist only in tables and in no selection list (`app0.hidden-types`). Type 45 has the same program bytes as Bypass in a
separate file range. Three other pairs also have identical bytes stored separately (`app0.pairs`). Type 29, COMPRESSOR 2, has its own program and works on a unit once the MFX grid offers it
(`app0.type29-on-unit`); how the grid works and how an entry was added: `st.mfx.grid`, `st.mfx.grid-readers`, `hk.recipe.mfx-grid-entry`.
Sent alone, without its own parameters, it changed nothing.

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

## For a mod author

- Read-only research can extend these findings. The current builder does not modify APP0; a recovery procedure after damaged APP0 is not established (`app0.recovery`). Keep APP0 writes out of ordinary mod experiments.
- Published tools for related Roland devices can decode much of the SP MFX catalogue. A local Bypass experiment ran in an adapted DSP model. Custom MFX on the SP itself remains unverified (`app0.dsp-sdk-roundtrip`, `app0.dsp-sdk-bypass`, `app0.own-effects`).
