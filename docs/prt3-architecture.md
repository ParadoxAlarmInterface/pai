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
