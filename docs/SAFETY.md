# Hardware Hazards and Recovery Limits

Read-only analysis and emulator testing do not establish that a hardware flash write is safe or recoverable.

## Known Hazards

Query any fact ID with `python -m lab404 ask FACT_ID` for full provenance and affected firmware versions.

| Operation | Risk | Current Protection |
|---|---|---|
| Oversized `APP1` | The bootloader erases only `0x37F000` bytes for `APP1` and does not validate the incoming file length (`hw.update.app1-range`). | `build` and `check` enforce the `0x37F000` flash ceiling. |
| Calling or hooking factory flash routines | Service routines in `APP1` can erase or overwrite the bootloader (`hw.service.loader-erase`), removing SD-card update capability. | Protected addresses in `lab404/image.py` (`PROTECTED`) are refused by hook and symbol checks. The sole exception is `disable` (`movs r0,#0; bx lr` at entry) on the four routines in `DISABLEABLE`. |
| Service or whole-flash update files | `SP404MKII_APP1W.bin` can overwrite the bootloader; other service filenames trigger poorly understood update paths (`hw.update.whole-files`). | `package` and `check` reject listed dangerous filenames in mod and output directories. |
| SD card writes over USB | The USB serial file API accesses the SD card root, making it theoretically possible for a host tool to place a file from `hw.update.whole-files` on the card (`hw.update.usb-card-path`, hypothesis). | 404Lab does not write over USB. Host tools writing to the card must enforce the same filename blocklist. |
| `APP0` / BMC writes | No recovery procedure is established if the second processor's firmware is damaged (`app0.recovery`); `APP1` recovery does not imply BMC recovery. | Tooling builds `APP1` only and rejects `APP0` and service update files. |

Blocked filenames: `SP404MKII_APP1W.bin`, `SP404MKII_APP0W.bin`, `SP404MKII_APP1U.bin`, `MIRXRT1060-EVK.bin`, `TD003_ROM.bin`, and `SP404MKII_APP0.bin` (official secondary processor firmware, excluded from mod packages to avoid unintended BMC flashes).

Do not bypass guards by renaming files or disabling safety checks. Low-level recovery research requires identified chips/interfaces, verified external backups, and an established recovery path before performing destructive writes; an external programmer or dump alone does not prove recovery.

The tool generates `SP404MKII_APP1.bin` for manual installation via SD card. Before testing any candidate on hardware, keep a verified copy of the stock `SP404MKII_APP1.bin` and back up all projects externally.

## Verification Boundaries

Automated checks inspect declared hook sites, symbol fingerprints, and structural bounds. They do not perform full static analysis of arbitrary C code, track every computed indirect call, or prevent logic hangs and data corruption. Real-time audio deadlines, DMA/cache interactions, SD card faults, and BMC behaviour cannot be fully validated in emulation ([STAND.md](STAND.md)).

## APP0 Research

Read-only `APP0` disassembly, table comparison, and BMC serial protocol analysis are within project scope ([knowledge/notes/app0.md](../knowledge/notes/app0.md)). Keep hypotheses explicitly labelled and separate from hardware-verified claims.
