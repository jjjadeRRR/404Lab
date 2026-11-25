# Examples and Research Entry Points

Setup instructions are in [README.md](../README.md); capabilities and known limits are in [STATUS.md](STATUS.md). Commands run from the repository root with the Python environment active (`FILE`, `ADDRESS`, and `SIZE` denote local inputs).

## Querying the Knowledge Base

```bash
python -m lab404 topics
python -m lab404 ask "key event" --firmware stock-5.52
python -m lab404 ask --topic app0
python -m lab404 gaps
python -m lab404 check-keys stock-5.52 sample SHIFT LOOP
```

`check-keys` returns `occupied`, `free`, or `unknown`. Because screen binding tables are partial, `unknown` is not evidence that a control is unused; repeat and release sequences are also not modelled.

## Inspecting an Image

```bash
python -m lab404 identify FILE
python -m lab404 map FILE
python -m lab404 read FILE ADDRESS SIZE
python -m lab404 dis FILE ADDRESS
python -m lab404 xrefs FILE ADDRESS
python -m lab404 find FILE TEXT
python -m lab404 verify-knowledge FILE
```

Unidentified images can be inspected with read/disassembly commands, though `build` requires a supported, hash-verified base. `APP1` disassembly commands do not apply to `APP0` (BMC) images. `xrefs` detects direct branches and literal pointer words, not computed calls; `verify-knowledge` validates SHA-256 byte checks, not prose claims.

## Minimal Function-Entry Hook (`demo_counter`)

[demo_counter](../mods/demo_counter/mod.json) ([counter.c](../mods/demo_counter/counter.c), [scenarios.py](../mods/demo_counter/scenarios.py)) counts calls to a stock function without adding UI:

```bash
python -m lab404 build mods/demo_counter SP404MKII_APP1.bin out/demo-1
python -m lab404 check out/demo-1 mods/demo_counter SP404MKII_APP1.bin
```

Each `build` targets a new output directory. Read [SAFETY.md](SAFETY.md) before installing any candidate on hardware.

For custom hooks, `python -m lab404 check-hook FILE ADDRESS` validates entry instructions and cross-references. Firmware symbols called by C code are declared in `firmware_symbols` in `mod.json` using an address and an ≥8-byte SHA-256 fingerprint from `python -m lab404 read FILE ADDRESS SIZE --sha256` (local unshared mods may use `"expect"` raw bytes; shared mods use SHA-256 fingerprints so no firmware bytes are committed).

### Basic Hook Kinds (`entry`, `word`, `disable`)

- **`entry`**: redirects function entry to a mod handler before running displaced instructions.
- **`word`**: replaces an aligned code pointer (vector, table entry, or vtable slot) with a mod function, optionally preserving the original target via `original`:
  ```json
  {"kind": "word", "address": "0x8021D018", "expect": "0x80072CF1", "function": "my_tick", "original": "stock_tick"}
  ```
  `expect` matches the 4-byte word in the base image (`python -m lab404 read FILE ADDRESS 4`). The mod function must preserve the original calling contract. `build` refuses words that mismatch `expect`, do not point to code, point to guarded flash-erase routines, or sit in DOOM OS startup veneers (`hk.doom.veneers-rewritten`).
- **`disable`**: overwrites the first 4 bytes of a routine in `lab404/image.py` `DISABLEABLE` with `movs r0,#0; bx lr` so loader-erasing service commands return `0` immediately (`hw.service.loader-erase`):
  ```json
  {"kind": "disable", "address": "0x80065838", "about": "service command that erases the loader: return at once"}
  ```
  No other bytes in guarded code may change; `check` reports disabled routines under `loader-code`.

## Extended Patch Kinds (`jump`, `patch`, `copies`, `flash`)

Larger mods use additional mechanisms verified in `tests/test_jump_patch.py`, `tests/test_copy_flash.py`, and `tests/test_fixed_places.py`:

- **`jump`**: takes over a stock code block without automatic return. Displaced instructions do not execute; the mod can branch back to the generated `resume` label:
  ```json
  {"kind": "jump", "address": "0x80115334", "function": "draw_page", "resume": "after_draw"}
  ```
  Refused if branches or pointers land mid-replacement, inside an IT block, or inside guarded code.
- **`patch`**: replaces declared bytes of equal length (immediates, limits, pointer tables, NOPs), verifying `before` bytes, avoiding guarded code and pointers/branches into guarded code, and avoiding DOOM OS veneer words:
  ```json
  {"kind": "patch", "address": "0x80115666", "before": "102e", "after": "202e", "about": "mute group limit: cmp r6,#16 -> #32"}
  ```
- **`copies`** (top level of `mod.json`): copies a SHA-256-verified stock function from the user's image into the payload (preserving address mod 4 for literal alignment), routing outgoing branches through veneers or `redirect` targets and applying `edits` (`after` bytes or `movw`/`movt` symbol relocations). Refused for out-of-copy PC-relative loads, out-of-range short/`cbz`/`cbnz` branches, or guarded code; inline `tbb`/`tbh` tables are preserved as data:
  ```json
  "copies": [{"name": "transient32", "from": "0x8017C138", "to": "0x8017C768", "sha256": "f51213ad...",
              "edits": [{"address": "0x8017C368", "before": "b9f10f0f", "after": "b9f11f0f"},
                        {"address": "0x8017C17C", "before": "48f6e018", "movw": "am_list"}],
              "redirect": {"0x8017BA38": "level_block"}}]
  ```
- **`flash`** (top level): places XIP code and read-only binary assets in flash after the base image and below `0x603FF000` (`hk.region.flash`), linked with the payload and validated by `check` (`flash-block`):
  ```json
  "flash": {"address": "0x603C0000", "max_size": "0x1A000", "sources": ["screensaver.c"], "data": [{"file": "frames.bin", "symbol": "frames"}]}
  ```
  Build fingerprints cover files inside the mod directory plus external source files and project headers reported by Clang. Preprocessed `.S` assembly uses `#include` for headers and `data` for binary assets. Flash sources may contain code and read-only constants; place writable globals in payload sources. Top-level `data` entries work identically in SDRAM payload.
- **Fixed-address objects**: a source entry may specify `"address"`, `"max_size"`, and compiler `"flags"` (`-O*`, FPU with the base `softfp` calling convention, `-ffp-contract`, jump tables, `-DNAME[=value]`) for deterministic placement (e.g., audio routines using FPU):
  `{"file": "meter.c", "address": "0x83FD0400", "max_size": "0xC00", "flags": ["-O3", "-mfpu=fpv5-sp-d16", "-mfloat-abi=softfp"]}`.

## Stock Screen Shortcut (`quick_system`)

[quick_system](../mods/quick_system/mod.json) ([quick_system.c](../mods/quick_system/quick_system.c)) binds `HOLD + ROLL` on the main screen to open `SYSTEM`, demonstrating event observation, screen filtering, and calling a guarded stock symbol. Verified on DM-404 for stock 5.52 and DOOM OS 0.7.3–0.7.4; built and run on one hardware unit on DOOM OS 0.7.4 (`hk.lab404-build-on-unit`). See [STAND.md](STAND.md) for DM-404 testing details.

## Fault Screen (`fault_screen`)

[fault_screen](../mods/fault_screen/mod.json) ([fault_screen.c](../mods/fault_screen/fault_screen.c)) hooks the four fault exception vectors (`hw.faults.vectors`) with `word` hooks, switches to a dedicated stack, and renders fault type, `PC`, `LR`, `CFSR`, and fault address directly to the OLED SPI port (`hw.display.port`) before halting. `HOLD + ROLL` on the main screen triggers an intentional fault for testing. Verified on DM-404 across stock 5.52 and DOOM OS 0.7.3–0.7.4 (`tests/test_fault_screen.py`).

## Optional Packaging for Conservative Additions

`preview`, `approve`, and `package` compare settled states on DM-404 and generate `UNIT_CHECKS.md` for additive mods that leave checked base behaviour intact:

```bash
python -m lab404 preview mods/quick_system SP404MKII_APP1.bin
```

Record interface approval with `python -m lab404 approve MOD_DIR --said "<approval text>"`, then build the package:

```bash
python -m lab404 package mods/quick_system SP404MKII_APP1.bin out/quick-1
```

Pass `--drive IMAGE` to mount a project drive overlay in DM-404. Remaining `unknown` checks require `--accept "<CHECK NAME>"` alongside `--said`; failed checks cannot be accepted.

## Intentional Behaviour Changes

Mods that intentionally alter stock controls or sound should document expected changes explicitly and verify unaffected subsystems separately rather than bypassing `package` refusals.
