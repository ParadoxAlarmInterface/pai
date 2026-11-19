# EVO onboard PGM / utility key control

How the onboard PGMs (and utility keys) of EVO192 / EVOHD / EVO48 panels are
controlled, by firmware version.

## Transport

* Panel messages are carried in an IP150 multicommand (`0xFB`) frame. Each inner
  message is prefixed with one byte holding its length. Several commands can be
  concatenated into one frame; the panel answers each one separately.
* Checksum: sum of the message bytes (length prefix excluded), low 8 bits.

## Command by firmware version

| Firmware | Onboard PGM command | PAI parser |
| --- | --- | --- |
| below 4.75 | `0xA4`, 5 PGMs | `PerformPanelPGMAction` |
| 4.75 and above | `0x40`, 32 PGMs | `PerformPGMAction` |

`Panel_EVOBase.control_outputs` selects the command from the firmware reported at
initialization: version and revision (BCD) compared against 4.75. Utility keys
(`0xAC`, firmware 2.70 to below 4.75) are not implemented in PAI.

PGMs on expansion modules use the 23-byte `0xA4` packet (`PerformModulePGMAction`),
which carries the module address in byte 3 and has 4 slots.

## `0xA4` — one command byte per PGM (firmware below 4.75, `PerformPanelPGMAction`)

71 bytes, no length prefix (the multicommand frame prepends `0x47`):

| Offset | Size | Value |
| --- | --- | --- |
| 0 | 1 | `0xA4` |
| 1 | 1 | `0x47` packet length including checksum |
| 2-5 | 4 | `00` (offset 3 = module address, 0 = the panel itself) |
| 6-69 | 64 | one command byte per PGM; offset `6 + (pgm - 1)`; unused slots `00` |
| 70 | 1 | checksum of bytes 0-69 |

Slot values: `04` to turn a PGM on, `03` to turn
it off. `00` leaves the PGM untouched. Only slots 0-4 are used (5 onboard PGMs).

Several PGMs: send one single-PGM packet per PGM, each with its own length
prefix, in one multicommand frame (do not merge them into one packet).

Reply: `a2 07 00 00 00 00 <checksum>` (high nibble `0xA`, length `0x07`).

Example, PGM 5 on (`a4 47 00 00 00 00 | 00 00 00 00 04 00 ... 00 | ef`):

```
a4 47 00 00 00 00 00 00 00 00 04 00 00 00 00 00 ... 00 ef
```

## `0xAC` — utility keys (firmware 2.70 to below 4.75, not implemented in PAI)

Same 71-byte layout, command `0xAC`. Utility key `i` (0-7) is a bit mask: byte
`6 + i / 8`, bit `i % 8` set to 1; checksum as above.

## `0x40` — PGM bit mask (firmware 4.75 and above, `PerformPGMAction`)

19 bytes (the multicommand frame prepends `0x13`):

| Offset | Size | Value |
| --- | --- | --- |
| 0 | 1 | `0x40` |
| 1 | 1 | `0x13` |
| 2 | 1 | `0x06` |
| 3-5 | 3 | `00` |
| 6-13 | 8 | little-endian bit mask, bit `pgm - 1` set |
| 14 | 1 | command: `03` on, `01` off |
| 15-17 | 3 | `00` |
| 18 | 1 | checksum of bytes 0-17 |

Example, PGM 3 on: `40 13 06 00 00 00 04 00 00 00 00 00 00 00 03 00 00 00 60`.
