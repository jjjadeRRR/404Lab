# Roadmap

Development priorities for 404Lab focus on reproducible examples, closing knowledge gaps, and strengthening verification coverage. See [STATUS.md](STATUS.md) for current capabilities and [REQUIREMENTS.md](REQUIREMENTS.md) for project scope.

## Reproducibility & Examples

- Validate setup and example builds across clean environments (Linux, macOS, Windows/WSL) without local-only path assumptions.
- Add source examples covering audio-loop DSP hooks, custom screen rendering, persistent sidecar settings storage, and fault diagnostics.
- Design clean `mod.json` schemas and safety refusals for additional patch patterns as needed (e.g., runtime-rewritten veneers and data label tables).

## Knowledge Gaps

- Resolve high-priority unknowns tracked in `python -m lab404 gaps`: stack/heap low-water marks, stock CPU headroom under polyphonic load, key-sweep completion per screen, file operation atomicity, and `APP0`/BMC packet semantics.
- Maintain strict version and SHA-256 check boundaries across stock 5.52 and DOOM OS 0.7.2–0.7.4.

## Verification & Emulation

- Expand DM-404 checks to cover bit-exact idle audio comparisons, project save/load round-trips, modifier hold/repeat/release sequences, and internal state assertions beyond screen pixels.
- Support explicit expectation declarations for mods that intentionally replace stock controls or audio behaviour.
- Improve stand fidelity (FPU state, interrupts, DMA/cache coherence notes, reset paths) while keeping hardware-only boundaries explicit (real timing, BMC DSP output, physical SD cards).
- Collect independent hardware test reports from additional units to confirm single-unit observations.
