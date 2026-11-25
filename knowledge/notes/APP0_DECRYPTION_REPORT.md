# SP-404MKII APP0 decryption report

Recorded 2026-11-25. Compared official SP-404MKII updates 3.02, 4.04,
5.01, 5.50 and 5.52, MC-101, MC-707 and VERSELAB MV-1 1.82, and SYSTEM-8
1.32. All work used files on a computer.

## Container and fingerprints

All five devices use header value `0xB6020001`. For MC-101 and SYSTEM-8,
mode `0x02` and slot `0xB6` select three-key 3DES in ECB mode using the
hardware's 32-bit word order. The published decryptors need the key
material, which was absent from the available inputs.
[MC-101 decryptor](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/tools/decrypt_c0a.py),
[SYSTEM-8 container reference](https://github.com/enorrmann/roland-plugout-reveng/blob/83ead8f92d3f9cf5fedfbb57a543dadcc9cc11c2/docs/vol4_firmware_container_protocol/container_formats.md).

For SP 5.52 the header gives a load address of `0x01000000` and a size
of 310,160 bytes. The stored block at file offsets `[0x60, 0x4BBF0)`
has byte entropy 7.99464 bits/byte.

| Input | SHA-256 |
|---|---|
| SP 5.52 full APP0 | `3e35ff30137f741a715566e205384f9b434ca7ac3847e247bad3f0c9c8a2bd23` |
| SP 5.52 encrypted block | `05703e9ad49ab373a679fe6a43c70c9546c31e2d7e971c997ccd0bf698f2f99c` |
| MC-101 1.82 C0A | `ebdb8d987232a31972c881065254419187d586d73bb1c808e681b5dd278d8cf6` |
| MC-707 1.82 C0A | `79e781811ebe20f02d53e17998ca351246a2e02f2e31338febe7d1964d840c34` |
| VERSELAB MV-1 1.82 C0A | `23b636250f1a887edbc81e6618ff08ab68f61ede04d40c613bdf5560d6d2ef1a` |
| SYSTEM-8 1.32 C0A | `cc8fa7ff044a404fb1614b6dd160af95a26b0ab4fdfb5cac5cdd6756c7fd9cfe` |

## Shared ciphertext on the eight-byte grid

| Reference against SP 5.52 | Distinct matches | Occur once in each | Matches with reference shifted one byte |
|---|---:|---:|---:|
| MC-101 1.82 | 2,839 | 2,333 | 0 |
| MC-707 1.82 | 1,708 | 1,246 | 0 |
| VERSELAB MV-1 1.82 | 2,995 | 2,472 | 0 |
| SYSTEM-8 1.32 | 3,030 | 2,043 | 0 |

All five share a 696-byte ciphertext run with 86 distinct eight-byte
blocks. The following positions are offsets in the unpacked containers.

| Firmware | Run file offset |
|---|---:|
| SP 5.52 | `0x425D8` |
| MC-101 1.82 | `0xAD8F8` |
| MC-707 1.82 | `0xF17C8` |
| VERSELAB MV-1 1.82 | `0xC8120` |
| SYSTEM-8 1.32 | `0x2086B0` |

The run SHA-256 is
`d95832cffb64a5f7982ffa9bc51f44a3f8f9ce04066d41d5b91dc5e1340582c9`.
The long runs, single-occurrence matches and shifted control strongly
support a common deterministic transform and key. A keyed SP
decryption remains unverified. Within the SP, 5.50 and 5.52 differ only
at the two eight-byte payload blocks starting at `0x4ADC8` and
`0x4ADD0`.

## Plaintext identified through a published reference

The MC-101 patch manifest gives the original bytes at specific addresses
in decrypted 1.82 C0A. There are 126 distinct complete eight-byte
plaintext/ciphertext pairs, with consistent results where sites overlap.
One pair identifies 370 eight-byte blocks of zeros in SP 5.52, or
2,960 bytes total, for example at file offset `0x80`. None of the
nonzero plaintext pairs from the manifest matches SP ciphertext. The
earlier SYSTEM-8 startup excerpt search also gave no match. The
classification of the 696-byte shared run remains open.
[MC-101 stock-byte manifest](https://github.com/edco/mc-101-re/blob/6b62129b7a2fcb74f73e690e357c2f3cde255ef6/8-track/manifest/sites.json).

No complete plaintext or `APP0_SP404MKII_decrypted.bin` was produced.
A compatible key would allow a full offline test. An existing
SYSTEM-8 plaintext excerpt covering payload offset `0x208650` for
696 bytes, or MC-101 at `0xAD898`, would identify the shared SP run
through exact block correspondence. With a full candidate, first
compare the known zero positions, then verify the Thumb-2 entry,
control flow against the SP load map and candidate plaintext CRC
against the header word at `0x50`.

## Reproduce

Unzip each official update. Open the inner groovebox `UPA_up.bin`
as a tar archive and select its C0A member. For SYSTEM-8 use
`p1y01_m0c0a_up.bin`. Use SP APP0 as shipped. Read the little-endian
payload size at `0x44`, control word at `0x54` and payload at `0x60`.
Count and compare the aligned eight-byte words. To match plaintext use
only complete aligned blocks within the MC-101 manifest's `expected`
spans. Subtract the manifest's base address from the address of each
block, then add `0x60` to obtain the C0A file offset.
