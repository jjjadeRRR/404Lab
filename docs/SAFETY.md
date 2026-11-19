# Hardware hazards and recovery limits

Researching a file and writing persistent memory on a unit are different operations. Read-only analysis and emulator experiments are useful ways to resolve unknowns. Passing their checks does not establish that a hardware write is recoverable.

## Known hazards

These are findings about particular images and hardware, not a complete catalogue of everything that can go wrong. Query the named fact with `python -m lab404 ask FACT_ID` for its evidence and scope.

| Operation | What is known | Current protection |
|---|---|---|
| Oversized APP1 | The loader erases only `0x37F000` bytes for APP1 and does not check the incoming length (`hw.update.app1-range`). | The image builder enforces the limit. |
| Calling or hooking factory flash routines | Some APP1 routines can erase or replace the loader (`hw.service.loader-erase`). Losing the loader can remove the normal update path. | Known routines are guarded in `lab404/image.py`; hook and declared firmware-symbol checks refuse them. |
| Whole-flash or service update files | `SP404MKII_APP1W.bin` can overwrite the loader. Other service filenames select different update paths whose effects or recovery are not fully known (`hw.update.whole-files`). | `package` rejects its listed dangerous filenames in mod and output folders. |
| Writing to the SD card over USB | The unit's USB serial link has a file API that reaches the card's root, where update files live, so a program on a computer could put a file from `hw.update.whole-files` on the card without taking it out (`hw.update.usb-card-path`, a hypothesis, not tried). | None in 404Lab: its tools do not use the USB link. Any host tool that writes to the card should refuse the same names as `package`. |
| APP0/BMC writes | A reliable recovery procedure is not documented (`app0.recovery`). APP1 recovery does not prove that BMC recovery works. | The tools build APP1 only; packages reject APP0 and service update files. |

The rejected names are `SP404MKII_APP1W.bin`, `SP404MKII_APP0W.bin`, `SP404MKII_APP1U.bin`, `MIRXRT1060-EVK.bin`, `TD003_ROM.bin` and `SP404MKII_APP0.bin`. They are listed for recognition, not as instructions to create or install them. The last is a normal official update filename, but including it in a mod package would also update the second processor.

Keep these operations out of ordinary mod experiments and distribution packages. Do not work around a refusal by renaming a file or removing a guard. A low-level recovery investigation is a separate hardware task: it needs an explicit scope agreed by the unit's owner, identified chips and interfaces, verified backups, and an evidenced recovery approach before destructive writes. An external programmer or a successful dump alone does not establish recovery.

You flash your own unit. This repository does not automate it. Before trying a candidate, preserve the base firmware and back up projects independently of the unit. If the unit stops behaving as expected, record the symptoms rather than assuming another update will recover it.

## What these protections do not prove

The checks cover known sites, declared references and structural constraints. They do not analyse every possible action of arbitrary C code, detect every dangerous indirect call, or guarantee that a mod cannot damage data or hang the unit.

Timing, stack use, DMA/cache interactions, storage failures and effects on the BMC have limits on the stand; see [STAND.md](STAND.md). A successful package remains a candidate, with its tested conditions and unknowns attached.

## APP0 research

Reading and comparing APP0 files, documenting BMC communication and studying the board are valid research directions. Current limits are not a ban on learning. They also are not evidence that a particular key, debug port or recovery mechanism exists. Keep hypotheses explicit and use the versioned facts in the knowledge base.
