# 404Lab

**English** | [Русский](README_RU.md)

Open research and tools for Roland SP-404MKII firmware modding, ready for work with AI agents.

404Lab is two things in one repository:

- **A research base.** What is known about the hardware, the stock firmware and other mods, written as checkable facts. Every fact says where it comes from: read in the bytes of a named image, seen on the emulator, reported from a unit, taken from a document, or only a hypothesis. Byte facts can be re-checked on your own image with one command.
- **A workbench for building mods, with an AI agent or by hand.** An agent asks the knowledge base for what it needs (`ask`, `topics`, `gaps`) instead of reading everything. The tools identify your image, build a mod onto it, tie the result to its exact base and sources, run it on the emulator, and refuse known ways to brick a unit. Two small source examples show the whole route.

It is for mod developers, researchers and owners who want to change their instrument, alone or together with a coding agent of their choice. There is no mandatory agent workflow, and no promise that an arbitrary request can become a working mod without further research.

**Early research tooling.** The examples have been exercised on the emulator. One build of these tools (`quick_system` on DOOM OS 0.7.4) has passed its checks on one unit, once; nothing made through `package` has been on a unit. Most hardware facts come from one unit. See [docs/STATUS.md](docs/STATUS.md) for current capabilities and limits.

This project ships no firmware. You bring your own `SP404MKII_APP1.bin`. Unofficial: not affiliated with or endorsed by Roland.

## What is in it

| Part | What you can use |
|---|---|
| Image tools | Identify known firmware, read an image, and check a hook site against supported structural constraints |
| Build | Add a mod to an identified image. Every build gets a new folder and is never overwritten |
| Check | Tie a candidate to its exact base and sources, and report `pass`, `fail` or `unknown` |
| Optional packaging | A conservative route for additions: preview an interface, compare base and candidate, and prepare a package and unit checklist. It retains approval, failure and unknown checks |
| Knowledge base | The hardware, stock functions, other mods and key bindings as checked records, each with its evidence. An agent asks for what it needs instead of reading everything |
| Register of gaps | Open research questions, their relevance and possible ways to investigate them: `gaps` |
| Refusals | Checks for the loader's image-size limit, known destructive routines and dangerous package filenames; not a guarantee against every hardware failure |
| Exact stand | Runs pieces of firmware code on an emulated processor, for exact comparison of results |
| Whole-firmware stand | Boots the firmware on the separate [DM-404](https://github.com/nickpetty/dm-404) emulator, presses keys and reads its screen |

Documentation coverage, build support and hardware validation are separate. Knowledge of a firmware does not mean the builder supports it. `identify` knows stock 3.02 to 5.52, DOOM OS 0.6 to 0.7.4 and Tampal builds by hash. The knowledge base carries byte checks for stock 5.52 and DOOM OS 0.7.2, 0.7.3 and 0.7.4; the build examples target stock 5.52 and DOOM OS 0.7.3 and 0.7.4 (on 0.7.4 one build has run on a unit), and the builder accepts only declared, identified bases. Research directions are in [docs/PLAN.md](docs/PLAN.md).

## Start from an example or a question

- [Research commands and source examples](docs/EXAMPLES.md): inspect an image, reproduce a finding, or try `demo_counter` and `quick_system`.
- [Reference documents](docs/SOURCES.md) for stock controls and MIDI, the processor, and board components.
- [Hardware hazards](docs/SAFETY.md): known paths to loader loss and the limits of recovery.
- [The stand](docs/STAND.md): which questions each emulator can answer.
- [Contributing](CONTRIBUTING.md): add findings, corrections, experiments and tests.
- [Agent project map](AGENTS.md): a short orientation for an agent working in this repository.

## Trust

- **A stand pass is never proof that something works on a unit.** The result is always called a candidate. Timing, the sound of effects and real SD cards can only be checked on a unit.
- **`unknown` is not `free` or `pass`.** Where the project does not know, it says so. Each fact carries a label: `[HARDWARE]`, `[EMULATOR]`, `[BYTES]`, `[DOC]` or `[HYPOTHESIS]`.
- **Describe intentional changes and test for unintended ones.** Replacing a control or sound can be a valid modding goal. The current `package` route checks conservative additions and cannot certify arbitrary behaviour replacements. See [docs/EXAMPLES.md](docs/EXAMPLES.md).
- **You do the flashing.** The tools only prepare a file and instructions. You install it yourself, at your own risk. Back up your projects first.

## Try it

You need Python 3.10 or newer, and clang for `build`. The tools are plain Python. What works where:

| | Linux | macOS | Windows |
|---|---|---|---|
| Knowledge base: `ask`, `topics`, `gaps`, `check-keys` | yes | yes | yes |
| Image tools: `identify`, `map`, `read`, `dis`, `xrefs`, `find`, `verify-knowledge` | yes | yes | yes |
| `build` and `check` (needs clang) | yes | expected | expected |
| Exact stand (Unicorn) | yes | expected | expected |
| Whole-firmware emulator (DM-404): `preview`, `package`, `sweep` | yes | not tried | in WSL only |
| How it is tested | every change, full suite | quick tests in CI | quick tests in CI |

Development happens on Linux. CI runs the quick tests on macOS and Windows on every push; "expected" means the code is written for it but no person has reported it yet. Tell us what `doctor` says on your machine.

Linux and macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Then, on any system, ask what is still missing and how to get it:

```bash
python -m lab404 doctor
```

Working with an AI agent: open this folder in your preferred coding agent and describe the question or experiment. [AGENTS.md](AGENTS.md) points to the relevant documents. The agent can choose its method; interface approval is not required for reading, local prototypes or emulator experiments.

```bash
python -m lab404 identify SP404MKII_APP1.bin
python -m lab404 ask "skip" --firmware stock-5.52
python -m lab404 topics
python -m lab404 gaps
python -m lab404 check-keys stock-5.52 sample SHIFT LOOP
python -m lab404 verify-knowledge SP404MKII_APP1.bin
```

Build and check the small demo mod. It counts calls of one function and adds no interface:

```bash
python -m lab404 build mods/demo_counter SP404MKII_APP1.bin out/demo-1
python -m lab404 check out/demo-1 mods/demo_counter SP404MKII_APP1.bin
```

The optional packaging route needs the emulator. `mods/quick_system` adds one key chord that opens Roland's own SYSTEM screen. It has only been tried on the emulator. Start with its preview:

```bash
python -m lab404 preview mods/quick_system SP404MKII_APP1.bin
```

For actual approval and `package` usage, see [the example](docs/EXAMPLES.md). This tool requires the user's real interface decision and acceptance of each named unknown; it does not accept failures. `--drive` supplies an internal project drive image through an emulator overlay. Without samples, some checks can only answer `unknown`. These are conditions of this packaging route, not a procedure for every research task.

An unknown image can be investigated, but the builder refuses it until support is established for that base. The whole-firmware stand needs one more step, `tools/setup_dm404.sh`, which builds DM-404 outside this repository. See [docs/STAND.md](docs/STAND.md).

## Related projects

- [SparkyMK2](https://github.com/TuscanPL/SparkyMK2): an open editor and librarian that talks to the unit over USB, with a specification of the protocol and file formats.
- [404tui](https://github.com/moahbeatlab/404tui): a terminal workshop for samples, slices and patterns, built on SparkyMK2's protocol work.

They work from outside the unit, over USB; 404Lab works from inside the firmware. Their findings appear here as facts with their source ([docs/SOURCES.md](docs/SOURCES.md)).

## For agents

Start with [AGENTS.md](AGENTS.md). It names the few hard limits and their reasons. Everything else here, including facts, tests and tool rules, is earlier work to check and improve, not to follow blindly.

## For people

По-русски: [README_RU.md](README_RU.md). To add what your unit showed, a correction or a question: [CONTRIBUTING.md](CONTRIBUTING.md). Issues and pull requests are welcome; please never attach firmware, dumps or samples.

## Tests

```bash
python tools/run_tests.py --quick
python tools/run_tests.py
```

The first leaves out the tests that boot the emulator.

Tests that need firmware or the emulator skip when those are missing.

## Rights

- **Licence:** [MIT](LICENSE), for this project's own code and text. It gives no rights to firmware or to other people's mods.
- Roland firmware and manuals belong to Roland, and nothing of them is stored here beyond short facts in our own words.
- Other mods are described in our own words, and their files are not stored here. Their terms differ, and some do not allow changing or passing on a patched file. In particular, a mod built on a DOOM OS image is a change to DOOM OS, which its licence restricts. Read [docs/LEGAL_NOTES.md](docs/LEGAL_NOTES.md) before you build on another mod. This is not legal advice.
- DM-404 is a separate project under its own licences and is not included here.
