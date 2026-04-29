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
                        - _prt3_send_wait uses a composite predicate matching both
                          the caller's expected reply AND PRT3BufferFull ('!');
                          a buffer-full response triggers a fast retry rather than
                          waiting the full IO_TIMEOUT
    parser.py           parse_line(line: str) -> PRT3Message | None
                        - pure function, no side effects
                        - handles: COMM&ok/fail, echo &OK/&fail, RA/RZ replies,
                          ZL/AL/UL replies, G/N/A events, PGM ON/OFF
    encoder.py          encode_*(...)  -> bytes
                        - pure command builders: arm, disarm, panic, label
                          requests, status requests, utility key
    event.py            EVENT_MAP: dict[int, dict]
                        - maps G-group codes to PAI event descriptors
                        - entries may include a "number_overrides" sub-dict keyed
                          by N value for groups where the N field changes the event
                          meaning (e.g. G065 N=001 exit_delay, N=002 entry_delay);
                          from_prt3() applies overrides generically
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

## Arm/disarm state tracking

The PRT3 ASCII protocol does **not** give a single authoritative signal for "the
partition is now armed" or "the partition is now disarmed".  PAI synthesises that
state from three sources, each of which is necessary to handle real-world panel
behaviour without HA showing the wrong state:

### 1. RA polling (`paradox/hardware/prt3/adapter.py:partition_status_from_area`)

Every poll cycle the panel reports an arm-state character (D/A/F/S/I) for each
configured area.  This drives `arm`, `arm_stay`, `arm_away`, `arm_force` in
storage.  Polling lags by 4–7 s on a panel with many zones (`KEEP_ALIVE_INTERVAL`
= 10 s, plus per-element 0.8 s timeouts), and during the brief window between
issuing a disarm command and the next RA cycle, the panel can still report
`arm_state='armed_stay'` — the panel hasn't internally settled yet.

### 2. G-events (`paradox/hardware/prt3/event.py:EVENT_MAP`)

Async system events fire on state transitions.  The mapping follows the PRT3
ASCII Programming Guide §"System Event Group Codes" (page 18):

| Group | Spec description | Effect on storage |
|---|---|---|
| 009 | Arming with Master | `arm=True, exit_delay=False` |
| 010 | Arming with User Code | `arm=True, exit_delay=False` |
| 011 | Arming with Keyswitch | `arm=True, exit_delay=False` |
| 012 | Special Arming (auto, one-touch, …) | `arm=True, exit_delay=False` |
| 013 | Disarm with Master | `arm=False, exit_delay=False` |
| 014 | Disarm with User Code | `arm=False, exit_delay=False` |
| 015 | Disarm with Keyswitch | `arm=False, exit_delay=False` |
| 016 | Disarm after alarm with Master | `arm=False, exit_delay=False` |
| 017 | Disarm after alarm with User Code | `arm=False, exit_delay=False, audible_alarm=False` |
| 064 | Status 1 (Armed/Stay/Force/Instant/etc.) | informational |
| 065 N=001 | Exit Delay flag active | `exit_delay=True` |
| 065 N=002 | Entry Delay flag active | `entry_delay=True` |
| 065 N=000 | Ready (no zones open) — informational | no change |

**Important:** G065 N=000 is the *Ready* status flag, not a "delay cleared"
signal.  It can fire while exit delay is still active (an area can be Ready
*and* in Exit Delay simultaneously — Ready means no zones are open).
`exit_delay` is cleared by arm/disarm events, not by Ready snapshots.

**Area field for G014:** the spec table shows `001-008` (specific area), but
on at least some firmware revisions a global keypad disarm fires `G014…A000`.
Partition events with `area ∈ {0, 255}` are broadcast to every known partition
in `Paradox.handle_prt3_event_message` so the change isn't silently dropped.

### 3. Optimistic update on command echo (`paradox/paradox.py:control_partition`)

When PAI sends `AD{aaa}{code}` and the panel echoes `AD{aaa}&OK`, the panel
*has* disarmed — that echo is authoritative.  G-events for ASCII-initiated
disarms during exit delay are not emitted reliably (the user's EVO192 only
sends `G065N000A015` which carries no disarm semantics), so PAI applies the
disarmed state directly on echo:

```
arm=False, arm_stay=False, arm_away=False, arm_force=False,
exit_delay=False, entry_delay=False
```

To stop a stale RA poll (issued microseconds after the echo, when the panel's
internal arm flags haven't updated yet) from briefly re-asserting `arm=True`,
arm-related properties from RA updates are dropped for **3 seconds** after a
disarm command is accepted (`Paradox._partition_arm_freeze_until`).  The window
auto-expires, so even pathological panel behaviour can't cause a permanently
stuck state.

### Sequence: HA disarm during exit delay

```
t+0      MQTT  paradox/control/partitions/Downstairs ← "disarm"
t+0      PAI → AD002{code}
t+700ms  Panel echoes  AD002&OK
         → optimistic update: arm=False, exit_delay=False, …
         → freeze window armed (3 s)
         → _update_partition_states publishes current_state="disarmed"
         → HA UI updates immediately
t+800ms  RA poll for area 2 returns arm_state='armed_stay' (panel still settling)
         → arm-keys filtered by freeze; non-arm fields (trouble, ready_status) flow through
t+3.7s   RA poll returns arm_state='disarmed'
         → freeze expired, arm fields applied normally; state already correct
```

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
