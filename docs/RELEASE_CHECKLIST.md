# Before publication

Use this checklist for the exact revision intended for release. A passing check
does not publish anything, establish third-party permission, or prove hardware
behaviour. Publication still requires the maintainer's decision.

## Files and provenance

- [ ] Review `git status --short` and the intended diff. Keep unrelated local work
  out of the release commit.
- [ ] Run the checks below. They inspect tracked files and unignored new files:
  no firmware, binary patches, samples or copied PDFs; no files under `inputs/`,
  `private/` or `out/`; no absolute home paths or unreviewed email addresses.
- [ ] Review all history that will be published, not just the working tree:
  `git log --all --name-status` and `git log --all --format=fuller`.
  The automated working-tree scan does not inspect old blobs, commit messages or
  author addresses. Use the maintainer's chosen public author identity.
- [ ] Inspect the actual release archive and attachments separately. Local logs,
  emulator drives, screenshots of third-party interfaces and firmware outputs
  must not be added to them.
- [ ] Review the source of every contributed finding. Facts use original wording;
  bytes, emulator observations, reports from units and hypotheses remain distinguishable.

The public DOOM OS licensing contact is allowed only in `LEGAL_NOTES.md` and its
existing licence fact in `knowledge/facts/mods.json`. This narrow exception does
not allow personal author addresses elsewhere.

## Reproducibility

Activate the environment described in [README](../README.md), then run:

```bash
python tools/run_tests.py --quick
```

Relevant checks included in this command:

| Check | What it establishes |
|---|---|
| `test_boundary` | Binary/material exclusions and dependency boundaries |
| `test_release` | Private-directory, home-path and email checks; non-interactive CLI examples from README executed with their arguments |
| `test_docs` | README command help, local links, MIT licence and attribution statements |
| `test_knowledge`, `test_gaps` | Fact format, byte checks where images exist, references from research questions |

- [ ] Run the README CLI examples with stock 5.52 available in `inputs/stock-5.52/`
  (or `LAB404_INPUTS`). `test_release` substitutes that image and a temporary build
  destination; it runs `build`, `check` and `preview` without flashing or recording
  approval. A missing image skips this test and is not a successful example run.
- [ ] Review every reported skip. Identify which images and emulator inputs were
  present in the test report.
- [ ] Verify knowledge against each supported local image using
  `python -m lab404 verify-knowledge FILE`, replacing `FILE` with its path.
- [ ] If firmware tooling or emulator behaviour changed, run
  `python tools/run_tests.py` as well and retain the full log in `private/`.
- [ ] Before claiming support on a new operating system, follow its installation
  instructions on that system. Tests do not reinstall dependencies, create a new
  environment, build DM-404 or run PowerShell setup. Linux results do not establish
  Windows or macOS support.

The README test executes only its recognised `lab404` examples. New command kinds
require review before they can run in that test. The two test-runner commands are
run separately to avoid recursively invoking the suite. If README includes
`approve` or `package` examples, only their help is run: example wording is not
anyone's approval. Packaging behaviour is covered by the pipeline and emulator
tests; a real package requires the user's actual decision.

## Documentation and release decision

- [ ] Read [status](STATUS.md) and [stand limits](STAND.md). Keep the distinction
  between tests of these tools and hardware reports from private research builds.
  No package made by 404Lab has yet been reported tested on a unit.
- [ ] Review [legal notes](LEGAL_NOTES.md) and the current original licences before
  release. MIT covers this project's own work only. Check third-party attribution,
  use of names and logos, and the statement that the project is unofficial and not
  affiliated with Roland. The tests check documentation consistency, not legal
  permission.
- [ ] Resolve withheld findings with the maintainer before including them.
  Use the dated [APP0 research](../knowledge/notes/app0.md) for the current
  stock-file comparisons and their limits.
- [ ] Record the exact commit, checks, skips, known limitations and the maintainer's
  publication decision. Do not infer permission to push from a local commit.
