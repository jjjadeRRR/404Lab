# SP-404MKII MFX selection and update checks

Recorded 2026-11-25. Read-only comparison of the stock SP-404MKII System
Program files for 3.02, 4.04, 5.01, 5.50 and 5.52 (`app0.versions`).
APP1 was inspected after mapping its copy section to `0x80000000`.
The hardware and update files were untouched.

## The parameter map shared by APP1 and APP0

In stock 5.52, APP1 uses its parameter-range table at `0x8022E1C8`
to turn a parameter number into a group number. The encoder then
searches 12-byte records at `0x80231408` by group and effect slot and
unpacks the first word of the selected record. This part of the host
trace is at `0x800D8118`–`0x800D81EE` and
`0x800D8212`–`0x800D82DA`. Ordinary effect changes also send a
separate type-selection message (`app0.no-runtime-load`).

The 12-byte records for the effect types occur after four non-MFX
records. Each effect type `t` from 1 onward has five rows for Input FX
and BUS 1–4. In the APP1 tables the second word's upper half is
`t + 3`, its lower half is twice the number of parameters in that
type's APP1 interval, and byte 9 of the row carries the slot index
from 0 to 4. The first word is the packed parameter address prefix
used by the host encoder. These observations describe the stored
map. The receiver's behavior at the end of each range is unmeasured.

| Version | APP0 map offset | APP1 map address | APP1 type 1 parameter interval address | Total rows |
|---|---|---|---|---:|
| 3.02 | `0x20313C` | `0x801F5B60` | `0x801F2A70` | 250 |
| 4.04 | `0x203644` | `0x8021C968` | `0x80219740` | 245 |
| 5.01 | `0x203644` | `0x80228780` | `0x80225558` | 245 |
| 5.50 | `0x203644` | `0x80231370` | `0x8022E148` | 245 |
| 5.52 | `0x203644` | `0x80231408` | `0x8022E1E0` | 245 |

The map is identical on APP0 and APP1 from 4.04 onward, and identical
across all four versions. For example, the five type-48 rows on both
sides change lower-halfword size from 2 in 3.02 to 22 in 4.04. The
five rows for type 49 disappear. This agrees with the DJFX Delay
change from one to eleven parameters in the
[factory update](app0-factory-mfx-update.md). Type 45 has a
two-byte range in every version checked, matching its single APP1
parameter. A prototype with additional controls would need to account
for both sides of this map.

There is one exception to the APP1/APP0 match in 3.02. The five type-16
(Tremolo/Pan) rows have size 16 in APP1 and 18 in APP0. The remaining
245 rows match. This is a file difference with unknown runtime effect.

## Candidate Thumb tables on the BMC side

Immediately after the parameter map, APP0 has 20 zero bytes followed
by a series of groups of 38–40 odd words. Each value
is inside the load interval of the closed ARM payload. Two zero words
separate consecutive groups.

| Versions | Group range in APP0 (end exclusive) | Groups |
|---|---|---:|
| 3.02 | `[0x203D08, 0x205BE8)` | 49 |
| 4.04, 5.01, 5.50, 5.52 | `[0x2041D4, 0x206014)` | 48 |

The group counts track the number of non-Bypass types in the parameter
map. This extends the previous observation of 39 words immediately
before the DSP register table. The full group region is identical in
5.50 and 5.52. Twenty-two of the first 48 group lengths differ by ordinal
between 3.02 and 4.04. These observations support treating the values
as candidate Thumb function tables. Their order and correspondence
with specific MFX types remain unverified. In particular, the last
group's location alone gives no confirmed DJFX Delay handler.

To reproduce the scan, start from the offsets above and read
little-endian 32-bit words. Require nonzero words to be odd and fall
within the interval defined by the length and load address at APP0
header offsets `0x44` and `0x48`. Split on pairs of zero words.
The host map's type-range records are six bytes each. Count parameters
from the inclusive first and last halfwords.

## What can be checked about update validation

All five factory ZIP archives contain APP0 and APP1 as their only
files. An exact search for the null-terminated `App0_UPD` label used
by the related Roland updater containers returned no matches in
those SP APP0 files. This bounds the available inputs. It does not
locate or identify the SP's resident BMC updater.

In all five SP APP0 files the known outer CRC contains the 12 zero
bytes immediately after the closed payload in its coverage. Ending
the calculation right before those zero bytes gives a different
result. The word at header offset `0x50` matched neither CRC-32 nor
Adler-32 in the trials over the stored closed block, the entire file
with that field omitted or zeroed, the file from `0x140000` onward,
the appended area after the container's 64-byte trailer, and the two
readable regions separately. These are limited file-format tests.
They leave the role of `0x50` and the BMC's validation of the open
MFX data unresolved. On MC-101, the corresponding field holds the
CRC-32 of the decoded payload, giving a separate candidate to check
if SP plaintext becomes available.
[MC-101 container implementation](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/tools/package_c0a_firmware.py),
[SYSTEM-8 resident updater notes](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol4_firmware_container_protocol/base_firmware.md).

The next evidence needed on the selection side is a cross-reference
from the SP BMC TYPE handler to a catalogue entry and a DSP loader.
On the update side, the resident BMC updater's validation and flash
routines remain the missing evidence. See
[hardware hazards](../../docs/SAFETY.md).
