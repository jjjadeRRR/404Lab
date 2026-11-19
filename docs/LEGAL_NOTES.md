# Legal notes

Working notes for contributors, not legal advice. Texts were read on 2026-11-09. Check them again before publishing.

## This project

MIT (`LICENSE`, `REQUIREMENTS.md` D11), for our own code and text only. It does not cover Roland firmware, other mods, or DM-404, which is a separate project with its own licences and is not included here. Check before publishing that nothing third-party has entered the repository.

## DOOM OS

Licence in `github.com/klangfeld-labs/doom-os`, file `LICENSE` [DOC]:

- Section 4 allows studying how DOOM OS works. What is learned about the SP-404MK2 and its firmware may be used, including
  in your own firmware. So a knowledge base describing its functions and internals in our own words is allowed.
- Section 3 requires written permission to pass on the patch, the patcher or a patched file, and to change DOOM OS.
- Section 3 also covers copying or closely imitating its code, screens, layouts, graphics or texts in anything else, and using
  its name or logo for anything else.

What follows for 404Lab:

- Write about DOOM OS in our own words. Do not copy its manual, changelog or screens into the repository.
- A new interface designed by an agent follows the Roland interface and the general conventions of the unit. It does not imitate
  DOOM OS screens or layouts.
- We name DOOM OS only to say what it is and what a tool is compatible with.
- The maintainer decided that users bring their own APP1 and that 404Lab is a tool (`REQUIREMENTS.md` D1). A mod built on a DOOM OS
  image is still a change to DOOM OS under section 3, made by that user on their own unit. Documentation should tell users this
  plainly so they can decide. Asking the author: `lab@klangfeldlabs.com`.

Older DOOM OS snapshots carried an MIT licence. Tampal's site still describes DOOM OS as MIT. The current licence text is the one to
follow.

## Side-Piece

`freakierfirmware.com/terms` [DOC]: site content is all rights reserved. A user may build and flash their own unit, but may not
share or redistribute a mod's patch data or a build made with it. Do not store its patch data in this repository. Describe its
functions in our own words.

## Tampal

`tampal.petakajaib.com/legal` [DOC]: no licence stated for its own code. Some effects derive from MIT-licensed Airwindows code.
Do not store its patches or effect files in this repository.

## IrakliyMOD

Its page credits DOOM OS 0.6.1 and Tracelistener SG / Kits as MIT [DOC]. No terms for the mod itself were found on the page: unknown. Do not store its files or screens. Describe it in our own words.

## SparkyMK2 and 404tui

Both are GPL-3.0-or-later, as their READMEs state and GitHub reports for their `LICENSE` files, read 2026-11-19 [DOC]. Facts such as byte layouts, command numbers and observed behaviour may be restated; their code, documentation text and images are not copied into 404Lab, which is MIT. Each fact taken from them names the project, the file and the revision read. SparkyMK2 follows its own clean-room rules (`docs/clean-room.md`): no Roland code, firmware or assets.

## Roland and hardware documents

Roland firmware and manuals are not ours. Nothing from them goes into the repository except short facts in our own words. Byte checks store a size and a SHA-256 of the bytes they check, not the bytes, for Roland's code and for other mods' code alike. NXP and
Arm documents are cited by revision in [the source index](SOURCES.md). The repository contains links and original research notes. Keep local copies of third-party documents outside Git.

## APP0

Describe what it is, what it does and what is known (`REQUIREMENTS.md` D3).
