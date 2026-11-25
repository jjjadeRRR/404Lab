# Scope and Evidence Model

404Lab is a research base and mod-building toolchain for the Roland SP-404MKII. It pairs versioned, machine-checkable firmware facts (`knowledge/`) with CLI tools (`lab404`) for analyzing images, building `SP404MKII_APP1.bin` candidates, and testing them in emulation.

## Project Boundaries

- **BYOF (Bring Your Own Firmware):** Users supply their own `SP404MKII_APP1.bin` images. The repository distributes no Roland firmware, proprietary mod binaries, or audio samples.
- **APP1 build target only:** Tooling builds and patches `APP1` images (`0x37F000` limit). `APP0` (Roland BMC) and hardware/board documentation are strictly read-only analysis; recovery after `APP0` writes is unestablished.
- **Multi-firmware knowledge:** Facts may cover stock firmware, DOOM OS, Side-Piece, Tampal, and other community mods in original wording with SHA-256 byte fingerprints (`verify-knowledge`). Documenting a firmware does not imply `build` support or redistribution rights.
- **Separate emulation levels:** Unicorn (`stand.py`) validates instruction-exact execution of isolated functions; external DM-404 (`emulator.py`) boots full `APP1` images for UI and integration testing.
- **Conservative packaging vs. general mods:** `build` and `check` apply to any supported `APP1` mod. `preview`, `approve`, and `package` target additive mods that preserve base behaviour and reject occupied controls or unintended diffs; intentional behaviour replacements require separate test declarations.
- **Independent verification:** An emulator pass validates only the tested scenario and never proves hardware correctness. Every built image remains a candidate until verified on a physical unit.

## Evidence Labels

| Label | Meaning |
|---|---|
| `[HARDWARE]` | Observed on a physical SP-404MKII unit, recording firmware, date, and test conditions |
| `[EMULATOR]` | Observed in a named Unicorn or DM-404 test |
| `[BYTES]` | Verified directly in the bytes of a named image (with address and SHA-256 check) |
| `[DOC]` | Cited from a named manual, datasheet, or specification (with revision and page) |
| `[HYPOTHESIS]` | Inferred or proposed; not yet established by bytes, emulation, or hardware |

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the JSON fact schema, [EXAMPLES.md](EXAMPLES.md) for CLI workflows, and [SAFETY.md](SAFETY.md) for hardware hazards.
