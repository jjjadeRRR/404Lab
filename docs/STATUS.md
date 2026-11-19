# Status

Current capabilities and known limits. The project purpose is in `docs/REQUIREMENTS.md`; research directions are in `docs/PLAN.md`. Examples and hardware hazards have separate guides.

Last update: 2026-11-18. **Early work. No package built by these tools has been on a unit yet.**

The original development milestones below describe existing work, not a mandatory sequence for new tasks.

| Area | State |
|---|---|
| 0 Requirements | Done |
| 1 Inventory | Done, kept in `private/INVENTORY.md`, outside git |
| 2 Tool core | Done: identify, read, check hooks, link, build, stand |
| 3 Identifying APP1 | Done for images with known hashes. Side-Piece has no image yet |
| 4 Knowledge | Bindings of stock 5.52 checked against Roland's 5.x manuals and tried on the emulator. No screen marked complete |
| 5 Stand | Unicorn for exact checks, DM-404 for the whole firmware. Coverage and further directions are in `STAND.md` and `PLAN.md` |
| 6 Pipeline | Optional `preview`, `approve`, `package` route for conservative additions, with refusal regressions. `mods/quick_system` runs from APP1 to package on stock and DOOM OS on the emulator. Not tried on a unit. Hold-repeat analysis and three contract lines stay `unknown`. A new input is also pressed on four other screens (`contained`); other screens are not tried. Intentional replacements are not supported by this packaging route |
| 7 Exam | Historical run passed 9 of 9 and found 4 holes, closed. Its original workflow criteria are preserved in `exam/` and do not describe the current research approach. Independent-user validation of the new documentation remains open |
| 8 Publication | Repository prepared for a public release: provenance checks, CI for the quick tests, issue templates. The release itself is the maintainer's decision |

## What is new (2026-11-19): files and USB, from SparkyMK2 and 404tui

- The project file formats are now described: samples (`st.storage.smp`), PADCONF.BIN (`st.storage.padconf`), patterns
  (`st.storage.ptn`) and screen pictures (`st.storage.picture`). They come from SparkyMK2's specification and were checked on
  files the maintainer's unit wrote with stock EXPORT: 13 projects, all matching. Two of our byte facts are now confirmed
  from outside: the zeroed tail of each pad record and the 0x80-byte mark table, which PADCONF stores as it is.
- What SparkyMK2 could only guess, these files settle: the trailer of a pattern holds its length in bars.
- The USB side: the hub and its two devices (`hw.usb`), the serial link with its file API and status poll (`hw.usb.link`),
  and what the unit sends over USB MIDI (`midi.usb.observed`).
- A new hazard: a computer program could write update files to the SD card over USB (`hw.update.usb-card-path`, docs/SAFETY.md).
- SparkyMK2 and 404tui are GPL-3.0: their facts are restated in our own words with the revision read; no code or text taken.

## What is new (2026-11-18): CHOP, AUTO MARK and the marker screen

- How stock AUTO MARK works inside: the job and dispatcher (`st.chop.automark`), TRANSIENT and LEVEL with their thresholds,
  distances and the limit of 16 (`st.chop.automark-transient`, `st.chop.automark-level`), and a stock fault that adds a false
  LEVEL mark near the start (`st.chop.automark-level-extra-mark`). Overview: `knowledge/notes/chop.md`.
- The marker screen: object fields, zoom window, knobs, the window kept per mark, what it draws, the peak buffers and cache,
  chop playback and lights (`st.chop.marker-screen`, `st.chop.marker-drawing`, `st.chop.waveform`, `st.chop.play`,
  `st.chop.lights`). An older note that `0x800552F0` is a background job is corrected: it creates the screen object.
- Cutting runs in PANEL TASK and the display does not change while it does (`st.chop.job`, `st.ui.commit`).
- A pad hit is events 5, 16, 17 and 18; VOLUME goes through the key events on a unit (`hk.key-event`).
- Effect second pages and EFX SET rows (`st.efx.knob-pages`); a new open question, `ui.effect-cells`.
- `hk.recipe.automark-32`: more than 16 marks by moving the stock analysis code. Emulator only.
- Byte checks no longer store firmware bytes. All 851 checks in the knowledge base, the guards on the factory flash
  routines and the example mod's symbol now hold a size and a SHA-256 of the bytes instead
  (`read FILE ADDRESS SIZE --sha256`). They check the same thing on the user's image; `tests/test_boundary.py` keeps
  raw bytes out of shared records.
- All addresses re-read in stock 5.52 and DOOM OS 0.7.2 to 0.7.4 (identical bytes). Emulator results come from a private
  build on DOOM OS 0.7.4 that leaves this code stock. None of it was measured separately on a unit.

## What is new (2026-11-15): DOOM OS 0.7.4-651C

- `identify` knows DOOM OS 0.7.4-651C (`aaec78ad…`). Put it in `inputs/doom-0.7.4/` for the tests.
- **What changed from 0.7.3 is recorded, so a port starts from the record instead of a new study:** `hk.doom.074.diff`
  (the scatter table and every startup region are identical except 15 runs of DOOM's own places in the main code row),
  `hk.doom.074.veneers` (13 veneers instead of 11, two new ones, later ones and the trampolines after them moved +0x10),
  `hk.doom.074.moved` (tab-name string, key, LOAD and voice-launch handlers, VERSION constructor call) and
  `hk.recipe.port-073-074` (how a private 88-hook mod was ported: 85 stock hooks unchanged). `python -m lab404 ask --topic hooks`.
- 99 facts about stock 5.52 code that held on 0.7.3 now also name `doom-os-0.7.4`. Each one was taken over only when its
  addresses lie outside those 15 runs, and its 0.7.3 byte checks were copied only when 0.7.4 has the same bytes
  (`verify-knowledge`: 204 of 204 checks pass on 0.7.4). Facts about DOOM's own behaviour (MIDI, files, mods list) were not
  extended: they are not checked on 0.7.4.
- [EMULATOR] 0.7.4 boots on DM-404 and, like 0.7.3, rewrites the words of all its veneers to RAM while it starts and leaves
  the key trampoline `0x802097CC` alone: `tests/test_emulator.py` `DoomOs074AtRunTime`.
- Not established: anything on a unit with 0.7.4; what DOOM's two new hooks (`0x8004F414`, `0x80188874`) do. The
  `build`/`package` route of this repository was not tried on 0.7.4.

## What is new (2026-11-14)

- The maintainer shifted the focus to reusable research, documentation and examples. `AGENTS.md` is a short project map;
  `EXAMPLES.md` contains optional routes and `SAFETY.md` explains known hardware hazards. Tool protections and the existing
  packaging conditions are unchanged. Local research does not require interface approval or following a fixed dialogue.
- The comparison walk cannot pass when the candidate has not settled, even if a sampled frame matches. Different input sequences
  are refused. Tests: `ReplayVerdicts` in `tests/test_pipeline.py`.
- A package keeps the source hash that was checked and refuses if the mod sources change during the comparison. It no longer
  labels an older candidate with a newer source hash.
- Refusals and `UNIT_CHECKS.md` keep the reasons for failed or unknown checks. The three untested compatibility promises include
  practical checks and their limits. Acceptance is still required for each unknown; no failure can be accepted.
- Clock and cycle-cost records now refer to the existing measurement on one unit without generalising it to all units or stock.

## Knowledge transfer (2026-11-13/14)

- The MFX grid, its readers and limits, and the BUS 3/4 effect list are documented.
  COMPRESSOR 2 has a report from the maintainer's unit running a private mod; this is not
  a hardware test of a package built by 404Lab. See `app0.type29-on-unit`.
- The APP0 catalogue pairs, CRC, BMC packet dispatch, SHIFT reports, mute groups,
  CHOP marks, waveform path and chop job are recorded with their evidence.
- Follow-up byte checks separate the BMC FF/FE and FE/20 service packets and remove
  an unsupported length of 44 entries from the table at 0x8022E30C. The confirmed
  effect descriptor table is at 0x8021996C (`app0.params`); effect knob ranges are
  read from separate max/min tables (`app0.knob-ranges`).
- The SAI1/eDMA setup includes a receive path from the second processor
  (`hw.periph.sai-dma`); what it carries is open.
- The proposed APP0 block-pattern finding is still withheld pending the maintainer's
  decision. Other open questions remain visible through `gaps`.
- [Publication checks](RELEASE_CHECKLIST.md) cover local-data exclusions and running
  the README CLI examples. They do not grant permission to publish.

## Earlier changes (2026-11-12)

- **The loader was read.** A dump of the main processor's loader from one unit settled what it checks (nothing), what an update
  erases, how large APP1 may be, and which files brick a unit. Ten facts: `hw.boot.*`, `hw.update.*`, `hw.service.loader-erase`,
  `hw.boot.watchdogs`. The dump is the maker's code and is not here.
- **The tools refuse what can brick.** A hook or a call into code that erases the loader is refused (`image.protected`), a folder
  holding a file the loader would act on is refused by `package`, and the size limit that was already enforced now says why.
  The build manifest reports `flash_room_left`. Tests: `tests/test_safety.py`.
- **A register of what must be known.** `knowledge/required.json` lists what a mod author needs answered before building, tied to
  the facts that answer it; `python -m lab404 gaps` prints what is still open and how to find it out. Tests: `tests/test_gaps.py`.
- **Asking is easier.** `ask` takes words in any order, `ask --topic` lists a topic, `topics` shows what there is.
- First numbers from a unit: audio load and heap use (`hw.cycles.measured`, `st.mem.heap-measured`), and a stock crash on import
  when the heap is short (`st.import.malloc-unchecked`).

## What to do next

1. **Make the existing research and examples reproducible outside the author's setup.** Record the exact base, commands,
   observations and limits. Hardware trials are a separate source of evidence, not a prerequisite for sharing a useful local
   experiment. Further examples could cover audio, a custom screen, saving a setting and fault visibility. Source only, never a built APP1.
2. **More kinds of hook, as an example needs them.** Only function-entry hooks exist. Real mods also replace a word in a vector
   or veneer, take a word at run time and give it back, place a module at a fixed address, and add a table of labels. Design each
   from a working mod, with its own refusals and tests.
3. **Close the open items in `python -m lab404 gaps`**, the ones a mod can answer on a unit first: stack and heap low-water marks,
   block time on stock under load, and fault visibility.
4. **Finish the key sweep** so `check-keys` can answer `free`: no screen is marked complete on any firmware.
5. A full written map of APP1 (every task, every screen, every file routine) and of what can be read of APP0. The knowledge base
   holds hundreds of facts; what share of the firmware they cover has not been measured.
6. Feedback from independent users of the research tools and examples: evaluate their actual tasks rather than requiring the
   historical workflow exam. Reports from more units would turn many one-unit facts into general ones.

## Open holes in the tools

- Sound bit for bit, project save, load and transfer, and hidden firmware state are checked by no tool. `package` lists them as `unknown` and the user must accept each.
- The comparison walk compares settled states, not what happens between steps. The picture after START/END is skipped because it varies between boots.
- A mod's real keys in its code are not tied to its declared keys. Only the declared ones are demonstrated.
- `check-keys` does not model key repeat or release sequences.
- `quick_system` keeps HOLD's state from events. A lost release would leave it armed. Whether calling the screen function is safe at every moment is not checked.
- The project drive is fingerprinted by size, time and its first 16 MB.
- Development and the full suite run on Linux. CI runs the quick tests on macOS and Windows on every push; they first passed on 2026-11-19 and now block a change like Linux. The emulator build (`tools/setup_dm404.sh`) is not tried on macOS; on Windows the emulator needs WSL, and `Emulator` says so instead of failing on a missing socket type.

## Known problems

- `test_a_whole_task_from_app1_to_package_on_two_bases` errored once, in a full run whose output was filtered, so its text is lost. It passed alone. A defect that fits was found and closed: the START/END picture varies between boots of one firmware, which could turn a good candidate into a failure or an unknown (`PICTURE_VARIES`). That this was that failure's cause is [HYPOTHESIS]. Full runs now keep their log in `private/test-run-latest.log`.
- Closed: blank boots (1 frame, 0 lit). The emulator's stderr went to a pipe nobody read, and a boot writes about 20 KB. With the pipe set to 4, 8 or 16 KB the hang repeated every time, with the processor stuck in `anon_pipe_write`, the same state as the real failures; at the default 64 KB it did not [EMULATOR]. Output now goes to a file (`test_a_talkative_machine_does_not_stall_and_its_words_are_kept`). Why a pipe was sometimes small: probably the kernel's per-user pipe limit [HYPOTHESIS]. Sweep `run2` started before the fix and had such failures; `run3` repeated them on the fix, with none.
- `test_doom_opens_its_own_screen_and_stock_does_not` failed once in an earlier full run. A defect that fits was found and closed: "a still picture" counted as booted, and it stopped on a boot logo in 8 of 12 loaded boots with a project [EMULATOR]. That this was the cause of that one failure is [HYPOTHESIS]. Boots now wait for the main-screen page word (`Emulator.wait_for_main`).
- An interrupted run can leave `qemu-system-arm` processes running. They are safe to stop if their command line holds `lab404-unit-`.
- Peak comparison of pad sound is coarse, not bit for bit.

## Where things are

| What | Where |
|---|---|
| Tools | `lab404/` (`pipeline.py`, `observe.py`, `emulator.py`, `check.py`, `build.py`) |
| Knowledge base | `knowledge/` (facts, bindings, observations, screens), queried with `ask` and `check-keys` |
| What the stand can and cannot do | `docs/STAND.md` |
| Historical agent exam | `exam/`. Held-out tasks and reviews are in `private/`, outside git |
| Inputs and results outside git | `inputs/`, `private/` (sweep results in `private/sweep/`) |

## Local files, outside git

- `inputs/`: your own images, and an optional `project-drive.img`.
- `private/`: anything personal: handoff notes, reviews, sweep pictures, test logs.
- The whole-firmware emulator is built outside the repository by `tools/setup_dm404.sh`.
