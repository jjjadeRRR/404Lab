# Contributing to 404Lab

Contributions can be a reproducible finding, a correction, a small source example, a tool improvement, or **what your own unit showed**. Almost every `[HARDWARE]` fact here comes from one unit. You do not need to build a complete mod or follow an agent workflow to contribute.

## Adding a fact

Facts live in `knowledge/facts/*.json`. One fact is one claim, in your own words, with its evidence:

```json
{"id": "hw.example", "claim": "What is true, with addresses and numbers, and what is not known.",
 "topic": "hardware", "firmware": "any", "status": "verified",
 "evidence": [{"label": "BYTES", "source": "stock-5.52: 0x80001234"}],
 "checks": [{"firmware": "stock-5.52", "address": "0x80001234", "size": 4, "sha256": "<64 hex digits>"}]}
```

- `status`: `verified`, `hypothesis`, `unknown` or `disputed`. An honest `unknown` is welcome. A confident guess is not.
- `evidence` labels: `HARDWARE` (a person with a real unit: say which unit, when, and what was seen), `EMULATOR` (a named test),
  `BYTES` (an address in a named image), `DOC` (a named document and page), `HYPOTHESIS`.
- `checks` let anyone confirm a `BYTES` claim on their own image: `python -m lab404 verify-knowledge FILE`. A check stores the size and SHA-256 of the bytes, not the bytes, so no firmware is copied here: get both with `python -m lab404 read FILE ADDRESS SIZE --sha256`. Use 8 bytes or more where you can, so the fingerprint tells a function from its neighbours.
- If your fact answers a question in `knowledge/required.json`, update its `state` there. If you found a question nobody asked, add it.
- Say how many units and how many times. "One unit, once" is fine and must be said.
- Many facts say "the owner's unit" or "the owner's research stand": that is the maintainer's own SP-404MKII and local emulator setup. Name your own unit the same neutral way, without your name, serial number or personal paths.

## What never goes in

- Firmware, update files, patches, samples, projects, or dumps read out of a unit (loader, ROM, flash). Study them at home and
  write the facts in your own words. `tests/test_boundary.py` refuses binary files.
- Text, screens or code copied from Roland or from another mod. See `docs/LEGAL_NOTES.md`.
- A built `SP404MKII_APP1.bin`. Examples are source code; everyone builds on their own image.
- Anything that tells a user to put a file from `hw.update.whole-files` on a card.

## Examples

A useful example states its question, supported base and hash, commands to reproduce it, expected observations and limits. Include source code and the evidence needed to understand it. State intentional changes to stock behaviour rather than describing them as accidental incompatibilities. Keep hardware installation separate from local analysis and emulator experiments; see [docs/SAFETY.md](docs/SAFETY.md).

## Code and tests

```bash
python tools/run_tests.py --quick
```

For a bug fix, demonstrate the failure and add a regression test. Choose checks for the affected behaviour; documentation-only edits need accurate claims and working commands and links. Firmware tooling changes should run the relevant regressions and the full suite before a pull request, including the emulator where available. Report skipped tests. Investigate failures before rerunning them. Known destructive operations remain refused; changing prose is not a reason to remove those guards.

## Correcting a fact, a rule or a test

The knowledge base, the tools and the tests were written by earlier agents and one maintainer. Expect mistakes and improve them.

- **A wrong fact:** change it with your evidence and keep a sentence on what it said before and why that was wrong, so anyone who relied on it can see the change. Set `status` to `disputed` while two sources disagree.
- **A bad test or rule:** find out what it protects (docstring, `git log -S`), then fix or narrow it and give the reason in the commit. Keep the regression it caught if that still matters.
- **What stays:** the hard limits in [AGENTS.md](AGENTS.md) (hardware safety, no third-party material, honest evidence labels). A change to them needs a stronger safeguard in its place, not a weaker one.
- **For the long run:** give every source a date, name the firmware versions, and write what is still unknown. A fact that says how it was found stays useful after the tools around it change.

## Issues and pull requests

Open an issue for a question, a wrong fact or a result from your unit; the templates ask for what is needed. A pull request should say which checks you ran (`python tools/run_tests.py --quick` at least) and which tests skipped because firmware or the emulator was missing. CI runs the quick tests without firmware, so it cannot run the byte checks: run `python -m lab404 verify-knowledge FILE` on your own image when you change a `BYTES` fact.

## Reporting a result from a unit

Say the firmware and its SHA-256 (`python -m lab404 identify FILE`), the package you used, what you did step by step, and what you
saw and heard, separately from what you think caused it. A photo of the screen is evidence; a guess is a hypothesis.
