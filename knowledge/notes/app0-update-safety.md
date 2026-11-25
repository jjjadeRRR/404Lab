# SP-404MKII APP0 update and recovery evidence

Reviewed 2026-11-25. The SP evidence comes from a read-only analysis of the
UPD1 1.10 dump from one unit and five unmodified Roland APP0 files. The test
case under consideration is one existing MFX program replaced at the same
length, with its descriptor, companion block and all other bytes preserved.

## What the stock NXP updater checks

| Stage | What UPD1 1.10 does | Evidence in the unpacked dump |
|---|---|---|
| Finds the file | Opens the ordinary APP0 file by name and sets the presence flag used for the `FOUND` screen. This step reads no APP0 data. | `0x8003D9EC`–`0x8003DA14`, `0x8003DB26`–`0x8003DB58` |
| Starts the update | Opens the file again, calculates a block count for the progress display from its size and starts the BMC exchange. This path compares neither the size with a fixed APP0 length nor the header or CRC with a reference. | `0x8003F0B0`–`0x8003F13E`, `0x8003F194`–`0x8003F1E2`, `0x8003DBEC`–`0x8003DC08` |
| Sends the file | Reads the next 4096-byte block when the BMC requests data. All five factory APP0 files contain 576 complete blocks. The host feeds the file to the BMC without interpreting the bytes in this worker. | `0x8003F206`–`0x8003F234` |
| Displays `APP0 UPDATER OK` | The receive path maps a BMC completion reply to a worker event. The worker sets status 4 through a callback, and the UI displays `OK` for status 4. This path performs no independent BMC flash readback and runs before a reboot. | `0x800353D6`, `0x8003F048`–`0x8003F0AE`, `0x8003F246`–`0x8003F282`, `0x8003DF90`–`0x8003DF9E`, `0x8003DBDA`–`0x8003DBEA`, `0x8003DCEC`–`0x8003DCF8` |

The UPD1 dump is identified by `hw.boot.loader-image`. The addresses above
are runtime addresses after UPD1 copies its code from flash. Roland also
calls for a separate version check after restarting the unit.
[Roland's update instructions](https://support.roland.com/hc/en-us/articles/4409641783579-SP-404MK2-System-Program-Version-Update).

## What the factory APP0 files show

In 5.52 the 98 descriptors and 98 payloads for types 0–48 all have distinct
start addresses. None of the 98 payload ranges overlap. The catalogue
contains four pairs of effects with identical code and companion content,
each stored twice. Bypass (0) and Sub Sonic (45), for example, have identical
66-byte programs at file offsets `0x14CF84` and `0x15BE00` respectively.
Every descriptor pointer and payload pointer occurs once as a
literal aligned little-endian word in the complete image. That scan cannot
resolve computed references or code inside the encrypted section.

The known file CRC covers the header and the encrypted block plus its first
12 trailing bytes. The range ends at `0x4BBFC` in 5.52, before the readable
DSP programs. Between factory 5.50 and 5.52, 11 header bytes, 16 encrypted
bytes, four CRC bytes and eight trailer bytes changed, 39 bytes in total.
The files are byte-identical from `0x4BC30` to the end. The header field at
`0x50` changes from `0xBFEC6DDE` to `0xDE7D4E5A`
while the open effects stay identical. This rules out that field being a
function of the MFX region alone. On MC-101 the matching field is a CRC-32 of
the decoded ARM payload. That gives a concrete candidate for SP and leaves
possible checks of the open MFX region unresolved.
[MC-101 reference implementation](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/tools/package_c0a_firmware.py).

To reproduce, compare the `SP404MKII_APP0.bin` members from the factory
archives listed in `app0.versions`. Count differing bytes over the whole
image and within the header `[0, 0x60)`, encrypted block
`[0x60, 0x4BBF0)`, CRC `[0x4BBFC, 0x4BC00)` and trailer after that CRC.
Verify the CRC with `app0.crc`.
In 5.52, read 49 pairs of little-endian pointers at `0x15D698` and follow
them with the `0xC0000` bias in `app0.pairs`. Test every two half-open
payload ranges for intersection and search the entire image on a four-byte
grid for each pointer value. The 5.50 and 5.52 file SHA-256 values are
`7615f712602583fc8fb5f333d815fa8cac0fae43293fc1f67692c4c77e100e27` and
`3e35ff30137f741a715566e205384f9b434ca7ac3847e247bad3f0c9c8a2bd23`.
[Factory release notes](https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/).

## What recovery would depend on

- On this SP, UPD1 samples GPIO1_IO02 before choosing its own update screen
  or APP1. The board signal's source during power-on with SHIFT held remains
  unresolved. The NXP can keep its updater intact while it still depends
  on the BMC to receive an APP0 again. The owner's stalled-update account
  shows that the update menu survived those stalls with the bad SD card.
  The state of BMC flash during those stalls was unmeasured. See
  `hw.boot.select-pin-driver` and `hw.update.stalled`.
- On MC-101, the published flash and boot-ROM analysis traces SHIFT to the
  resident App0 and an update path that bypasses its main `C0A` application.
  MC-107's author ran modified `C0A` on hardware using this route and
  describes returning to stock with a factory `C0A`. The first-stage flash
  partition and `C1A` sound-engine image stayed stock. This is evidence for
  a split boot path on MC-101. The corresponding SP BMC partition layout
  and SHIFT path remain open.
  [MC-101 boot ROM analysis](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/docs/boot_rom_analysis.md),
  [MC-107 hardware results and rollback instructions](https://github.com/edco/mc-107/tree/62ee091bd04167a73874ca7fe3e53631be922dfe).
- The Side-Piece recovery guide covers restoring APP1 on SP. Roland's
  official guide warns that a power failure during the official update can
  require service. Neither source documents restoring SP BMC flash after an
  APP0 failure.
  [Side-Piece recovery scope](https://freakierfirmware.com/recovery/#sp-404mkii),
  [Roland update caution](https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/).

## What a computer-only test can predict

| Question | Current answer | Evidence that would settle the rest |
|---|---|---|
| Can one catalogue program change in isolation? | As stored in 5.52, yes. Its address and size identify a separate range outside the known CRC, so changing only that range can preserve the encrypted bytes and descriptors. | An in-memory byte-diff check can establish the exact scope of a candidate. |
| Would the SP accept it, and what is erased before any rejection? | The observed UPD1 file path forwards the data. The BMC's validation, write order and flash ranges are still unknown. | The SP UPD0 receive and flash routines would show validation order, erase ranges and what its completion reply guarantees. |
| Would the MFX run correctly? | The offline SDK tests cover instruction encoding and a stock Bypass test in synthetic memory. | Trace the SP BMC ARM code for MFX load, scheduling and memory mapping. A model of this path can then test program bounds, DSP writes, sample outputs and effect switching. |
| Could a failing image be undone? | The observed SP recovery cases leave that open. The host entering its update menu and the BMC being able to receive and rewrite stock APP0 are separate conditions. | Board or firmware evidence for entry and reception independent of APP0, followed by a demonstrated recovery from a known bad APP0 on equivalent hardware. |

The 310,160-byte block remains undecoded. The shared container and SP's
entry word `0x01000001` make BMC ARM control code a plausible role. Both
published parsers located the SP payload, and their decryption attempts
stopped for lack of compatible key material. The exact contents and location
of the MFX loader remain unconfirmed. A small change to the open DSP code can
be studied without decrypting that block. Predicting what SP does beyond the
host transfer still requires BMC-side evidence. Under the owner's no-risk
constraint, the experiment stays offline.
[Roland Plug-Out SDK container reference](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol4_firmware_container_protocol/container_formats.md#141a-app1_main-payload-cipher-3-key-3des-verified).
