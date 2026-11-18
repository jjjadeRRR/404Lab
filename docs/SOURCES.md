# Reference documents

404Lab records findings in [the knowledge base](../knowledge/facts/). Use the sources below to check the relevant manual, register description, or hardware specification. This index links to third-party documents. Keep any local PDF copies under `private/`, which Git ignores.

Start with `python -m lab404 ask` for the topic. The matching record in `knowledge/facts/` gives the source and, where available, the section or page. Match the cited document revision when following page numbers.

## Roland SP-404MKII

| Document | Use it for |
|---|---|
| [Roland owner’s manuals](https://www.roland.com/global/support/by_product/sp-404mk2/owners_manuals/) | HTML and PDF editions, shortcut lists, SP-404MKII App, and integration guides. |
| [Reference Manual 5.50, English, document 04 (PDF)](https://static.roland.com/assets/media/pdf/SP-404mk2_v550_reference_eng04_W.pdf) | Stock controls, effects and system settings. The audio block diagram is on p. 165, specifications on p. 166, and the MIDI chart and note maps on pp. 167–173. |
| [Reference Manual Version 5, English, document 03 (PDF)](https://static.roland.com/assets/media/pdf/SP-404MK2_v5_reference_eng03_W.pdf) | The edition cited by the stock MIDI records. See pp. 123–124 for MIDI settings and pp. 151–152 for the chart introduction and header. |
| [Reference Manual Version 4, English, document 02 (PDF)](https://static.roland.com/assets/media/pdf/SP-404MK2_v4_reference_eng02_W.pdf) and [Version 4 shortcut list (PDF)](https://static.roland.com/assets/media/pdf/SP-404MK2_v4_shortcut_eng03_W.pdf) | Comparing controls and shortcuts against 4.x. |
| [Reference Manual Version 3, English, document 02 (PDF)](https://static.roland.com/assets/media/pdf/SP-404mk2_v300_reference_eng02_W.pdf) | Stock behavior in the 3.x generation. |
| [Roland system program 5.52 and update history](https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/) | Stock firmware changes and Roland’s update instructions. |

## Processor and architecture

| Document | Use it for |
|---|---|
| [NXP i.MX RT1060 documentation](https://www.nxp.com/products/i.MX-RT1060?tab=Documentation_Tab) and [Reference Manual Rev. 3 (NXP PDF hosted by PJRC)](https://www.pjrc.com/teensy/IMXRT1060RM_rev3.pdf) | Memory map, boot, clocks, FlexSPI, SAI and eDMA register definitions. The hardware facts cite Rev. 3. |
| [NXP i.MX RT1060 consumer datasheet (PDF)](https://www.nxp.com/docs/en/nxp/data-sheets/IMXRT1060CEC.pdf) | Pin assignments, electrical limits, and interface timing. |
| [NXP silicon errata A (PDF)](https://www.nxp.com/docs/en/errata/IMXRT1060CE_A.pdf) and [silicon errata B (PDF)](https://www.nxp.com/docs/en/errata/IMXRT1060CE_B.pdf) | Known silicon issues. Check the chip revision before applying a workaround. |
| [Arm Cortex-M7 Technical Reference Manual, DDI 0489F (Arm PDF hosted by PJRC)](https://www.pjrc.com/teensy/DDI0489F_cortex_m7_trm.pdf) | Core registers, tightly coupled memory, caches, exceptions, and debug. |
| [Armv7-M Architecture Reference Manual, DDI 0403E (Arm PDF hosted by PJRC)](https://www.pjrc.com/tmp/ARM_Arch_v7m_reference.pdf) | Thumb instruction semantics, memory protection, and exception behavior. |
| [NXP AN12042, L1 cache (PDF)](https://www.nxp.com/docs/en/application-note/AN12042.pdf) | Cache maintenance and DMA coherence. |
| [NXP AN12077, FlexRAM (PDF)](https://www.nxp.com/docs/en/application-note/AN12077.pdf) | ITCM, DTCM, and OCRAM bank allocation. |
| [NXP AN12437, performance optimization (PDF)](https://www.nxp.com/docs/en/application-note/AN12437.pdf) | NXP measurements for code and data placement. |

## Interfaces and components

| Document | Use it for |
|---|---|
| [USB-IF USB MIDI 1.0 specification (PDF)](https://www.usb.org/sites/default/files/midi10.pdf) | USB-MIDI event packets and descriptors. For the SP-404MKII’s specific MIDI messages, use the Roland chart above. |
| [Microchip USB2422 datasheet (PDF)](https://ww1.microchip.com/downloads/en/DeviceDoc/00001726B.pdf) and [errata (PDF)](https://ww1.microchip.com/downloads/en/DeviceDoc/00001576A.pdf) | USB hub configuration and descriptors. |
| [TI PCM1802 ADC (PDF)](https://www.ti.com/lit/ds/symlink/pcm1802.pdf) and [PCM4104 DAC (PDF)](https://www.ti.com/lit/ds/symlink/pcm4104.pdf) | Audio formats, clocking, and converter configuration. |
| [Solomon Systech SSD1309 datasheet (PDF hosted by DISPLAY VISIONS)](https://www.lcd-module.com/fileadmin/eng/pdf/zubehoer/ssd1309.pdf) | OLED controller commands, display RAM, and interface timing. |
