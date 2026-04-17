# PRT3 Connection — Architecture Notes

## Why PRT3 is a separate connection type

PRT3 is not a transport wrapper around the existing Paradox binary serial protocol.
It is a distinct ASCII protocol spoken by the PRT3 Printer Module, which acts as a
gateway between a home automation host and the Digiplex EVO control panel's combus.

| Property | Native serial / IP150 | PRT3 |
|---|---|---|
| Framing | Binary, variable-length, nibble-pattern + checksum | `\r`-delimited ASCII lines |
| Handshake | `InitiateCommunication` / `StartCommunication` binary exchange | Await `COMM&ok\r` on startup |
| Panel detection | `product_id` from `StartCommunicationResponse` | Known at config time |
| Labels | EEPROM reads at arbitrary addresses | `ZL`, `AL`, `UL` ASCII commands |
| Status | Binary RAM block reads at mapped addresses | `RA`, `RZ` ASCII poll commands |
| Events | Binary event packets (`0xE` command byte) | `G{ggg}N{nnn}A{aaa}\r` ASCII events |
| Auth | PC password embedded in binary frame | User code embedded in arm/disarm commands |

Treating PRT3 as native serial would require faking binary frames that the EVO panel
never generates — this would be fragile, undocumented, and unmaintainable.
PRT3 must be a first-class connection type with its own protocol adapter.

## Layer layout

```
paradox/connections/prt3/
    __init__.py
    connection.py       PRT3SerialConnection(Connection)
                        - opens serial port via serial_asyncio
                        - makes_protocol() returns PRT3Protocol
    protocol.py         PRT3Protocol(ConnectionProtocol)
                        - buffers incoming bytes until \r
                        - emits complete ASCII lines via on_message()
                        - send_message() writes bytes directly (no framing)
                        - variable_message_length() is a no-op

paradox/hardware/prt3/
    __init__.py
    panel.py            PRT3Panel(Panel)
                        - implements all Panel abstract methods
                        - routes parsed lines to state updates or events
                        - reply routing via _prt3_send_wait() / wait_for_message()
    parser.py           parse_line(line: str) -> PRT3Message | None
                        - pure function, no side effects
                        - handles: COMM&ok/fail, echo &OK/&fail, RA/RZ replies,
                          ZL/AL/UL replies, G/N/A events, PGM ON/OFF
    encoder.py          encode_*(...)  -> bytes
                        - pure command builders: arm, disarm, panic, label
                          requests, status requests, utility key
    event.py            EVENT_MAP: dict[int, dict]
                        - maps G-group codes to PAI event descriptors
    adapter.py          normalise_area_status() / normalise_zone_status()
                        - converts PRT3 status dataclasses into PAI storage dicts
    property.py         PROPERTY_MAP
                        - maps state-change keys to PAI property descriptors
```

### Wiring into the existing runtime

Minimal additions to existing files:

**`paradox/config.py`** — adds `"PRT3"` to the `CONNECTION_TYPE` allowed list and
new `PRT3_*` config keys (`PRT3_SERIAL_PORT`, `PRT3_SERIAL_BAUD`, `PRT3_MAX_AREAS`,
`PRT3_MAX_ZONES`, `PRT3_MAX_USERS`, `PRT3_USER_CODE`, `PRT3_COMM_TIMEOUT`,
`PRT3_UTILITY_KEYS`).

**`paradox/paradox.py`** — one `elif cfg.CONNECTION_TYPE == "PRT3":` branch in the
`connection` property; a guard in `connect()` that skips the binary panel detection
path and directly instantiates `PRT3Panel`; protocol-gap guards for `sync_time`,
`_clean_session`, and `control_utility_key`.

**`paradox/interfaces/mqtt/`** — utility key button discovery (`UtilityKeyButton`
entity, HA discovery publish, MQTT subscription and command handler).

Everything else is either inherited unchanged or lives in the new modules above.

## What can be reused from existing PAI

| Component | Reused as-is |
|---|---|
| `Connection` base class | Yes — `PRT3SerialConnection` subclasses it |
| `serial_asyncio` transport | Yes — same call, different `make_protocol()` |
| `AsyncMessageManager` + `HandlerRegistry` | Yes — raw and parsed handler dispatch |
| `MemoryStorage` | Yes — zone/partition/user containers |
| `ps` pub/sub bus | Yes — `labels_loaded`, `status_update`, `events`, `changes` |
| `Paradox._on_labels_load` | Yes |
| `Paradox._on_status_update` | Yes |
| `Paradox._on_event` | Yes |
| `Paradox._update_partition_states` | Yes |
| MQTT interface | Yes — unchanged |
| Home Assistant discovery | Yes — unchanged |
| All text / GSM / push interfaces | Yes — unchanged |
| `InterfaceManager` | Yes — unchanged |
| Config loading / env override | Yes — unchanged |
| `event.py` `Change` / `Event` / `LiveEvent` types | Yes |

What is **not** reused:

- `SerialConnectionProtocol` — binary framer, replaced by `PRT3Protocol`
- `Panel.load_labels()` / `_eeprom_batch_reader()` — EEPROM-based, replaced by ASCII label requests
- `Panel.handle_status()` / `parsers/status.py` — binary status blocks, replaced by ASCII status parsing
- `create_panel()` factory — PRT3 panel is instantiated directly
- `parsers/` (EVO/Spectra `Construct` parsers) — not applicable

## v1 scope

**In scope:**

- Serial transport only (direct USB or BUS2SER)
- `COMM&ok` / `COMM&fail` status handling
- Area label reads (`AL`)
- Zone label reads (`ZL`)
- User label reads (`UL`)
- Area status polling (`RA`) — arm state, trouble, alarm, ready flags
- Zone status polling (`RZ`) — open/closed/tamper/alarm/fire/supervision/battery
- Async system event parsing (`G{ggg}N{nnn}A{aaa}`)
- Arm / quick arm / disarm (`AA`, `AQ`, `AD`)
- Emergency / medical / fire panic (`PE`, `PM`, `PF`)
- Utility key commands (`UK`)
- MQTT publishing via existing PAI MQTT interface
- Home Assistant discovery via existing PAI HA interface

**Explicitly excluded from v1:**

- Virtual inputs (`VO` / `VC`) — not needed for alarm state integration
- Virtual PGMs (`PGM{nn}ON/OFF`) — complex to map, deferred
- IP transport — PRT3 is a serial module; TCP tunnelling is out of scope
- Multi-panel sites

## Limitations to document

| Limitation | Detail |
|---|---|
| Zone bypass | PRT3 has no zone bypass command; `control_zones()` raises `NotImplementedError` |
| PGM / output control | No direct PGM command in PRT3 spec; `control_outputs()` raises `NotImplementedError` |
| Door / access control | No door commands in PRT3 spec |
| Module PGM outputs | No module bus access via PRT3 |
| EEPROM / memory dump | PRT3 provides no EEPROM read facility |
| Time synchronisation | PRT3 has no set-time command |
| Panel count | Only one area/zone count configuration; must be set to match the physical panel |
| EVO48 / EVO96 / EVO192 / DGP-848 differences | Max zones and areas differ; controlled by config, not auto-detected |
| Quick Arm | Requires "One-Touch Arming" enabled on the panel; otherwise the command is silently ignored |
| User codes | Codes must be provided at command time; PAI does not store or manage user codes |
| Event history | PRT3 does not replay buffered events on connect; only live events are received |
| Reconnection | On serial disconnect, all in-flight label/status requests are lost; full re-init on reconnect |
