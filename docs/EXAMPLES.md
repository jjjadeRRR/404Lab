# Examples and research entry points

These are independent starting points, not a sequence every task must follow. Setup is in [README.md](../README.md); limits and known problems are in [STATUS.md](STATUS.md). Commands below run from the repository root with its Python environment active. `FILE`, `ADDRESS` and `SIZE` are placeholders for your own image and the location you are investigating.

## Find out what is already known

```bash
python -m lab404 topics
python -m lab404 ask "key event" --firmware stock-5.52
python -m lab404 ask --topic app0
python -m lab404 gaps
python -m lab404 check-keys stock-5.52 sample SHIFT LOOP
```

Questions in `gaps` are research leads. A particular experiment only needs the ones relevant to it. `check-keys` returns `occupied`, `free` or `unknown`; an incomplete record is not evidence that a key is free. It checks prefixes and gestures but does not model every repeat or release sequence.

## Investigate an image

```bash
python -m lab404 identify FILE
python -m lab404 map FILE
python -m lab404 read FILE ADDRESS SIZE
python -m lab404 dis FILE ADDRESS
python -m lab404 xrefs FILE ADDRESS
python -m lab404 find FILE TEXT
python -m lab404 verify-knowledge FILE
```

An unknown image can be investigated. The builder will not use it until support for that exact base is established; assigning a familiar version name is not enough. The APP1 image commands are not a BMC disassembler.

`xrefs` sees direct branches and pointer words, not every computed call. An empty result is not proof of no callers. `verify-knowledge` checks the recorded bytes for that image; it does not validate every prose claim.

A useful research result records the question, image/version and hash, method, observation, and remaining uncertainty. See [CONTRIBUTING.md](../CONTRIBUTING.md) for the fact format. A small local script or a comparison on the stand can be the entire experiment; no mod package is required.

## A minimal function-entry hook

[demo_counter](../mods/demo_counter/mod.json) counts calls to one function and adds no interface. Its [source](../mods/demo_counter/counter.c) and [scenarios](../mods/demo_counter/scenarios.py) show a small payload and exact comparisons.

With your own supported APP1:

```bash
python -m lab404 build mods/demo_counter SP404MKII_APP1.bin out/demo-1
python -m lab404 check out/demo-1 mods/demo_counter SP404MKII_APP1.bin
```

Each build uses a new output directory. `build` and `check` do not need interface approval, and their output alone is not a hardware-ready release. Read [SAFETY.md](SAFETY.md) before considering installation.

For another hook, `python -m lab404 check-hook FILE ADDRESS` checks the entry instructions and known references. Firmware functions called by the payload are declared in `firmware_symbols` in `mod.json`, with an address and a fingerprint of at least eight bytes read from the base: `"size"` and `"sha256"` from `python -m lab404 read FILE ADDRESS SIZE --sha256`. A private mod may give the bytes themselves as `"expect"`; shared examples use the fingerprint, so they carry no firmware. This prevents silently reusing an address whose contents differ.

Two kinds of hook exist. An `entry` hook (above) runs a mod function before a firmware function. A `word` hook repoints one aligned word that holds a code pointer, such as a vector, a table entry or a vtable slot, at a mod function:

```json
{"kind": "word", "address": "0x8021D018", "expect": "0x80072CF1", "function": "my_tick", "original": "stock_tick"}
```

`expect` is the value the word holds on that base (`python -m lab404 read FILE ADDRESS 4`). `original` is optional: it names the code the word pointed to, so the mod can call it as an ordinary function. The mod function is called exactly as the original would be, with its arguments and in its context, so it must keep the original's contract. The build refuses a word that does not hold `expect`, does not point to code, points to code that can erase the loader, or is a DOOM OS veneer word that DOOM rewrites while it starts (`hk.doom.veneers-rewritten`). Who else reads the word, and whether code writes it at run time, is not visible from bytes. Veneers, fixed-address modules and data tables are not implemented.

A third kind, `disable`, switches off a factory service routine that can erase the loader (`hw.service.loader-erase`): its first
four bytes become `movs r0,#0; bx lr`, so anything that calls it gets 0 back and nothing is erased. It takes only an address, which
must be one of the four entries in `lab404/image.py` `DISABLEABLE`:

```json
{"kind": "disable", "address": "0x80065838", "about": "service command that erases the loader: return at once"}
```

Nothing else may change inside guarded code; `check` reports which routines a candidate switched off (`loader-code`). The
maintainer's own mod has carried these four since 2026-11-11 and runs on a unit; the routines themselves are not reached in normal
use, so that shows the unit works with them off, not what a caller does with the 0.

## Kinds of change for a larger mod

Entry and word hooks cover small additions. A mod that changes how the firmware works, like the maintainer's own, also needs the
kinds below. Each is checked against the bytes of the user's image; `tests/test_jump_patch.py` and `tests/test_copy_flash.py`
use the private mod's real sites.

- **`jump`**: the firmware goes to a mod function and does not come back by itself. Use it to take over a piece of a stock
  function. The replaced instructions do not run again: the mod does their work, or jumps on to `resume`, a name the build gives
  the first address after them. Refused where anything branches or points into the replaced bytes past the first, inside an IT
  block, or in guarded code.

  ```json
  {"kind": "jump", "address": "0x80115334", "function": "draw_page", "resume": "after_draw"}
  ```
- **`patch`**: declared bytes become other bytes of the same length: an immediate, a limit, a table of pointers, calls made into
  NOPs. The build checks the image holds `before`, that no byte is in guarded code, that the new bytes neither branch into it nor
  hold a pointer to it, and on DOOM OS that no veneer word is covered. What the new bytes mean is the author's claim, to be tested.

  ```json
  {"kind": "patch", "address": "0x80115666", "before": "102e", "after": "202e", "about": "mute group limit: cmp r6,#16 -> #32"}
  ```
- **`copies`** (top level of `mod.json`): a stock function copied into the payload from the user's image, checked by SHA-256, so
  no firmware is kept in the mod. It keeps its address mod 4, so PC-relative literals still line up; branches leaving it go
  through veneers placed after it, or to a mod function named in `redirect`. `edits` change bytes inside it, as raw bytes or as a
  `movw`/`movt` aimed at a mod symbol. Refused: a PC-relative load of anything outside the copy, a `cbz`/`cbnz` or short branch
  that leaves it and cannot reach its veneers, and guarded code. Inline `tbb`/`tbh` tables are skipped as data.

  ```json
  "copies": [{"name": "transient32", "from": "0x8017C138", "to": "0x8017C768", "sha256": "f51213ad...",
              "edits": [{"address": "0x8017C368", "before": "b9f10f0f", "after": "b9f11f0f"},
                        {"address": "0x8017C17C", "before": "48f6e018", "movw": "am_list"}],
              "redirect": {"0x8017BA38": "level_block"}}]
  ```
- **`flash`** (top level): code and data that stay in flash after the image and run or are read in place, for pictures,
  animations and code that does not need SDRAM speed (`hk.region.flash`). It is linked together with the payload, so each can call
  and read the other; data files from the mod folder get a symbol and a `_end` symbol. The block must start after the image and
  end before `0x603FF000`; `check` compares its bytes with the manifest (`flash-block`).

  ```json
  "flash": {"address": "0x603C0000", "max_size": "0x1A000", "sources": ["screensaver.c"], "data": [{"file": "frames.bin", "symbol": "frames"}]}
  ```

Payload `data` files work the same way at the top level of `mod.json`.

A source can also be an object instead of a file name, for code that other code reaches by a literal address, or audio code that
needs the FPU: `{"file": "meter.c", "address": "0x83FD0400", "max_size": "0xC00", "flags": ["-O3", "-mfpu=fpv5-sp-d16",
"-mfloat-abi=softfp"]}`. A fixed object is laid out from its address; everything else flows around it; overlaps and a module larger
than its `max_size` are refused. `flags` accepts optimisation levels, the FPU and float ABI, `-ffp-contract`, jump tables and
`-DNAME[=value]`, nothing else. Data files take an `address` the same way (`tests/test_fixed_places.py`).

## A shortcut using a stock screen

[quick_system](../mods/quick_system/mod.json) and its [source](../mods/quick_system/quick_system.c) add HOLD + ROLL on the main screen to open the firmware's SYSTEM page. They illustrate observing events, restricting a feature to one screen and calling a guarded firmware symbol. The example has been exercised on stock 5.52 and DOOM OS 0.7.3 and 0.7.4 in the emulator. Its build on DOOM OS 0.7.4 passed the unit checks listed in its `mod.json` on one unit, once (`hk.lab404-build-on-unit`); stock and 0.7.3 builds have not been on a unit.

It can be built and checked like `demo_counter`. For screen and event experiments, [STAND.md](STAND.md) describes the external DM-404 emulator and the tests that exercise it. Inspecting existing examples does not require agreeing to use their interface in a new mod.

## A fault screen

[fault_screen](../mods/fault_screen/mod.json) and its [source](../mods/fault_screen/fault_screen.c) make a crash visible. The
firmware's fault handlers only return, so a fault leaves a frozen screen (`hw.faults.vectors`). The example points the four fault
vector words at its own handler with `word` hooks. The handler takes PC and LR from the exception frame, moves to its own stack, and
draws the kind of fault, PC, LR, CFSR and the faulting address straight into the display controller by polling its SPI port
(`hw.display.port`). Then it stands until the power is switched off. HOLD + ROLL on the main screen faults on purpose, to see it
work. Use it while developing a mod, and put the same handler into your own mod: a photo of the screen names the instruction that
failed. Three such photos found three stock bugs (`hk.fault-visibility`).

It has run on stock 5.52 and DOOM OS 0.7.3 and 0.7.4 in the whole-firmware emulator. The private mod it was adapted from showed real
faults on a unit; this build has not been on a unit yet.

## Optional packaging for conservative additions

`preview`, `approve` and `package` form one existing delivery route. It compares a fixed walk on the base and candidate, exercises declared inputs, and prepares a report and `UNIT_CHECKS.md`. It is designed for additions that preserve the checked base behaviour. It still refuses occupied controls and failed comparisons, even if a different behaviour was intentional. Arbitrary replacements need different validation that this route does not yet implement; do not disable checks to make such a mod appear to pass.

For `quick_system`:

```bash
python -m lab404 preview mods/quick_system SP404MKII_APP1.bin
```

After the person using the package has actually agreed to that interface, record their words with `python -m lab404 approve MOD_DIR --said "THEIR ACTUAL WORDS"`. Then:

```bash
python -m lab404 package mods/quick_system SP404MKII_APP1.bin out/quick-1
```

This command may refuse with named unknowns. It accepts `--drive IMAGE` for a project drive used through an emulator overlay. If the user accepts a remaining unknown, repeat with `--accept "EXACT CHECK NAME"` for each and `--said "THEIR ACTUAL WORDS"`. Acceptance records a decision, not proof; failures cannot be accepted. These conditions belong to `package`, not to reading, researching or prototyping.

## Intentional changes to behaviour

Changing an existing control or sound is a valid research goal. State what you intend to change, demonstrate it, and compare the behaviour you intend to preserve. Keep that result separate from a claim that all stock behaviour is unchanged. Examples and checks can evolve as new types of mod become understood.
