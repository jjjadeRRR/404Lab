# CHOP, AUTO MARK and the marker screen

Facts: `knowledge/facts/stock.json` (`st.chop.*`), recipes in `hooks.json`. The code named here is the same bytes in stock 5.52
and DOOM OS 0.7.2, 0.7.3 and 0.7.4. Emulator results come from DM-404 with the whole firmware, on a private build based on
DOOM OS 0.7.4 that leaves this code stock. Nothing here was measured separately on a unit.

## Where things are

```
marker screen (page 8, object vtable 0x80227008)
   knobs, window, zoom           st.chop.marker-screen
   what it draws, the menu       st.chop.marker-drawing
   waveform, peak buffers, cache st.chop.waveform
   pad press plays a chop        st.chop.play
   pad and button lights         st.chop.lights
marks: table 0x82E3C508 + pad x 0x80, project value 0xA2   st.chop.marks, st.chop.mark-gap
AUTO MARK 0x8017B410(job)                                  st.chop.automark
   LEVEL 0x8017BC48                                        st.chop.automark-level
   TRANSIENT 0x8017C138                                    st.chop.automark-transient
cutting: 0x80047EB0 -> ExeChop 0x8017C828                  st.chop.job
   its pad copy 0x800AE700, cancel check 0                 st.chop.copy-null-check
```

## Things that surprise

- The analysis always starts at the first frame of the file and ignores the pad's start point. It stops at 16 marks with the start.
- The return value of AUTO MARK is not a count. TRANSIENT returns -127 even when it found marks. Read the job.
- Set the project values 0x9D, 0x9F, 0xA0 and 0x9E before calling it. The analysis reads them, not only the job.
- Stock LEVEL can hand back one false mark near the start. The 16th word it copies is its own counter. See
  `st.chop.automark-level-extra-mark`.
- If the pad copy that starts CHOP fails, stock calls its cancel check without testing it, and CHOP passes 0: a jump to
  address 0 (PC 0, LR 0x8004A987). A mod that copies pads should pass a real check. See `st.chop.copy-null-check`.
- A mark closer than 1000 frames to its neighbour is refused by the setter. The low level writer `0x800CDB90` does not check.
- The stock cuts a copy of the pad in the temporary pad 160. Every chop but the last is one frame longer than its gap.
- A chop range set on a pad's player stays there for ordinary play until it is set back.
- `0x800552F0` creates the marker screen object. It is not a background job, as an older note said.

## Long work and the screen

Cutting runs in PANEL TASK. While it runs the display does not change, even if `0x8006FD48` is called (`st.ui.commit`). Split
long work into steps between PANEL ticks if it has to show progress.

## More than 16 marks

`hk.recipe.automark-32` moves the stock TRANSIENT and LEVEL code instead of writing new analysis. It changes only the limits
and the list. The first 16 marks then match the stock on the emulator. It has not been reported on a unit.

## Input on a screen of your own

A pad hit is events 5, 16, 17 and 18, not only 5 (`hk.key-event`). If a mod's screen takes pads it must keep all of them.
A screen that keeps every event also takes VOLUME away. That was seen on the maintainer's unit.

## Open

- What mode 4 of AUTO MARK is, and what project value 0xA1 means.
- How TIME DIVISION spreads the remainder of the length.
- Where the stock decides how many knob cells an effect shows (`st.efx.knob-pages`).
- Anything on a unit: timing, the extra LEVEL mark, the relocated analysis.
