# MIDI

Facts: `knowledge/facts/midi.json`. Stock facts come from the Roland SP-404MK2 Reference Manual, Version 5 (chart dated 2025-07-01), which
says it holds for software 5 or later. Nothing was tested on a unit. DOOM OS documents no MIDI behaviour at all (`midi.doom.docs`).

## Routing and settings (`midi.routing.ports`, `midi.routing.settings`, `midi.sync.out`, `midi.settings.notes`)

| Setting (UTILITY > SYSTEM > MIDI) | Values | Effect |
|---|---|---|
| MIDI Sync | Auto, Internal, MIDI, USB | Tempo source (clock from MIDI IN, USB, or own) |
| MIDI Sync Out | off, on | Clock, start, stop out of the MIDI OUT jack |
| SEQ Note Out | off, on | Pattern note sent while a pattern plays |
| PAD Note Out | off, on | Pad note sent when a pad is played |
| SYNC Delay | 0-20 ms | Delays own playback against external gear |
| Bend SYNC(DJ) | off, on | Clock follows BEND pitch change |
| Soft Through | off, on | MIDI IN copied to MIDI OUT |
| USB-MIDI Thru | off, on | USB in to MIDI OUT, MIDI IN to USB, both also to the sound engine |
| PC Rx | on, off | Receive program change |
| MIDI Mode | A, B | Note numbering (below) |
| Pad MIDI Channels | 1/2 ... 9/10, 10/11 | Channel pair, mode B only |
| Note offset | -11 to 35 | Mode B only |
| MIDI EXT SRC | Toggle, Gate, Through | How incoming notes drive EXT SOURCE |

DIN and USB are two ports of the same MIDI engine: the manual gives no separate map for USB. USB is class compliant, no hub in between.
Start (FA) and stop (FC) from outside start and stop sampling. Clock is received only while the unit follows an external tempo, and sent
only with Sync Out on and no external tempo.

## Notes (`midi.mode.a.map`, `midi.mode.b.map`, `midi.chart.notes`)

| Mode | Channel | Notes | Rule |
|---|---|---|---|
| A | 1-10 = bank A-J | 36-51 | pads 1-4 = 48-51, 5-8 = 44-47, 9-12 = 40-43, 13-16 = 36-39 |
| A | any | 35 | EXT SOURCE |
| B | first of pair: banks A-E, next: F-J | 12-91 | note = 24 + 16*bank + (pad-1)%4 - 4*((pad-1)//4), bank A = 0 |
| B | | 0 | EXT SOURCE |
| any | 16 | 36-60 | chromatic mode samples |
| any | 11 | 0-127 + pitch bend | vocoder note, input only |

Examples in mode B: A1 = 24, A13 = 12, B1 = 40, E16 = 91. The printed table seems to show I where H is expected for bank C pads (`midi.mode.b.maperr`).
Velocity is used on Note On. Note Off is "not handled" in the chart, yet EXT SRC Gate uses it (`midi.chart.noteoff`, disputed).

## Control change (`midi.cc.channels`, `midi.cc.dj`, `midi.cc.looper`)

| Channel | CC | Meaning |
|---|---|---|
| 1-4 bus, 5 input | 16, 17, 18 | Ctrl 1, 2, 3 |
| same | 80, 81, 82 | Ctrl 4, 5, 6 |
| same | 19 | EFX switch (0-63 off, 64-127 on) |
| same | 83 | EFX number (list on manual p.142 onward) |
| DJ 1 / 2 / 3 | 7 | Volume slider of CH1 / CH2 / sequencer |
| DJ 1 | 8 | Crossfader (127 = CH1 only) |
| DJ 1-3 | 20-27 | Play, release press, SYNC, CUE, BEND+, BEND-, BPM+, BPM- (sent only) |
| Looper 1 | 87 DEL, 88 REC, 89 RESAMPLE, 90 Ctrl 3 | 127 acts, 0 stops or releases |
| Looper 1 | 85 EXIT, 86 PITCH/SPEED, 91 undo/redo | 127 undo, 0 redo for 91 |

## Other messages (`midi.pc.recv`, `midi.sysex`, `midi.realtime`)

| Message | Sent | Received |
|---|---|---|
| Program change | no | yes: 0-15 = pattern 1-16, channel = bank (ch 4 = D) |
| System exclusive | no | no |
| Clock, start, stop | yes (see above) | yes (remote mode) |
| Active sensing | yes | yes |
| All Sound Off | no | yes |
| Aftertouch, song position, song select, tune request, all-notes-off | no | no |
| Pitch bend | no | yes, only vocoder channel 11 |

Incoming notes can be recorded into a pattern, and sound generator mode plays from an external keyboard.

## DOOM OS (all unknown or guessed)

Its manual, README and changelog never name MIDI. It is a patched stock image, so stock MIDI is probably still there (`midi.doom.inherit`,
hypothesis). Not documented: recording MIDI notes into DOOM OS tracks, per-track channels, clock handling (`midi.doom.rec`,
`midi.doom.channels`, `midi.doom.clock`). Also unknown: whether the unit sends program change (`midi.gap.sendpc`), and how 5.52 differs from the
chart (`midi.gap.firmware`).
