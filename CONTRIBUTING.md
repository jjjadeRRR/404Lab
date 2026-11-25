# Contributing to 404Lab

Contributions include reproducible findings, fact corrections, source mod examples, tooling fixes, and hardware test reports.

## Adding a fact

Facts are stored in `knowledge/facts/*.json`. Each record states one claim in original wording with provenance:

```json
{"id": "hw.example", "claim": "Claim with exact addresses, sizes, and open boundaries.",
 "topic": "hardware", "firmware": "any", "status": "verified",
 "evidence": [{"label": "BYTES", "source": "stock-5.52: 0x80001234"}],
 "checks": [{"firmware": "stock-5.52", "address": "0x80001234", "size": 4, "sha256": "<64 hex digits>"}]}
```

- `status`: `verified`, `hypothesis`, `unknown`, or `disputed`.
- `evidence` labels: `HARDWARE` (physical unit observation with firmware version, date, and scope), `EMULATOR` (named test), `BYTES` (address in a named image), `DOC` (document title, revision, and page), or `HYPOTHESIS`.
- `checks`: store byte length and SHA-256 instead of raw firmware bytes so anyone can validate them locally with `python -m lab404 verify-knowledge FILE`. Generate the fingerprint with:
  ```bash
  python -m lab404 read FILE ADDRESS SIZE --sha256
  ```
  Use at least 8 bytes where possible so the fingerprint distinguishes adjacent routines.
- Update `knowledge/required.json` if the finding resolves or opens a tracked research question.
- Keep unit identifiers neutral (e.g., "one unit, once" or "reference SP-404MKII unit") without personal names, serial numbers, or local file paths.
- When correcting an inaccurate fact, update it with supporting evidence and note what changed and why; use `disputed` if sources conflict.

## What must not be committed

- Firmware binaries, update packages, binary patches, audio samples, project backups, or device dumps (`tests/test_boundary.py` rejects binary files and private directories).
- Text, graphics, layouts, or code copied from Roland manuals or third-party mods ([docs/LEGAL_NOTES.md](docs/LEGAL_NOTES.md)).
- Compiled `SP404MKII_APP1.bin` outputs (examples are shared as source code only).
- Instructions or configurations referencing service update filenames listed in `hw.update.whole-files` ([docs/SAFETY.md](docs/SAFETY.md)).

## Pull requests and verification

Run the quick test suite before opening a PR:

```bash
python tools/run_tests.py --quick
```

- When modifying `BYTES` facts, run `python -m lab404 verify-knowledge FILE` against your local image (CI runs without firmware images).
- When modifying `lab404/` tooling or emulator integration, run the full `python tools/run_tests.py` suite where DM-404 is available and report any skipped tests.
- Document intentional behaviour changes in mod examples alongside observed side effects.

## Reporting a hardware test result

Include:
1. Base firmware name and SHA-256 (`python -m lab404 identify FILE`).
2. Mod source revision and build manifest hash (`manifest.json`).
3. Step-by-step actions taken on the device.
4. Direct observations (screen photos, audio behaviour, crashes) separated from hypotheses about the cause.
