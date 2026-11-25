# Other firmwares: what they add and which keys they take

Written 2026-11-09 from each mod's own manual, changelog or site, in our own words. Fact ids `mod-*` in `facts/mods.json`; keys in
`bindings/<id>.json` (all `partial`, so `check-keys` says `unknown` for anything not listed: treat as taken). Mod firmware is not ours to
copy: do not store its patches, screens or text. No hardware tests are claimed here.

## Comparison

| | DOOM OS 0.7.3 | Side-Piece 0.1.0 | Tampal 0.1.0 | Etc (Sound Generator + Kits v9.46) | Tallfree | IrakliyMOD 0.10.62 |
|---|---|---|---|---|---|---|
| Maker | Klangfeld Labs | Freakier Firmware Labs | Petak Ajaib | tracelistener | Mudb0y | Irakliy |
| Base needed | stock 5.52 | stock 5.52 | stock 5.52, or a DOOM OS image 0.6.1 to 0.7.3 | stock 5.52 (contains DOOM OS 0.6.1) | stock 5.52 | stock 5.52 |
| Delivery | browser patcher, own APP1 | browser patcher, own APP1 | browser patcher or patch file, plus effect files on SD | browser patcher, own APP1 | release zip with APP1, APP0, engine file | prebuilt APP1 |
| Adds | sequencer, instruments, mixer, EQ, arp | per-bus FX stacks, LFOs, chop, ducker | 52 SD-card effects in the MFX menu | 4-voice synth, 13 drum kits, MIDI | screen reader | dual sample engines, LFO/motion, MFX reverb, synth/FM drums, MIDI looper |
| Own keys | REMAIN+SUB PAD, many inside | SHIFT+PATTERN EDIT, SHIFT+CTRL1/2/3, SHIFT+pad | none documented | SHIFT+PATTERN EDIT, SHIFT+RECORD SETTING | SHIFT+EXIT | RECORD SETTING+effect, Sound Generator keys |
| Licence | free use; no passing on, no changing | free; no sharing patch data or builds | none stated; effects free to copy | MIT (base DOOM OS 0.6.1 notice kept) | MIT | unknown |
| On a unit | author's own; ours not claimed | author's own unit and testers | stock, DOOM OS 0.7 and 0.7.1 only | partly, per author | not stated | not stated |

Note: Screen Loader (Freakier Firmware) is a tool for the stock opening-screen feature rather than firmware, and Roland's Sound Generator is a built-in stock 5.52 feature rather than a mod.

Combining: only Tampal is documented to sit on another mod. DOOM OS plus Side-Piece, or any other pair, is unknown (`mod-cmp-*`,
`mod-sipi-*-compat`). SHIFT+PATTERN EDIT is used by Side-Piece (FX screen), Etc (kits) and, inside DOOM OS, for NEW NOTES. A mod
that wants it must pick a base and check.

## DOOM OS 0.7.3

A heavily modified 5.52 that keeps all stock functions; REMAIN+SUB PAD opens its own world from any screen, EXIT leaves. Facts
`mod-doom-*`. Source: README, manual, CHANGELOG, LICENSE of the klangfeld-labs/doom-os repository.

- Grid sequencer: pads are 16 steps, VALUE picks the track, CTRL1/2/3 velocity, length, nudge (whole track, or one step if its pad
  is held), SHIFT+CTRL1/2 pitch and fine length on a held step. Five grid views. Piano roll on VALUE.
- Recording: REC rehearse then record, modes SINGLE, MULTI, CHROMATIC, 16 VEL (SHIFT+REC). SHIFT+PATTERN EDIT is NEW NOTES.
  SHIFT+pad 1 fixed velocity, SHIFT+pad 2 16 VEL, SHIFT+pad 9 metronome.
- 20 instruments and 11 kits via SUB PAD plus an empty pad; START/END editor; MARK for parameter locks; arpeggiator and PRINT ARP
  under RECORD SETTING; PATTERN EDIT tools; bounce in place on RESAMPLE; mixer (hold RECORD SETTING); per-pad EQ (PITCH/SPEED in
  the mixer); waveform overlay SHIFT+START/END; SIDECHAIN; FX Automation SHIFT+MARK; help mode on a 3 s SHIFT hold.
- Stock keys that change while DOOM OS is open: SHIFT+pad 13 is a step, UTILITY is REMAIN+PATTERN EDIT, SHIFT+REVERSE is not used
  for muting. Solo is SHIFT+ROLL; pad solo in the mixer is REMAIN+pad.
- Changes outside it: DOOM OS and SHORTCUT tabs in SYSTEM, boot animations, instruments saved as ordinary pad samples, pad EQ and
  mixer settings audible in stock screens, projects carry DOOM data, safer pattern save, a stock mono-recording fix.
- Eight user shortcut slots exist (SHORTCUT tab); their contents are unknown to any public text, so no combination is certain free.
- Disputes and gaps: undo depth (11 or 12), the manual is headed 0.7, no extension interface (planned only), licence history (MIT
  on old copies, restrictive now). 0.7.3 added a BINDINGS.DAT name to the image ([BYTES]).
- Licence consequence: a mod built on a DOOM OS image changes DOOM OS (section 3). Say so plainly to users. See `docs/LEGAL_NOTES.md`.

## Side-Piece 0.1.0 (build 14d, open beta)

Stock 5.52 only. Free, closed rights. Facts `mod-sipi-*`. SHIFT+PATTERN EDIT opens its FX screen (HOME menu) from the main
screen, SYSTEM, EFX SETTING, PAD SETTING and looper; EXIT returns. Four slots per bus on BUS 1 to 4 and DRY (filter, lo-fi, EQ,
chorus, phaser, delay, transient shaper), SHIFT+pad switches a stack, four LFOs, bus EQ, four Euclidean lanes, frequency chop (no
undo), own time-stretch, ducker and pump (SHIFT+CTRL1/2 on the main screen), input level (SHIFT+CTRL3), main-screen views, CPU
guard, picture source setting in SYSTEM, GENERAL. Settings are lost at restart. Unknown: which pads and how SHIFT+pad shares keys
with stock; how views change; sub-page keys; internals. Screens `sp-fx` verified, the rest `unknown`.

## Tampal 0.1.0

Adds 52 effects loaded from the SD card into the MFX menu on both buses, up to 32 at a time, in packs Dynamics (13), Colour (22),
Space and time (17); six knobs per effect. Works with stock 5.52 and DOOM OS 0.6.1 to 0.7.3; only stock, 0.7 and 0.7.1 have run
on a unit. No keys of its own. Unknown: how knobs 4 to 6 are reached, how it numbers MFX slots. No bindings file, because it
documents no keys. Facts `mod-tampal-*`.

## Etc (Sound Generator + Kits)

Extends the stock Sound Generator: four voices, 17 waves, nine envelope presets, 34 scales, arpeggiator, MIDI in, plus 13
drum-machine kits (SHIFT+PATTERN EDIT, back with SHIFT+RECORD SETTING). Based on DOOM OS 0.6.1. Settings reset at power-on.
Author reports partial hardware play. Facts `mod-etc-*`; bindings are relative to stock only (the DOOM OS 0.6.1 layer is not in
`bindings/`).

## Tallfree

Screen reader for blind users: speaks titles, items, values, tabs, dialogs, bank letters, effect names and button states.
SHIFT+EXIT opens speech settings (stock lists SHIFT+EXIT on the main screen too; the overlap is unresolved). Costs half of the
looper and skip-back buffer (27.3 s to 13.65 s per channel). Stock APP0 is shipped unchanged inside the release. Facts `mod-tallfree-*`.

## IrakliyMOD 0.10.62

Known only from its own page, read 2026-11-09. No image has been read, so nothing is checked against bytes. Facts `mod-irakliy-*`, keys `bindings/irakliymod.json` (partial, so anything not listed answers `unknown`).
Ships as a ready-made APP1 for stock 5.52. It adds two sample engines on START/END, an LFO and motion recorder for effect parameters, a reverb in the MFX list, a synth and FM drums on the Sound Generator page, scales and arp, a MIDI looper, and bounce to pad.
It takes RECORD SETTING + effect button from the main screen, and several inputs on the Sound Generator page. Terms of the mod itself: unknown.
