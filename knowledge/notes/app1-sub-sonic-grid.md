# Exposing Sub Sonic in the MFX grid

Recorded 2026-11-25. An experimental APP1 based on the 5.52 generation
exposed the hidden stock type 45, Sub Sonic, after Compressor 2 on page
3. The added cell is the twelfth on the page. The separate EFX SET
BUS 3/4 effect list still ends with Compressor 2.

The change appends stock type 45 to the existing expanded grid, raises
the upper index from 42 to 43 and extends the two unrolled searches for
the current type. It uses the original `Sub Sonic` label and parameter
record 520. The record and name are identical in the parent and
candidate APP1. Navigation through the actual candidate Thumb code
passes for the pad, both VALUE paths, the CTRL endpoint, the grid title
and reopening the selected type's page. The same test cases failed
against the previous APP1 at the new cell and name. The test stops in
the UI and does not emulate the BMC or check sound.

Stock APP0 stores the same DSP program and companion data for Sub Sonic
and Bypass. The test candidate was withdrawn and its local binaries were
deleted. The sound of type 45 remains unverified on the SP. See the
[shared parameter map](app0-mfx-selection-trace.md#the-parameter-map-shared-by-app1-and-app0)
and `hk.recipe.mfx-grid-entry` for the selection paths.
