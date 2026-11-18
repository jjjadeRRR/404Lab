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

For another hook, `python -m lab404 check-hook FILE ADDRESS` checks the entry instructions and known references. Firmware functions called by the payload are declared in `firmware_symbols` in `mod.json`, with an address and a fingerprint of at least eight bytes read from the base: `"size"` and `"sha256"` from `python -m lab404 read FILE ADDRESS SIZE --sha256`. A private mod may give the bytes themselves as `"expect"`; shared examples use the fingerprint, so they carry no firmware. This prevents silently reusing an address whose contents differ. Currently only function-entry hooks are implemented.

## A shortcut using a stock screen

[quick_system](../mods/quick_system/mod.json) and its [source](../mods/quick_system/quick_system.c) add HOLD + ROLL on the main screen to open the firmware's SYSTEM page. They illustrate observing events, restricting a feature to one screen and calling a guarded firmware symbol. The example has been exercised on stock 5.52 and DOOM OS 0.7.3 in the emulator, not on a unit.

It can be built and checked like `demo_counter`. For screen and event experiments, [STAND.md](STAND.md) describes the external DM-404 emulator and the tests that exercise it. Inspecting existing examples does not require agreeing to use their interface in a new mod.

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
