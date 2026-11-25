# Observing the SP-404MKII BMC over USB

Reviewed 2026-11-25 using stock APP1 5.52, public protocol implementations,
and a saved hardware log. The device was untouched in this investigation.

## The editor port belongs to the main processor

The SP hub exposes two USB devices. The Roland editor uses the CDC-ACM
serial device `0582:02E7`. Audio and MIDI use the separate composite
device `0582:0281`. Stock APP1 5.52 supplies the editor port's descriptor:
at `0x800427CE` the USB handler branches to the getter at `0x80043698`,
which returns the 18-byte descriptor at `0x20009060`. Its configuration
descriptor at `0x20009080` declares CDC communication and data interfaces.
The same APP1 maps the editor file prefix `/SP404REMOTE//` to `B:/`
in the path handler at `0x800D9CC0`. See `hw.usb` for the checked bytes.
[USB enumeration in SparkyMK2](https://github.com/TuscanPL/SparkyMK2/blob/3007b5d4a796ecf752c7866c1cead87d31c5e416/docs/re/00-findings.md).

SparkyMK2 documents project and pad queries, waveform summaries, and file
operations on internal storage and the SD card. open404 calls a waveform
operation a memory read in its API and notes. Its request builder takes
project, pad, channel and offset within audio data. SparkyMK2 documents
the observed waveform display reply as minimum and maximum sample values.
Neither implementation documents an address-based read of BMC RAM or a dump
of running BMC code. Reading an APP0 file from an SD card through the file
API would return the file already on the card.
[SparkyMK2 transport and waveform](https://github.com/TuscanPL/SparkyMK2/blob/3007b5d4a796ecf752c7866c1cead87d31c5e416/docs/re/01-transport.md),
[open404 waveform request](https://github.com/iare-digital/open404/blob/294d5cb8278d07295d01c645bca67fb7b158c3a5/pkg/protocol/packet.go).

## What the saved hardware log shows

A diagnostic APP1 on the owner's SP captured incoming messages at the
main processor's internal receive table on 2026-11-12/13. The saved log
contains 3,170 four-byte records with timestamps. Recounting groups gives
3,101 in the USB MIDI relay class and 69 on the BMC service channel.
The service group contains 66 SHIFT transitions and three startup records.
The log contains no bulk firmware data. The private test's one Roland RQ1
request asked for the first slot's effect-type field, and its before and
after receive counters are both 3,170. This result applies to that request
and that receive path. See `hw.bmc.rx-table`, `hw.bmc.host-midi` and
`hw.bmc.no-read`. The log stays outside this repository.

The earlier `UPD1` dump used code on the main processor to copy from that
processor's own address space. An equivalent read of the running `APP0`
would require a path to memory on the other chip.
See `hw.boot.loader-image` and [the APP0 update study](app0-update-safety.md).

## What transfers from SYSTEM-8

The SYSTEM-8 researchers installed a PLUG-OUT that ran code on the ARM
processor with access to the live system image. That code read its own
address space and returned the bytes via MIDI. The authors report a
2,939,504-byte OS dump. The USB transport carried the data once the
PLUG-OUT could read it. The corresponding execution or readback interface
on the SP's BMC remains unverified.
[SYSTEM-8 live memory observations and bulk dump](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol4_firmware_container_protocol/base_firmware.md).

Passive recording of an ordinary editor session can help map settings and
status messages. Recording the SP's audio while using stock effects can
characterize their sound and how it changes with parameters. These are
measurements of the outputs the instrument already provides. A capture of
either kind cannot recover firmware bytes that the SP never transmits.
