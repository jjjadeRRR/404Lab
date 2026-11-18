# Research directions

404Lab develops through useful findings, reproducible examples and better tools. These are directions to choose from, not stages every contributor or agent must complete. [STATUS.md](STATUS.md) records what exists; [REQUIREMENTS.md](REQUIREMENTS.md) states the current scope.

## Make the existing work reusable

- Reproduce the documented setup and examples on a machine without the author's private working directories. Record missing dependencies and platform differences.
- Keep the knowledge base consistent as new observations qualify old claims. Preserve version and evidence boundaries.
- Make one small example easy for another researcher to understand, build, inspect and extend. Record any hardware trial separately from emulator results.
- Gather feedback from independent users of the tools and documentation. The original agent exam is historical evidence, not a current quality gate.

## Extend examples where there is a real question

Candidate examples include audio processing in APP1, drawing a screen, storing a setting and showing a fault. Add a new hook mechanism when an example requires it: vectors, veneers, fixed-address modules and data tables have different constraints from function-entry hooks.

Each example should explain its intended behaviour, supported bases, relevant resource/context assumptions, how it was tested and what remains unknown. Examples can stop at a local experiment. A candidate intended for hardware needs the separate considerations in [SAFETY.md](SAFETY.md).

## Research the unknowns

`python -m lab404 gaps` lists questions and possible approaches. Select those relevant to the experiment rather than trying to close the whole list first.

Useful areas include memory ownership, stack and heap use, timing under load, key behaviour, file operations and BMC communication. APP0/BMC file and board research can extend what is known without assuming that a key can be extracted or that a damaged BMC can be restored. Results may be positive findings or well-described limits of an attempted method.

## Improve checks according to the claims they support

For the existing conservative packaging route, desired coverage includes:

- Audio with the new feature unused compared bit for bit.
- Project save, load and transfer, including failures and readability by the base firmware.
- Controls across held modifiers, release, repeat, prefixes and screen contexts.
- Handler calls and internal state as well as visible screens and lights.

These are coverage goals, not claims about today's tests. The current gaps are in [STATUS.md](STATUS.md) and [STAND.md](STAND.md). Intentional replacements will need their own declared expectations and comparisons; the existing `package` command does not support that general case.

Potential stand improvements include task/FPU state, interrupts, voice routes, filesystem failures, DMA/cache effects and reset behaviour. Priorities depend on the mod being investigated. Instruction counts are not unit timing. The BMC is not faithfully modelled, so its effect output remains a hardware question.

## Share the project

Every release goes through [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md): a clean checkout with no private dependencies, only material the project can share, and the provenance and licence review. The maintainer decides when to publish.

A useful first release can have limited, explicit coverage. A complete firmware map, universal mod generator and prescribed agent workflow are not prerequisites for sharing original research and tools.
