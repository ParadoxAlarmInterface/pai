# Digiplex panel support (DGP-48 / DGP-848 / DGP-NE96)

Work in progress, intended for
[ParadoxAlarmInterface/pai#257](https://github.com/ParadoxAlarmInterface/pai/issues/257).

This package adds a driver for the older **Digiplex** family, which is the
predecessor of Spectra/EVO and speaks a related but incompatible variant of the
PC protocol. It was reverse engineered against a **DGP-848, firmware build
A095**, and cross-checked with two independent implementations:

- [tonyrog/digiplex](https://github.com/tonyrog/digiplex) (Erlang)
- [adumat/paradox-dgp-mqtt](https://github.com/adumat/paradox-dgp-mqtt) (.NET, DGP-848)

## Why a separate driver

The family differs from EVO in ways that make the generic panel code unusable:

- `InitiateCommunication` (0x72) is **ignored silently**; the panel only answers
  `StartCommunication` (0x5F), and only with `source_id=0`.
- The panel identifies itself in the `StartCommunication` **response**
  (`product_id=0` → `DIGIPLEX_v13`), which the generic `Panel.parse_message`
  rejects (`message[4] > 0`).
- Login is done by **echoing that response** with the PC password (BCD) in bytes
  `[8..9]` and a recalculated checksum. No installer code is required.
- Frames are fixed 37 bytes (36 payload + checksum), never variable length.
- The panel never broadcasts anything; status must be polled from RAM (`READ 0x5x`).
- Only one PC session is allowed. After a connection loss the panel keeps the
  session and releases it only after ~15–25 s of **absolute line silence** —
  every request, even a rejected one, restarts that timer. Reconnection
  therefore has to wait ~30 s between attempts.

## Memory map (verified live)

| Address | Meaning |
|---|---|
| `0x0153..0x0158` | zone status 1–48, bit 0 = zone 1, `1` = open |
| `0x0159..0x015E` | tamper status 1–48, same bit layout |
| `0x0195..` | partition status, 5-byte blocks per partition (see below) |
| `0x000B` | unfiltered AC sample per poll — not a usable voltage, not published |
| `0x000C` | PSU / AUX voltage |
| `0x000D` | battery voltage |
| `0x2000..` | zone labels, 16 bytes per zone, `\0` separates words |

Partition block layout (partition 1 at `0x0195`, partition 2 at `0x019A`, …):

```
+0  arm/alarm flags: bit0 armed, bit1 force, bit2 stay, bit3 no entry,
                     bit4 strobe alarm, bit5 silent alarm, bit6 audible alarm
+1  status flags:    bit0 ready, bit1 exit delay, bit2 entry delay,
                     bit3 partition enabled, bit4 alarm in memory
```

Measured values on the reference panel:

| Situation | Byte |
|---|---|
| disarmed | `0x00` |
| armed (full) | `0x01` |
| armed (perimeter / stay) | `0x05` |
| garage armed | `0x019A = 0x01` |
| exit delay running | `+1` bit1 set (`0x02`) |
| entry delay running | `+1` bit2 set (`0x04`) |

## Voltage calibration

Calibrated against a multimeter on the reference installation (2026-10):

| Reading | Raw byte | Scale |
|---|---|---|
| battery terminals 13.68 V | `0x53` (83) | `0.16482 V/step` |
| PSU / AUX output 13.66 V | `0xF2` (242) | `0.05645 V/step` |

A flat 0.1 V/step (the initial guess) produced the impossible pair
"PSU 24.2 V / battery 8.3 V", hence the per-register scales.

## Partition commands (`MONITOR`, 0x40)

```
40 00 | P1:P2 | P3:P4 | P5:P6 | P7:P8
```

One command nibble per partition, `NOP` in the slots that are not addressed:

| Value | Command | Home Assistant |
|---|---|---|
| `0x0` | NOP | — |
| `0x2` | full arm | `armed_away` |
| `0x3` | stay arm | `armed_home` (after the exit delay) |
| `0x4` | instant arm | — (see limitations) |
| `0x5` | force arm | — |
| `0x6` | disarm | `disarmed` |
| `0x8` | beep | — |

No user code is sent: authority comes from the PC session. The panel answers
with an **echo** of the frame; an `ErrorMessage` (0x70) means the command was
rejected.

## Limitations (all measured, not assumed)

- **No event history.** The panel does not broadcast `0xE0` frames, and event
  log requests (`0xE` + number) are answered with an echo of the request. The
  event buffer exists (it is readable by WinLoad), but its protocol is not
  publicly documented.
- **No PGM / siren control.** The command set for outputs is undocumented for
  this family; `control_outputs`, `control_zones` and `send_panic` remain
  `NotImplementedError`.
- **Arming from the PC goes through the panel's auto-arm path**: the keypad
  shows "auto-exit" and the configured exit delay (60 s on the reference
  installation) runs in full, for both partitions. Arming from the keypad uses
  the programmed delays instead (20 s for the house, none for the garage).
- **Instant arm is reported as a full arm** (no stay bit), so Home Assistant's
  "night" mode is mapped to stay arm to keep `armed_home` meaningful.

## Tested environment

| | |
|---|---|
| Panel | Paradox Digiplex **DGP-848**, firmware build **A095** (software 4.13) |
| Partitions | 2 — house (perimeter/stay arming) and garage |
| Zones | 48 on board, 26 assigned, labels read from EEPROM |
| Transport | ESP8266 (NodeMCU) running an ESPHome `uart_tcp` bridge (UART ↔ TCP), 19200 8N1 |
| PAI connection | `IP_CONNECTION_BARE`, PC password `0000` |
| PAI version | 3.9.0-dev, Python 3.15, Home Assistant OS (aarch64) |
| Reference meter | battery 13.68 V, PSU/AUX 13.66 V — used for the calibration above |

Notes:

- The bridge adds latency (tens of milliseconds) and accepts a single TCP
  client, which is enough for the polling driver; a direct serial connection
  should behave the same or better.
- The panel was exercised with real keypad actions: arming and disarming both
  partitions, perimeter arming, entry/exit delays and a door contact opening.

## Testing

- `tests/hardware/digiplex/test_parsers.py` — golden frames (checksums, INIT,
  login, READ), adapters (zones, partitions, voltages) and the MONITOR frame
  builder.
- Live verification on a DGP-848: two partitions armed/disarmed independently,
  entry delay reported as HA `pending`, exit delay as `arming`, voltages
  matching the multimeter, 26 zone labels read from EEPROM.
