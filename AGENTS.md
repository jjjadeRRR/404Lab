# 404Lab Agent Reference

404Lab is a Roland SP-404MKII firmware research base and mod-building toolchain (`lab404`). Facts live in `knowledge/facts/*.json` with SHA-256 byte fingerprints and provenance labels; `lab404` builds and validates `SP404MKII_APP1.bin` candidates from C sources and `mod.json` manifests.

## Hard Constraints

1. **Protect `UPD1` and guarded service routines:** Never erase, write, patch, branch to, or hook the bootloader region (`0x60000000`–`0x6007FFFF`) or factory flash/update routines listed in `lab404/image.py` (`PROTECTED`). The only permitted modification in guarded code is a `disable` hook placing `movs r0,#0; bx lr` at the entry of the four routines in `lab404/image.py` `DISABLEABLE`. Keep APP0 writes and service update filenames (`docs/SAFETY.md`) out of mod builds, and keep all safety guards enabled.
2. **Validate every built `APP1`:** For every candidate produced by `build`, verify declared hook sites and `firmware_symbols` targets against the exact base image, run `python -m lab404 check`, confirm the image fits the `0x37F000` APP1 region, and verify no service update files are emitted.
3. **No third-party binaries or proprietary material in git:** Never commit firmware images, binary patches, samples, unit dumps, PDFs, or copied third-party code/assets (`docs/LEGAL_NOTES.md`, `tests/test_boundary.py`).
4. **Preserve strict evidence boundaries:** Separate `[BYTES]`, `[EMULATOR]`, `[HARDWARE]`, `[DOC]`, and `[HYPOTHESIS]`. Never present an emulator pass as hardware proof; any built `APP1` remains a candidate until tested on a physical unit.

## Key Paths & CLI

- `lab404/` — CLI, builder, checker, emulation stands and desktop preview (`gui.py`)
- `knowledge/` — JSON facts (`facts/`), key bindings (`bindings/`), observations (`observations/`), screens (`screens/`), and notes (`notes/`)
- `mods/` — source mod examples (`demo_counter`, `quick_system`, `fault_screen`)
- `docs/` — [EXAMPLES.md](docs/EXAMPLES.md), [SAFETY.md](docs/SAFETY.md), [STAND.md](docs/STAND.md), [STATUS.md](docs/STATUS.md), [ON_A_UNIT.md](docs/ON_A_UNIT.md), [SOURCES.md](docs/SOURCES.md), [LEGAL_NOTES.md](docs/LEGAL_NOTES.md)
- `tests/` — unit, boundary, release, and emulator test suites

Useful commands:
- `python -m lab404 doctor` — check local Python, `clang`, Unicorn, and DM-404 setup
- `python -m lab404 topics` / `ask TERM` / `gaps` — query facts and open research items
- `python -m lab404 verify-knowledge FILE` — verify SHA-256 byte checks against a local `APP1` image

## Testing & Local Directories

After `build` and `check` succeed, offer to open the new candidate in DM-404 with `python -m lab404 gui <output-dir>/SP404MKII_APP1.bin`. Use the APP1 path from the completed build. Add `--project PATH` if the user wants to test it with a local project or sample folder. See [desktop preview setup](docs/STAND.md#native-2d-preview).

- Quick suite (no DM-404 boot): `python tools/run_tests.py --quick`
- Full suite (includes DM-404 tests): `python tools/run_tests.py`
- Local firmware images belong in `inputs/` (or `LAB404_INPUTS`); local logs and scratch outputs belong in `private/` (both gitignored).
