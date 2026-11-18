# Stock 5.52: functions, screens, keys (quick map)

> Status rule: `verified` needs Roland's own manual for 5.x (or two independent sources for 5.x). Key bindings were checked on 2026-11-09
> against two Roland manuals: the "Version 5" Reference Manual (eng03, no side chain) and the 5.50 Reference Manual (eng04, downloaded
> from Roland's site). Roland's update history says 5.51 only fixes bugs and 5.52 only changes the version number, so the 5.50 key
> list is taken to hold for 5.52. Nothing here has been checked on a unit yet. Two bindings stay `hypothesis`.

Base: stock firmware 5.52. Main sources are Roland's own 5.x manuals; 4.x translations and community sheets are kept only as extra
evidence. Evidence is labelled in each record. 785 of 787 bindings are `verified` (read in the Roland text); 2 are `hypothesis`
(one key combination that only a 4.05 sheet lists, one EXIT the manual does not describe). None is `disputed`.
All screens are `partial` on purpose: the manuals give no exhaustive control list per screen, so `check-keys` answers `unknown` for
anything not listed. Treat unknown as taken. The new `microscope` screen (TR-REC note editing) exists only in the binding file.

Files: `controls.json` (names), `bindings/stock-5.52.json`, `screens/stock-5.52.json`, `facts/functions.json` (facts `fn-stock-*`).

## Controls
Pads `PAD1`..`PAD16`, `SUB PAD`, banks `BANK A/F`..`BANK E/J`, knobs `CTRL1`..`CTRL3`, encoder `VALUE` (turn and press), plus
`SHIFT`, `REMAIN`, `EXIT`, `DEL`, `COPY`, `REC`, `RESAMPLE`, `RECORD SETTING`, `PATTERN SELECT`, `PATTERN EDIT`, `START/END`,
`PITCH/SPEED`, `MARK`, `BPM SYNC`, `GATE`, `LOOP`, `REVERSE`, `ROLL`, `HOLD`, `BUS FX`, `EXT SOURCE` and six effect buttons.
No CTRL4-6 exist physically (MIDI only).

## Screens (ids used in bindings)
`sample` (home), `pattern-select`, `pattern-rec`, `tr-rec`, `pattern-edit`, `pattern-chain`, `sampling`, `looper`, `skipback`,
`sound-gen`, `sample-edit`, `marker-edit`, `envelope`, `pitch-speed`, `chromatic`, `velocity-16`, `tempo-sel`, `efx-edit`,
`mfx-select`, `dj-mode`, `utility-menu`, `system`, `efx-set`, `pad-set`, `import-export`, `select-project`, `input-setting`,
`pad-link`, `mute-group`, `exchange`, `sample-merge`, `bank-volume`, `copy-select`, `delete-select`. `any` only for EXIT (back).

## What SHIFT does (all taken in `sample`)
SHIFT+PAD1 fixed velocity, 2 16-velocity, 3 cue, 4 chromatic, 5 exchange, 6 init params, 7 pad link, 8 mute group, 9 metronome,
10 count-in, 11 tempo, 12 gain, 13 utility menu, 14 import/export, 15 pad set, 16 efx set.
SHIFT+: BUS FX mute bus, HOLD pause, EXT SOURCE input setting, SUB PAD projects, MARK(3 s) save effect params,
PITCH/SPEED envelope, START/END chop, PATTERN SELECT undo (pattern recording), ROLL interval, REVERSE+pad pad mute,
REVERSE+REMAIN latch, LOOP ping-pong, GATE / BPM SYNC bank-wide, REC TR-REC (pattern playing), bank bank volume,
REMAIN(3 s) live mode, COPY bank protect, VALUE press skip-back/looper, RESAMPLE merge, RECORD SETTING sound generator, EXIT stop all.
Other held modifiers: REMAIN (bus routing, bank-wide edits), VALUE (select without play, effect grab), COPY (mute-group edits, bank copy),
DEL (delete, bank delete), HOLD (latch, chain select), ROLL (roll, root note), MARK (select without play), MFX (effect list).

## Functions by area (details in facts)
Playback gate/one-shot/loop/reverse/roll, chromatic, 16 velocity, pad mute, groups, merge, live mode. Effects: BUS 1-4, MFX, input
FX, side chain (new in 5.50), direct FX, favorites. Sampling: REC, RESAMPLE, skip-back, looper, sound generator. Editing: start/end,
markers/chop, envelope, pitch/speed. Patterns: real time, TR-REC, edit, chain, motion record, bounce. DJ mode. System menus.

## Changes 4.x to 5.x
Side chain tab in EFX SET, App Auto Connection and Start-up Screen in SYSTEM GENERAL (confirmed from the 5.50 manual); Serato
control and DJ pad-mode skip-back from release-note snippets (unconfirmed). No new chord is visible in the 5.50 shortcut tables, but
the Roland 5.x tables match the 4.x ones. Corrections made on 2026-11-09: DJ pads 9/11 are "return to start" and 14/16 "CUE",
SHIFT+REVERSE+pad 13/15 in DJ mode is MUTE, VALUE+SUB PAD evens out start timing (it does not bypass BUS 3/4), pad bus toggle is
bus-or-dry, DEL with pad 2 or pad 6 resets a DJ tempo (either pad alone).

## Honest gaps
Screens never seen from the unit; hardware tests absent for every binding. Menu sub-screens (system tabs, import/export, backup)
and Serato mode are only roughly covered. The only power-on combination known is SHIFT at start-up for the update. Roland's
standalone shortcut list PDF is for 4.x only; the 5.x lists are inside the Reference Manuals.
