# Status

## Current State

404Lab provides a SHA-256-verifiable knowledge base (`knowledge/`), a C/JSON firmware mod builder and validator (`lab404 build` / `check`), an instruction-exact Unicorn stand (`stand.py`), and whole-firmware DM-404 integration (`emulator.py`, `preview`, `approve`, `package`, `sweep`). Two `SP404MKII_APP1.bin` candidates built with `lab404 build` on DOOM OS 0.7.4 have run on a reference SP-404MKII unit (`quick_system` and a full mod image with relocated AUTO MARK routines and screensaver flash data). Builds produced via `package` have not been tested on hardware.

## Firmware & Hook Matrix

| Capability | Coverage | Notes |
|---|---|---|
| `identify` | Stock 3.02–5.52, DOOM OS 0.6–0.7.4, Tampal | Hash-based identification; Side-Piece hash not yet recorded |
| `verify-knowledge` | Stock 5.52, DOOM OS 0.7.2, 0.7.3, 0.7.4 | 868 byte checks across stock and DOOM OS facts (208 checks on 0.7.4) |
| `mods/` examples | Stock 5.52, DOOM OS 0.7.3, DOOM OS 0.7.4 | `demo_counter`, `quick_system`, `fault_screen` verified on DM-404 |
| `package` route | Stock 5.52, DOOM OS 0.7.3, DOOM OS 0.7.4 | Verified on DM-404 for additive mods (`quick_system`) |

Supported `mod.json` patch mechanisms:
- **`entry`**: function-entry jump with displaced instruction validation.
- **`word`**: aligned code-pointer replacement (vectors, tables, vtable slots) with optional `original` trampoline.
- **`disable`**: `movs r0,#0; bx lr` at entry of the four routines in `lab404/image.py` `DISABLEABLE`.
- **`jump`**: one-way takeover of a stock function fragment with a `resume` target.
- **`patch`**: raw byte replacement at verified offsets outside guarded code and DOOM OS veneers.
- **`copies`**: SHA-256-verified stock functions copied into payload with `edits` and `redirect` branch veneers.
- **`flash` & fixed sections**: XIP flash blocks below `0x603FF000`, embedded binary data, and fixed-address objects (`-O3`, FPU, `-ffp-contract`, `-D` flags).

## Known Limitations

- **`check-keys`:** Binding files mark screens `partial`; missing entries report `unknown` rather than `free`. Key repeat and release sequences are not modelled.
- **`package`:** Designed only for conservative additive mods; intentional replacements of existing behaviour are refused. Audio bit-exactness, project save/load/transfer, and hidden firmware state remain `unknown` and require explicit acceptance.
- **Audio & display comparisons:** Pad audio comparison in DM-404 uses coarse peak matching, not bit-exact PCM. The START/END screen varies between boots (`PICTURE_VARIES`) and is skipped during replay comparison.
- **`quick_system` state:** Tracks `HOLD` from observed events; a missed release event leaves it armed, and calling `0x800DA598` is not verified across every firmware state.
- **Project drive fingerprinting:** `inputs/project-drive.img` is fingerprinted by size, mtime, and the first 16 MB.
- **Platforms:** Full test suite (including DM-404) runs on Linux. CI runs `--quick` on Linux, macOS, and Windows. DM-404 (`tools/setup_dm404.sh`) requires Linux (WSL on Windows) and is untested on macOS.
- **Orphaned QEMU processes:** Interrupted emulator runs may leave `qemu-system-arm` processes running (identifiable by `lab404-unit-` in the command line).
- **APP0 / BMC:** The DSP reference model runs a factory Bypass program and an original saturation program. Custom DSP execution on the SP and recovery from damaged APP0 remain unverified. [APP0 research](../knowledge/notes/app0.md).

## Directory Map

| Path | Contents |
|---|---|
| `lab404/` | Core CLI, builder, checker, image parser, Unicorn stand, DM-404 driver, pipeline |
| `knowledge/` | JSON facts (`facts/`), bindings (`bindings/`), observations (`observations/`), screens (`screens/`), notes (`notes/`) |
| `mods/` | Source mod examples (`demo_counter`, `quick_system`, `fault_screen`) |
| `docs/` | Technical guides, hardware findings, safety, stand boundaries, legal notes |
| `exam/` | Clean-agent evaluation task definitions (`tasks.json`) |
| `tests/` | Unit, boundary, release, knowledge, and DM-404 integration tests |
| `inputs/`, `private/` | Local gitignored directories for firmware images, `project-drive.img`, and scratch logs |
