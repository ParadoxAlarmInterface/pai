# PRT3 Connection — Usage Guide

## What is PRT3?

The PRT3 is a Paradox printer module that exposes an ASCII serial interface over
a DB9 cable.  Unlike the native EVO/Spectra binary serial protocol (which requires
knowledge of internal EEPROM addresses and is encrypted on newer firmware), the
PRT3 protocol is documented by Paradox and uses human-readable ASCII commands.

### Why PRT3 matters

- **Native serial encryption**: Newer Paradox firmware encrypts the native binary
  serial link, making reverse-engineered integrations unreliable or impossible.
- **IP150 lockdown**: Recent IP150 firmware versions restrict third-party connections,
  breaking IP-based integrations on many panels.
- **PRT3 is stable**: Paradox publishes and maintains the PRT3 ASCII protocol. It
  works over a simple USB-to-serial adapter and is unaffected by firmware encryption
  changes to the native protocol.

PRT3 is therefore a practical, long-term path for integrating Paradox panels that
are otherwise inaccessible.

---

## Hardware setup

1. Connect the Paradox PRT3 module to the panel's combus.
2. Wire the PRT3's DB9 serial port to a USB-to-serial adapter on your host.
3. Confirm the PRT3 baud rate matches your config (factory default: 9600 baud,
   though some panels ship set to 19200 — check your PRT3 module's DIP switches).

---

## Configuration

Set `CONNECTION_TYPE = 'PRT3'` and configure the PRT3 section in `pai.conf`:

```python
CONNECTION_TYPE = 'PRT3'

PRT3_SERIAL_PORT = '/dev/ttyUSB0'   # Port the PRT3 module is attached to
PRT3_SERIAL_BAUD = 9600             # Must be 9600 or 19200 — matches PRT3 DIP switch setting

# User code for arm/disarm commands.  Must be 1–6 digits, or leave empty
# to use quick-arm (requires One-Touch Arming enabled on the panel).
# Disarm always requires a valid user code.  An invalid format is rejected
# at startup so a misconfigured code fails fast rather than silently at
# first disarm attempt.
# SECURITY: store pai.conf chmod 600 root-owned.  The code does not appear
# in PAI logs at default log levels; disable LOGGING_DUMP_MESSAGES and any
# byte-level serial tracing before sharing debug logs.
PRT3_USER_CODE = '1234'

PRT3_MAX_AREAS = 2    # Number of areas (partitions) to poll (1–8)
PRT3_MAX_ZONES = 32   # Number of zones to poll (1–96 for EVO48; up to 192 for EVO192)
PRT3_MAX_USERS = 32   # Number of users to load labels for

PRT3_COMM_TIMEOUT = 10  # Seconds to wait for COMM&ok on connect

# Utility keys: expose panel-programmed outputs as HA button entities.
# Map key numbers (1–251) to display labels.
PRT3_UTILITY_KEYS = {
    1: 'Lock Front Gate',
    2: 'Activate Garden Lights',
}
```

### Utility key MQTT topic

Utility key press commands arrive on:

```
{MQTT_BASE_TOPIC}/{MQTT_CONTROL_TOPIC}/{MQTT_UTILITY_KEY_TOPIC}/{key_number}
```

Default: `paradox/control/utility_key/1`

The payload is ignored — any publish to the topic triggers the key.

---

## Home Assistant integration

With `MQTT_HOMEASSISTANT_AUTODISCOVERY_ENABLE = True` (default), PAI publishes
discovery configs for:

- **alarm_control_panel** entities — one per area
- **binary_sensor** entities — one per zone
- **button** entities — one per entry in `PRT3_UTILITY_KEYS`

The alarm panel entity supports: `disarm`, `arm_away`, `arm_home`, `arm_night`.

### Arming states

| HA state | Meaning |
|----------|---------|
| `disarmed` | Area is disarmed |
| `arming` | Exit delay in progress |
| `armed_away` | Armed away |
| `armed_home` | Armed stay/instant |
| `pending` | Entry delay in progress |
| `triggered` | Alarm active |

---

## Limitations (v1)

- **Read-only zone control**: zones cannot be bypassed or forced via PRT3.
- **No output (PGM) control**: virtual PGM outputs are parsed but not acted on.
- **No EEPROM/definition reads**: zone/area/user labels are read via ASCII label
  commands; internal panel definitions are not available.
- **No time sync**: PRT3 has no `SetTimeDate` command; `SYNC_TIME` is a no-op.
- **Poll-based status**: area and zone states are established by polling on
  connect; ongoing state is maintained via async system events.  A brief gap
  on reconnect is possible.
- **Area count is fixed by config**: unlike EVO panels, the PRT3 interface does
  not report the number of enrolled areas.  Set `PRT3_MAX_AREAS` to match your
  panel programming.
- **Utility keys are not idempotent**: each command triggers the programmed
  action once (e.g. a gate toggle).  PAI sends no retries for utility key
  commands to avoid double-triggering.
- **User code required for disarm**: quick-arm (One-Touch) is supported for
  arming, but disarm always requires `PRT3_USER_CODE` to be set.
