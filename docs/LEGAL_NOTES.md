# Legal Notes

Reference notes on licensing and third-party boundaries (not legal advice).

## 404Lab

404Lab's original code, documentation, and structured facts are licensed under the [MIT License](../LICENSE). The MIT License does not apply to Roland firmware, third-party mods, or the external DM-404 emulator.

## DOOM OS

Per `LICENSE` in `github.com/klangfeld-labs/doom-os` `[DOC]`:
- Section 4 permits studying DOOM OS internals and applying knowledge learned about the SP-404MKII hardware and stock firmware in independent firmware work.
- Section 3 requires written permission to redistribute the patch, patcher, or patched firmware, or to modify DOOM OS, and prohibits copying or closely imitating DOOM OS code, screens, layouts, graphics, text, name, or logo.

Implications for 404Lab:
- Document DOOM OS behaviour in original words only; do not copy its manual, changelog, or screens.
- Custom mod UIs must follow Roland/hardware conventions rather than imitating DOOM OS screens or layouts.
- Users supply their own `APP1` image. Building a mod onto a DOOM OS `SP404MKII_APP1.bin` constitutes a modification of DOOM OS under Section 3 for the user's own device; redistribution of modified DOOM OS images is restricted unless authorized by the DOOM OS author (`lab@klangfeldlabs.com`).
- Older DOOM OS snapshots used MIT; the current license text governs current releases.

## Side-Piece

Per `freakierfirmware.com/terms` `[DOC]`: all rights reserved. Users may build and flash their own device, but may not redistribute patch data or patched builds. Do not store Side-Piece patch data in 404Lab; describe behaviour in original words only.

## Tampal

Per `tampal.petakajaib.com/legal` `[DOC]`: no license stated for Tampal's own code; some effects derive from MIT-licensed Airwindows code. Do not store Tampal patches or effect binaries in 404Lab.

## IrakliyMOD

Credits DOOM OS 0.6.1 and Tracelistener SG / Kits as MIT `[DOC]`; license terms for IrakliyMOD itself are unknown. Do not store its binaries or assets; describe observed features in original words only.

## SparkyMK2 and 404tui

Both projects are licensed under GPL-3.0-or-later `[DOC]`. Protocol facts, packet IDs, and file format layouts may be restated in original words with explicit repository and commit references ([SOURCES.md](SOURCES.md)); no code, documentation prose, or images may be copied into MIT-licensed 404Lab.

## Roland, NXP, Arm, and APP0

Roland firmware, update packages, bootloaders, and manuals belong to Roland. Nothing from Roland binaries or manuals is stored beyond original prose facts and SHA-256 byte fingerprints (`verify-knowledge`). NXP and Arm reference documents are linked by revision in [SOURCES.md](SOURCES.md); keep local PDF copies outside Git. `APP0` (BMC) documentation covers read-only analysis only (`REQUIREMENTS.md`).
