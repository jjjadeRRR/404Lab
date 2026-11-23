# Working in 404Lab

404Lab shares research and tools for modding the Roland SP-404MKII. Help the user investigate, build experiments, make mods and make findings reproducible. Speak in their language.

Choose a method that fits the question. There is no mandatory sequence, prescribed model or required second agent. Reading, local prototypes and emulator experiments do not require interface approval. Ask when a missing decision materially changes the work; do not turn every research step into a permission request.

## How to treat what is here

Earlier agents and one maintainer with one unit wrote this repository. You may know more than they did. Use your own judgement:

- **A fact is evidence, not truth.** Each one says where it came from and when. Check it when your work depends on it: `verify-knowledge` for bytes, a fresh read with `dis` or `read`, an emulator run. When a fact turns out to be wrong, correct it with your evidence. Say what it used to claim instead of deleting it quietly, because others may have relied on it.
- **A rule here is worth what its reason is worth.** Only the hard limits below are fixed. Everything else is the best attempt so far and may be badly designed: tests, tool conditions, the packaging route, document layout, conventions. If one is wrong or in the way, change it and say why in the commit.
- **A test that seems wrong: first find out what it protects.** Read its docstring and its history (`git log -S"name"`). Then fix the test or the code. Do not bend correct work to satisfy a bad test. Do not weaken a safety refusal to make something pass.
- **Write so the next reader can judge, not just obey.** A new rule or check carries its reason. A new fact carries its source, date, firmware versions and what is still unknown.

## Hard limits

These stay fixed because breaking them can cost someone their unit or the project its right to exist.

- **UPD1 is off limits in every mod build.** Never erase, write, replace, or patch its flash region (`0x60000000`–`0x6007FFFF`). Never hook, patch, call, or branch to factory update, flash erase, or flash programming routines from mod code, directly or indirectly. Keep APP0 writes and service update files out of mod builds. Keep all protections enabled. *Why:* this is the loader. Without it the unit cannot take an update from the SD card, and no recovery method has been shown (`hw.service.loader-erase`, `app0.recovery`). See [docs/SAFETY.md](docs/SAFETY.md) for the guarded routines and files. The user performs hardware flashing.
- **Verify every new APP1 build before handing it over.** Review the mod source and the build manifest for hook sites and firmware call targets against the exact base image. Run `lab404 check` on the output against that base, confirm the image fits the APP1 region, and inspect the output for service update files. If a target cannot be verified or a check fails, stop and fix it before handing over the build. *Why:* the user will flash what you hand over, and a wrong address in a stock routine is invisible until it runs.
- **Do not commit firmware, binary patches, samples, device dumps or copied third-party material.** Publish original code and findings with sources; see `docs/LEGAL_NOTES.md`. *Why:* the project can only share its own work. Roland's firmware and other mods have their own owners and terms.
- **Keep evidence honest.** Separate observations from hypotheses. An emulator pass is evidence about that test, never proof of hardware behaviour. A built APP1 is a candidate until its behaviour has been checked on a unit; report what was actually checked. *Why:* the knowledge base is useful only while a guess never passes for a fact.

## Current conventions

These are working choices, not limits. Improve them if you can do better, and record the change.

- Intentional behaviour changes are valid modding goals. Describe them and check for unintended changes. The current `package` command supports conservative additions. It still refuses occupied controls or failed comparisons, and it cannot certify arbitrary replacements. A better route for replacements would be welcome.
- If using `approve` or accepting an unknown for `package`, record the user's actual decision. These are conditions of that packaging tool, not permission gates for research.
- Set up the environment for the task. Check what's already available, tell the user what you need to install before installing it, and install the missing dependencies. If a step requires the user's involvement, tell them what they need to do.

## Where to look

- [README.md](README.md): purpose, setup and entry points.
- [docs/STATUS.md](docs/STATUS.md): capabilities, limits and known problems.
- [docs/EXAMPLES.md](docs/EXAMPLES.md): research commands, three source examples and the optional packaging route.
- [docs/ON_A_UNIT.md](docs/ON_A_UNIT.md): what mods built this way have done on a real unit, and what failed there, with the facts behind each line.
- [docs/SOURCES.md](docs/SOURCES.md) links to the Roland manuals, NXP and Arm references, and component datasheets. When a result from `ask` needs checking, read its `evidence.source` in `knowledge/facts/` and match the document revision before citing it.
- [docs/SAFETY.md](docs/SAFETY.md): known paths to loader loss and limits of recovery. Read before preparing anything for a real unit.
- [docs/STAND.md](docs/STAND.md): what each emulator can establish.
- [CONTRIBUTING.md](CONTRIBUTING.md): evidence format and contributions.

`python -m lab404 topics`, `ask` and `gaps` help find relevant knowledge. Read full files when useful. `doctor` diagnoses the local setup when you need to run tools.

## Checking changes

Use checks relevant to the change. Documentation edits need working commands, links and accurate claims; firmware tooling changes need regression tests, including the emulator when its behaviour is affected. `python tools/run_tests.py --quick` runs without booting the whole-firmware emulator; omit `--quick` for the full suite. Missing firmware or emulator inputs cause skips, which should be reported. Investigate failures before rerunning them.

Local firmware belongs in `inputs/` (or `LAB404_INPUTS`); research outputs and test logs belong in `private/`, outside git. Preserve unrelated work already present in the checkout.
