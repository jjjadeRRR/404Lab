# What has run on a unit

What mods built with the methods in this knowledge base have done on a real SP-404MKII, and what went wrong there. Most of it
comes from the maintainer's private mod, DEEPCUT, on DOOM OS 0.6.1 to 0.7.4. The maintainer flashed and tried each build on one
unit between 2026-10-23 and 2026-11-23. The mod itself is not published: a build on DOOM OS is a change to DOOM OS, and its licence
restricts passing that on ([LEGAL_NOTES.md](LEGAL_NOTES.md)). What it learned is here in our own words, as facts you can ask for
with `python -m lab404 ask`. Some of it is an example you can build for stock 5.52 and DOOM OS 0.7.3 and 0.7.4.

Read each line as "this worked on that unit, as the owner checked it". It does not mean it works on every unit or every project.
The owner's own words, dates and build names are in each fact's evidence.

## Worked

| Function | What the unit showed | When, build | How (facts) | Example here |
|---|---|---|---|---|
| Fault screen | Three real faults photographed with PC, LR, CFSR and the address. Each one led to a stock bug | 2026-11-11 d73-G6, 2026-11-18 d74-H18, 2026-11-23 d74-H24 | `hk.fault-screen`, `hk.fault-visibility`, `hw.display.port` | [`mods/fault_screen`](../mods/fault_screen/mod.json), emulator only so far |
| An effect on each pad: low/high pass filter with resonance, sample-rate reducer, mono | "Everything is great"; settings kept across LOAD and power-off, also without an SD card | 2026-11-13 d73-H8c, kept to d74-H27 | `hk.recipe.pad-effects`, `hk.site.audio-voice`, `hk.storage.sidecar` | |
| Output meter: peaks, CLIP, loudness M, S and I | Integrated loudness matched a DAW loudness meter within rounding | 2026-11-14 d73-H16b | `hk.recipe.output-meter`, `hw.bmc.rx-slots` | |
| Mute groups of up to 32 pads, in two pages | "Works wonderfully" | 2026-11-13 d73-H6 | `hk.recipe.mute-32`, `st.mute.groups`, `st.mute.screen` | |
| COMPRESSOR 2 (stock MFX type 29) exposed by the DEEPCUT APP1 mod | On BUS 1, the BMC runs the factory DSP effect. SUSTAIN, ATTACK and RATIO audibly change the sound. In this build TONE had little effect and LIMIT muted the bus. | 2026-11-13 d73-H9 | `hk.recipe.mfx-grid-entry`, `app0.type29-on-unit` | |
| A monitor screen: audio load, peak, overruns, panel gap, CPU clock, malloc pool | Photos: audio 10 % average and 18 % peak, 599-600 MHz, 2.2 MB of the pool free | 2026-11-12 d73-H2b, 2026-11-19 d74-H23 | `hw.cycles.measured`, `st.mem.heap-measured`, `st.mem.heap-walk` | the pool walk is `Emulator.malloc_pool` |
| Reading the loader into a file on the SD card | The dump was read on a computer, the same bytes twice | 2026-11-12 d73-H3, d73-H4b | `hk.lesson.read-what-you-can`, `hw.boot.loader-image` | |
| A key chord that opens a stock screen | HOLD + ROLL opened SYSTEM and EXIT came back | 2026-11-23, built by 404Lab | `hk.lab404-build-on-unit`, `hk.open-screen` | [`mods/quick_system`](../mods/quick_system/mod.json) |
| Animated screensavers from a block of flash | Ran; broke once (d72-F6) and was fixed | from 2026-10, d74 included | `hk.region.flash`, `hk.site.saver` | |
| A game on the pads and the screen | Ran; a bug of the game itself: the pieces fell only when REMAIN was pressed | 2026-11-03 d72-F4 to F6 | `hk.site.tick`, `hk.site.draw` | |
| Chopping one sample to 32 pads with the stock chop screens | Works after several rounds; one fault at the third assign, traced to a stock jump to address 0 | 2026-11-17 to 2026-11-23, d74-H17 to H27 | `st.chop.*`, `hk.recipe.automark-32`, `st.chop.copy-null-check` | |

The latest build, d74-H27 on DOOM OS 0.7.4, runs on the owner's unit (2026-11-23). It also carries a fix for the stock screensaver
leak (`st.ui.saver-leak`); nobody has measured that fix on the unit yet.

On 2026-11-25, the maintainer confirmed that COMPRESSOR 2 functions in their
current DEEPCUT build on the same unit. The build identifier and current
LIMIT behavior were unspecified. See [the APP0 notes](../knowledge/notes/app0.md#hidden-effects-in-stock-552)
for the other hidden entry, Sub Sonic, and the file evidence for both.

## Did not work, or cost a lot

As useful as the table above: each line is a way not to go, or a reason for a rule in the tools.

| What | What happened | Facts |
|---|---|---|
| Delay and reverb on each pad | Too heavy: dropouts under load, a "metallic" reverb, crackle with two reverbs. Dropped | `hk.lesson.overload` |
| File work and memory allocation from drawing code | Crashes and hangs; they stopped once that work moved out of drawing | `hk.ctx.draw`, `hk.ctx.files` |
| A CPU guard that cut effect tails | The owner disliked it, and its load figure was wrong | `hk.lesson.overload` |
| Settings that needed the SD card | Without a card the effects locked up after LOAD. Since then a mod must never require a card | `hk.ctx.files`, `hk.lesson.sd` |
| A dying SD card | Hangs and failed starts that looked like a firmware fault, even on plain DOOM OS; and interrupted updates | `hk.lesson.sd`, `hw.update.stalled`, `hw.update.stalled-cause` |
| A chop screen written from scratch | Rejected: "worse than stock". The stock screens were reused instead | `st.chop.screens`, `st.chop.marker-screen` |
| An early build with pad animations | TRUNCATE worked only every other time, also with the animations off; the cause was not found. The rule since then: a mod must not break what works in stock | `hk.lesson.stock-first` |
| A change to the sample-rate reducer | Clicks at some settings, mostly around 5 kHz. Still open | |

## Bugs in the stock firmware found this way

- `st.import.malloc-unchecked`: the sample import writes through a null pointer when the malloc pool is short. Found from the fault screen.
- `st.ui.saver-leak`: the Custom screensaver keeps about 66 KB of the pool at every start. Found from the monitor screen, and
  measured again on unmodified stock 5.52 on the emulator.
- `st.chop.copy-null-check`: when the pad copy at the start of CHOP fails, the firmware jumps to address 0. Found from the fault screen.
