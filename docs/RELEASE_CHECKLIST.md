# Release Checklist

Run these checks against the exact commit intended for release.

## 1. Repository Hygiene & History

- [ ] Verify `git status --short` and `git diff` contain only intended release changes.
- [ ] Inspect commit history (`git log --all --name-status` and `git log --all --format=fuller`) to confirm no firmware binaries, binary patches, dumps, samples, copied PDFs, `inputs/`/`private/`/`out/` files, absolute home paths, or personal email addresses were committed.
- [ ] Verify `docs/LEGAL_NOTES.md` and `knowledge/facts/mods.json` are the only files containing the documented DOOM OS licensing contact.
- [ ] Verify every contributed fact uses original prose and distinguishes `[BYTES]`, `[EMULATOR]`, `[HARDWARE]`, `[DOC]`, and `[HYPOTHESIS]`.

## 2. Automated Verification

Run the quick suite in the project virtual environment:

```bash
python tools/run_tests.py --quick
```

- [ ] Confirm `test_boundary`, `test_release`, `test_docs`, `test_knowledge`, and `test_gaps` pass.
- [ ] Run with stock 5.52 in `inputs/stock-5.52/` (or `LAB404_INPUTS`) so `test_release` executes the `README.md` CLI examples (`build`, `check`, `preview`) rather than skipping them.
- [ ] Run `python -m lab404 verify-knowledge FILE` against each supported local firmware image (`stock-5.52`, `doom-0.7.2`, `doom-0.7.3`, `doom-0.7.4`).
- [ ] When modifying `lab404/` tooling or emulator integration, run the full `python tools/run_tests.py` suite on Linux with DM-404 installed and record any skipped tests.

## 3. Documentation & Legal Review

- [ ] Confirm [STATUS.md](STATUS.md) and [STAND.md](STAND.md) accurately reflect current platform support, tool limits, and hardware verification status (e.g., whether `package` outputs have been tested on hardware).
- [ ] Confirm [LEGAL_NOTES.md](LEGAL_NOTES.md) reflects current third-party licenses, MIT scope, and Roland non-affiliation notices.
