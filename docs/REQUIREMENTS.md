# Purpose and scope

The project began on 2026-11-09 as an agent-led mod-building workflow. On 2026-11-14 the maintainer shifted its focus to shared research, documentation, examples and tools. On 2026-11-18 the maintainer set its position as a hybrid of the two: a research base and a workbench for building mods with AI agents. This document records that direction; it is not a prescribed sequence for an agent.

## What 404Lab is for

Two parts, kept together:

- **Research:** make SP-404MKII research reusable and verifiable, so other mod authors can start from existing findings.
- **Agents and development:** make it easy to start building mods with an AI agent. The knowledge base answers an agent's questions with evidence and states what is unknown; the tools build, check and compare a mod and refuse known hazards.

The audience is developers, researchers and technically curious owners. People can use the tools themselves or with an agent of their choice.

Useful outcomes include a corrected fact, a documented unknown, a repeatable experiment, a source example, a test, or a firmware candidate. Producing an APP1 is one possible outcome, not the definition of a successful task. Documentation, build support and hardware validation have distinct coverage.

## Scope decisions

The D identifiers are retained for references from earlier documents. The current wording applies; git preserves the original decisions.

| # | Decision |
|---|---|
| D1 | Users supply their own firmware images. The project ships no firmware. |
| D2 | Share original code, tools, documentation and findings. Publishing the repository is the maintainer's decision. |
| D3 | APP0/BMC read-only research, file comparison and documentation are in scope. The tools do not build APP0 or establish recovery after BMC writes. A suspected protection mechanism remains a hypothesis until supported by evidence. Hardware writes are a separate task; see `SAFETY.md`. |
| D4 | The maintainer's private mod feature code remains outside the public repository. |
| D5 | Knowledge can cover stock, DOOM OS, Side-Piece, Tampal and other firmwares. Describing a firmware does not imply build support or permission to redistribute it. |
| D6 | Shared technical documentation is in English; a Russian introduction is provided. Agents speak in the user's language. |
| D7 | A general telemetry and SD-logging feature remains postponed. Recording observations from an experiment is still useful. |
| D8 | Unicorn supports exact function-level checks; the external DM-404 emulator supports whole-firmware experiments. Their boundaries are documented separately. |
| D9 | No particular model, second reviewer or agent arrangement is required. Choose review and tests appropriate to the work. |
| D10 | The project is named 404Lab; Python commands use `lab404`. |
| D11 | MIT covers this project's own code and text, not firmware or third-party materials. |

## Working principles

- Give findings enough context to reproduce: base/version and hash, method, addresses or inputs, observations and limits.
- Separate evidence from inference. A negative observation may mean the experiment lacked a necessary condition.
- Make known information easy to find; do not require reading the whole repository or forbid reading a relevant file in full.
- Choose experiments according to the question. Local prototypes can help discover requirements and interface possibilities.
- Ask for missing decisions when they matter. A task does not need a fixed dialogue or an approval at every stage.
- Intentional changes to sound, controls and other behaviour are legitimate goals. State them and test for unintended effects.
- Keep the known hardware protections documented and enforced. They are narrower than a guarantee that arbitrary code is safe.
- Report the boundary of each test. A passing emulator run never proves operation on a unit.

## Current packaging route

`build` and `check` can be used independently for supported APP1 experiments. `preview`, `approve` and `package` implement a more conservative delivery route for additions that preserve the checked base behaviour. Its interface approval and named unknown acceptance remain requirements of that command. Failed comparisons and occupied bindings are still refused.

The route is not a general validator for intentional replacements. Supporting those requires appropriate declarations and tests in future tooling, not silently skipping its refusals. Read-only work and local experiments do not need a package.

## Evidence labels

| Label | Meaning |
|---|---|
| `[HARDWARE]` | Reported by a person from a real unit, with conditions and scope |
| `[EMULATOR]` | Observed in a named test on the stand |
| `[BYTES]` | Read from a named image, with an address |
| `[DOC]` | Supported by a named document or page |
| `[HYPOTHESIS]` | Inferred or proposed, not established |

See [CONTRIBUTING.md](../CONTRIBUTING.md) for record structure, [EXAMPLES.md](EXAMPLES.md) for entry points and [SAFETY.md](SAFETY.md) for hardware hazards.
