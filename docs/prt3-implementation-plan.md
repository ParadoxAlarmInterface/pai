# PRT3 — Detailed Implementation Plan

Generated from: inspection of `feature/prt3-connection` branch, PAI `dev` as of 2026-03-29.

---

## 1. Change inventory

### Existing files to modify

| File | Change | Risk |
|---|---|---|
| `paradox/config.py` | Add `"PRT3"` to `CONNECTION_TYPE` allowed list; add 5 new `PRT3_*` config keys | Zero — additive only |
| `paradox/paradox.py` | Add one `elif` branch in `connection` property; add one guard in `connect()` | Minimal — 4–6 lines in well-isolated spots |

No other existing file is touched.

### New files to create

```
paradox/connections/prt3/
    __init__.py
    connection.py
    protocol.py

paradox/hardware/prt3/
    __init__.py
    panel.py
    parser.py
    encoder.py
    event.py
    property.py

tests/hardware/prt3/
    __init__.py
    test_parser.py
    test_encoder.py
    test_panel.py
    fixtures/
        session_startup.txt
        session_events.txt
        session_arm_disarm.txt

tests/connection/prt3/
    __init__.py
    test_protocol.py
```

---

## 2. Existing runtime path (for reference)

Understanding this path is essential for knowing exactly where PRT3 diverges.

### 2.1 Connection bootstrap

```
main.py: Paradox()
  Paradox.connection  (property, paradox.py:72)
    cfg.CONNECTION_TYPE == "Serial"  →  SerialCommunication(port, baud)
    cfg.CONNECTION_TYPE == "IP"      →  BareIPConnection | LocalIPConnection | StunIPConnection
    else                             →  AssertionError

  Paradox._register_connection_handlers()
    raw_handler_registry  ←  PersistentHandler(self.on_connection_message)
    handler_registry      ←  EventMessageHandler(self.handle_event_message)
    handler_registry      ←  ErrorMessageHandler(self.handle_error_message)

  Paradox.full_connect()
    → connection.connect()              # opens transport
    → send_wait(InitiateCommunication)  # binary: gets model/firmware/serial
    → send_wait(StartCommunication)     # binary: gets product_id
    → create_panel(self, reply)         # factory selects EVO48/96/192/HD or Spectra
    → panel.initialize_communication()  # binary login with PC password
    → run_state = CONNECTED
    → panel.load_memory()               # EEPROM reads for labels
    → run_state = RUN
    → loop()
```

### 2.2 Message dispatch (existing)

```
serial bytes arrive
  → SerialConnectionProtocol.data_received()
      buffer until checksum-valid frame assembled
  → ConnectionHandler.on_message(raw_bytes)
  → Connection.schedule_raw_message_handling(raw_bytes)
  → raw_handler_registry.handle(raw_bytes)
      → PersistentHandler calls Paradox.on_connection_message(raw_bytes)
          → panel.parse_message(raw_bytes)  →  Construct Container
          → connection.schedule_message_handling(container)
          → handler_registry.handle(container)
              → FutureHandler (send_wait pending)   resolved if command == expected
              → EventMessageHandler                 fires if command == 0xE
              → ErrorMessageHandler                 fires if command == 0x7
```

### 2.3 Status polling loop (existing)

```
Paradox.loop()
  while RUN:
    results = await asyncio.gather(*panel.get_status_requests())
      each request_status(i):
        → send_wait(ReadEEPROM, address=RAM_BASE+i)
        → parse binary RAM block
        → return plain dict  {zone_open: {1: T, 2: F, ...}, partition_arm: {1: T}, ...}
    merged = deep_merge(*results)
    _process_status(merged)
      → convert_raw_status(merged)   # splits "zone_open" → type="zone" prop="open"
      → ps.sendMessage("status_update", status=status)
    wait up to KEEP_ALIVE_INTERVAL
```

### 2.4 `send_wait()` mechanics

`send_wait()` (`paradox.py:372`) does:
1. Builds message bytes: `message_type.build(dict(fields=dict(value=args)))`
2. `connection.write(message)`
3. `connection.wait_for_message(reply_expected)` → adds a `FutureHandler` to `handler_registry`
4. Returns when `handler_registry.handle(container)` fires the FutureHandler

The `reply_expected` callable matches on `container.fields.value.po.command`.

### 2.5 `HandlerRegistry` error on no-match

`handlers.py:123`: when no handler matches a dispatched message, it logs:
```python
logger.error("No handler for message {}\nDetail: {}".format(
    data.fields.value.po.command, data))
```
This attribute access would blow up on a PRT3 ASCII line. **PRT3 parsed messages must never enter `handler_registry` unless they carry a compatible shape, or the FutureHandler consumes them first.**

---

## 3. PRT3 insertion points

### 3.1 `paradox/config.py` — `Config.DEFAULTS` dict

**Insertion 1** (line 28): add `"PRT3"` to `CONNECTION_TYPE` allowed list.

```python
# Before:
"CONNECTION_TYPE": ("Serial", str, ["IP", "Serial"]),

# After:
"CONNECTION_TYPE": ("Serial", str, ["IP", "Serial", "PRT3"]),
```

**Insertion 2** (after the `SERIAL_BAUD` block, ~line 32): add PRT3-specific keys.

```python
"PRT3_SERIAL_PORT": "/dev/ttyUSB0",
"PRT3_SERIAL_BAUD": (9600, int, (2400, 115200)),
"PRT3_MAX_AREAS":   (8,    int, (1, 8)),
"PRT3_MAX_ZONES":   (96,   int, (1, 192)),
"PRT3_MAX_USERS":   (999,  int, (1, 999)),
```

### 3.2 `paradox/paradox.py` — `Paradox.connection` property

**Insertion** (inside `if not self._connection:` block, after the `elif cfg.CONNECTION_TYPE == "IP":` block, ~line 107):

```python
elif cfg.CONNECTION_TYPE == "PRT3":
    logger.info("Using PRT3 Serial Connection")
    from paradox.connections.prt3.connection import PRT3SerialConnection
    self._connection = PRT3SerialConnection(
        port=cfg.PRT3_SERIAL_PORT,
        baud=cfg.PRT3_SERIAL_BAUD,
    )
```

**Insertion** in `Paradox.connect()` (~line 140): skip binary panel detection for PRT3.

```python
# After connection.connect() succeeds, before InitiateCommunication:
if cfg.CONNECTION_TYPE == "PRT3":
    from paradox.hardware.prt3.panel import PRT3Panel
    self.panel = PRT3Panel(self)
    result = await self.panel.initialize_communication(cfg.PASSWORD)
    if not result:
        raise ConnectionError("PRT3: failed to receive COMM&ok")
    self.run_state = RunState.CONNECTED
    return True
```

This guard short-circuits the binary handshake entirely and falls through to the normal `run_state = CONNECTED; return True` path.

---

## 4. New file specifications

### 4.1 `paradox/connections/prt3/protocol.py`

**Class: `PRT3Protocol(ConnectionProtocol)`**

Overrides:
- `data_received(data: bytes)` — appends to buffer; on each `\r` (0x0D) emits the line via `self.handler.on_message(line_bytes)` including the `\r`; discards empty lines.
- `send_message(message: bytes)` — `self.transport.write(message)` (no framing, no checksum).
- `variable_message_length(mode)` — no-op (PRT3 has no binary framing).

Does NOT override `connection_made`, `connection_lost`, `is_active`, `close` — those are inherited from `ConnectionProtocol`.

**Key test cases** (see §5):
- Complete line in one chunk
- Line split across multiple chunks
- Two lines in one chunk
- Partial line followed by completion
- `\r\n` vs bare `\r`
- Garbage before first valid `\r`

### 4.2 `paradox/connections/prt3/connection.py`

**Class: `PRT3SerialConnection(SerialCommunication)`**

Subclasses `SerialCommunication` to reuse: serial port open, permissions fix, `connected_future`, `open_timeout`, `connect()` exactly. Only one method is overridden:

- `make_protocol(self) -> PRT3Protocol` — returns `PRT3Protocol(self)` instead of `SerialConnectionProtocol(self)`.

All other `Connection` and `SerialCommunication` behaviour is inherited unchanged.

### 4.3 `paradox/connections/prt3/__init__.py`

Empty (makes it a package).

### 4.4 `paradox/hardware/prt3/parser.py`

Pure module, no imports from PAI runtime. Returns typed dataclasses.

**Dataclasses:**
```python
@dataclass
class PRT3CommStatus:      ok: bool          # True = COMM&ok, False = COMM&fail

@dataclass
class PRT3CommandEcho:
    prefix: str            # first 5 chars echoed back
    ok: bool               # True = &OK, False = &fail
    payload: str           # anything after &OK / &fail (empty for simple acks)

@dataclass
class PRT3AreaStatus:
    area: int
    armed: str             # D / A / F / S / I
    programming: bool
    trouble: bool
    ready: bool
    alarm: bool
    strobe: bool
    alarm_in_memory: bool

@dataclass
class PRT3ZoneStatus:
    zone: int
    status: str            # C / O / T / F
    alarm: bool
    fire_alarm: bool
    supervision_lost: bool
    low_battery: bool

@dataclass
class PRT3LabelReply:
    kind: str              # "ZL" / "AL" / "UL"
    index: int
    label: str             # 16 chars, stripped

@dataclass
class PRT3SystemEvent:
    group: int             # G value
    number: int            # N value
    area: int              # A value

PRT3Message = Union[
    PRT3CommStatus, PRT3CommandEcho, PRT3AreaStatus, PRT3ZoneStatus,
    PRT3LabelReply, PRT3SystemEvent,
]
```

**Public API:**
```python
def parse_line(line: str) -> Optional[PRT3Message]:
    """
    Parse one complete ASCII line (with or without trailing \r).
    Returns None for unrecognised lines.
    """
```

Routing logic (order matters):
1. `COMM&ok` → `PRT3CommStatus(ok=True)`
2. `COMM&fail` → `PRT3CommStatus(ok=False)`
3. `!` → `None` (buffer full; caller handles retry)
4. `RA{3d}{1c}{1c}{1c}{1c}{1c}{1c}{1c}` (13 chars) → `PRT3AreaStatus`
5. `RZ{3d}{1c}{1c}{1c}{1c}{1c}` (11 chars) → `PRT3ZoneStatus`
6. `ZL{3d}{16c}` → `PRT3LabelReply(kind="ZL", ...)`
7. `AL{3d}{16c}` → `PRT3LabelReply(kind="AL", ...)`
8. `UL{3d}{16c}` → `PRT3LabelReply(kind="UL", ...)`
9. `G{3d}N{3d}A{3d}` (13 chars) → `PRT3SystemEvent`
10. Anything matching `{5chars}&OK` or `{5chars}&fail` → `PRT3CommandEcho`
11. Else → `None`

### 4.5 `paradox/hardware/prt3/encoder.py`

Pure module. All functions return `bytes` ending with `b"\r"`.

```python
def encode_request_area_status(area: int) -> bytes:
    # b"RA001\r"
def encode_request_zone_status(zone: int) -> bytes:
    # b"RZ001\r"
def encode_request_area_label(area: int) -> bytes:
    # b"AL001\r"
def encode_request_zone_label(zone: int) -> bytes:
    # b"ZL001\r"
def encode_request_user_label(user: int) -> bytes:
    # b"UL001\r"
def encode_arm(area: int, mode: str, code: str) -> bytes:
    # mode in ("A", "F", "S", "I"); code up to 6 digits
    # b"AA01A123456\r"
def encode_quick_arm(area: int, mode: str) -> bytes:
    # b"AQ01A\r"
def encode_disarm(area: int, code: str) -> bytes:
    # b"AD01123456\r"
def encode_panic_emergency(area: int) -> bytes:
    # b"PE01\r"
def encode_panic_medical(area: int) -> bytes:
    # b"PM01\r"
def encode_panic_fire(area: int) -> bytes:
    # b"PF01\r"
def encode_smoke_reset(area: int) -> bytes:
    # b"SR01\r"
def encode_utility_key(key: int) -> bytes:
    # b"UK001\r"
```

### 4.6 `paradox/hardware/prt3/event.py`

Maps PRT3 G-group codes to PAI event descriptors. Same dict shape as `spectra_magellan/event.py` but keyed by integer G-group, not binary major/minor. The `PRT3Panel` will NOT use `LiveEvent` (which requires `po.command == 0xE`); it will use a `PRT3Event(Event)` subclass (defined in this file or in `panel.py`) that takes a `PRT3SystemEvent` dataclass directly.

```python
# event.py structure
from paradox.data.enums import EventLevel

EVENT_MAP: dict[int, dict] = {
    0:  dict(type="zone",      level=EventLevel.DEBUG,    change=dict(open=False), ...),
    1:  dict(type="zone",      level=EventLevel.DEBUG,    change=dict(open=True),  ...),
    2:  dict(type="zone",      level=EventLevel.CRITICAL, change=dict(tamper=True), ...),
    3:  dict(type="zone",      level=EventLevel.CRITICAL, change=dict(fire_loop_trouble=True), ...),
    9:  dict(type="partition", level=EventLevel.INFO,     change=dict(arm=True), ...),
    10: dict(type="partition", level=EventLevel.INFO,     change=dict(arm=True), ...),
    13: dict(type="partition", level=EventLevel.INFO,     change=dict(arm=False), ...),
    14: dict(type="partition", level=EventLevel.INFO,     change=dict(arm=False), ...),
    24: dict(type="zone",      level=EventLevel.CRITICAL, change=dict(alarm=True), ...),
    26: dict(type="zone",      level=EventLevel.INFO,     change=dict(alarm=False), ...),
    # ... all groups from PRT3 protocol reference
    64: dict(type="partition", level=EventLevel.DEBUG,    ...),  # Status 1 flags
    65: dict(type="partition", level=EventLevel.DEBUG,    ...),  # Status 2 flags
    66: dict(type="partition", level=EventLevel.DEBUG,    ...),  # Status 3 flags
}
```

G064/G065/G066 are special: `N` encodes a flag index, not an element ID. These need sub-maps like Spectra's `sub` key.

### 4.7 `paradox/hardware/prt3/property.py`

Reuse `spectra_magellan/property.py` directly — the property keys (`open`, `arm`, `tamper`, `alarm`, `trouble`, `exit_delay`, etc.) are identical. Import and re-export:

```python
# property.py
from paradox.hardware.spectra_magellan.property import property_map

__all__ = ["property_map"]
```

Only add new PRT3-specific properties if any new state keys are introduced that don't exist in the Spectra map.

### 4.8 `paradox/hardware/prt3/panel.py`

**Class: `PRT3Panel(Panel)`**

Key design decisions (see §6 for rationale):

- **`initialize_communication(password)`** — sends nothing; just returns `True`. The `COMM&ok` wait is handled in `Paradox.connect()` before this is called.
- **`load_memory()`** — overrides completely; sends `AL`, `ZL`, `UL` requests one at a time using `_prt3_send_wait()` (see §4.9); populates `self.core.storage` directly; fires `ps.sendMessage("labels_loaded", data=labels)`.
- **`request_status(nr)`** — sends `RA{nr:03d}\r` (if `nr <= max_areas`) or `RZ{nr:03d}\r` (if `nr > max_areas`); parses reply; returns a plain Python dict in the format `{"zone_open": {nr: bool}, ...}` or `{"partition_arm": {nr: bool}, ...}` — compatible with `convert_raw_status()`.
- **`get_status_requests()`** — generator of `request_status(nr)` for all configured areas and zones. Areas use indices 1..`cfg.PRT3_MAX_AREAS`, zones use distinct indices.
- **`parse_message(raw, direction)`** — decodes the ASCII line; calls `parser.parse_line()`; returns a simple namespace or the dataclass directly. For PRT3, `parse_message()` is not used for reply routing (see §4.9); it is only used for unsolicited event dispatch.
- **`control_partitions(partitions, command)`** — maps PAI command strings to PRT3 arm/disarm commands; uses `_prt3_send_wait()`.
- **`control_zones(zones, command)`** — raises `NotImplementedError` (PRT3 has no zone bypass command).
- **`control_outputs(outputs, command)`** — raises `NotImplementedError`.
- **`control_module_pgm_outputs(...)`** — raises `NotImplementedError`.
- **`control_doors(doors, command)`** — raises `NotImplementedError`.
- **`dump_memory(file, memory_type)`** — raises `NotImplementedError`.
- **`send_panic(partitions, panic_type, user_id)`** — maps `panic_type` to `PE`/`PM`/`PF` commands.

**Partition command map:**
```python
PARTITION_COMMANDS = {
    "arm":       ("AA", "A"),   # regular arm
    "arm_stay":  ("AA", "S"),   # stay arm
    "arm_force": ("AA", "F"),   # force arm
    "arm_sleep": ("AA", "I"),   # instant arm (no entry delay)
    "arm_quick": ("AQ", "A"),   # quick arm (no code)
    "disarm":    ("AD", None),  # disarm
}
```

### 4.9 `PRT3Paradox` — runtime subclass

**File: `paradox/hardware/prt3/runtime.py`**
(Kept with the hardware layer since it is specific to PRT3 operation; imported from `paradox/paradox.py`.)

**Class: `PRT3Paradox(Paradox)`**

Overrides only what is different; inherits all MQTT/HA/storage/ps plumbing unchanged.

#### Reply routing design

The existing `handler_registry.handle()` error path accesses `data.fields.value.po.command` (a binary-specific field). PRT3 messages never carry this. To avoid that code path and keep a clean separation:

- **Command echo replies** (RA, RZ, ZL, AL, UL, AA, AD, PE/PM/PF echo) are routed through a dedicated `asyncio.Queue` (`_prt3_reply_queue`), not through `handler_registry`.
- **Unsolicited system events** (`G{ggg}N{nnn}A{aaa}`) are dispatched directly to `ps.sendEvent()`.
- **COMM status** (`COMM&ok/fail`) updates run-state directly.

#### Overridden methods

```python
class PRT3Paradox(Paradox):

    def __init__(self, retries=3):
        super().__init__(retries)
        self._prt3_reply_queue: asyncio.Queue = asyncio.Queue(maxsize=1)

    def _register_connection_handlers(self):
        # Only register the raw handler; skip binary EventMessageHandler/ErrorMessageHandler
        self.connection.register_raw_handler(
            PersistentHandler(self.on_connection_message)
        )

    async def connect(self) -> bool:
        """Skip binary handshake; await COMM&ok; create PRT3Panel directly."""
        # (full implementation — not calling super().connect())

    def on_connection_message(self, message: bytes):
        """Route incoming ASCII lines to reply queue or event dispatch."""
        line = message.decode("ascii", errors="replace").rstrip("\r\n")
        parsed = parse_line(line)
        if parsed is None:
            return
        if isinstance(parsed, PRT3CommStatus):
            self._handle_comm_status(parsed)
        elif isinstance(parsed, PRT3SystemEvent):
            self._handle_system_event(parsed)
        elif isinstance(parsed, (PRT3AreaStatus, PRT3ZoneStatus, PRT3LabelReply,
                                  PRT3CommandEcho)):
            try:
                self._prt3_reply_queue.put_nowait(parsed)
            except asyncio.QueueFull:
                logger.warning("PRT3 reply queue full, dropping: %s", parsed)

    async def _prt3_send_wait(
        self,
        command: bytes,
        timeout: float = cfg.IO_TIMEOUT,
    ) -> Optional[PRT3Message]:
        """Send an ASCII command and wait for exactly one reply."""
        # Drain stale replies
        while not self._prt3_reply_queue.empty():
            self._prt3_reply_queue.get_nowait()
        async with self.request_lock:
            self.connection.write(command)
            return await asyncio.wait_for(
                self._prt3_reply_queue.get(), timeout=timeout
            )

    def _handle_comm_status(self, msg: PRT3CommStatus):
        if msg.ok:
            logger.info("PRT3: COMM&ok — panel communication established")
        else:
            logger.error("PRT3: COMM&fail — panel communication lost")
            asyncio.create_task(self.disconnect())

    def _handle_system_event(self, evt: PRT3SystemEvent):
        # Build PRT3Event and dispatch via ps
        ...
```

#### `connect()` override flow

```
PRT3Paradox.connect()
  self.run_state = RunState.INIT
  await connection.connect()           # opens serial port
  # Wait for COMM&ok (panel sends this on startup)
  comm = await asyncio.wait_for(
      self._prt3_reply_queue.get(), timeout=15.0
  )
  if not isinstance(comm, PRT3CommStatus) or not comm.ok:
      self.run_state = RunState.ERROR
      return False
  self.panel = PRT3Panel(self)
  await self.panel.initialize_communication(cfg.PASSWORD)  # no-op
  self.run_state = RunState.CONNECTED
  return True
```

#### `PRT3Event(Event)` class

Defined alongside `PRT3Paradox` or in `event.py`. Constructs an `Event` directly from a `PRT3SystemEvent` dataclass and the `EVENT_MAP`, bypassing `LiveEvent`'s `po.command == 0xE` assertion.

```python
class PRT3Event(Event):
    def __init__(self, raw: PRT3SystemEvent, event_map: dict, label_provider=None):
        super().__init__(label_provider=label_provider)
        entry = event_map.get(raw.group)
        if entry is None:
            raise AssertionError(f"Unknown PRT3 event group: {raw.group}")
        self.major = raw.group
        self.minor = raw.number
        self.id    = raw.number
        self.partition = raw.area
        self.timestamp = int(time.time())
        # populate level, type, change, tags, message from entry
        ...
```

### 4.10 `paradox/hardware/prt3/__init__.py`

```python
from .panel import PRT3Panel
```

---

## 5. Test files and patterns to follow

### 5.1 Protocol framer tests — follow `tests/connection/test_serial_protocol.py`

**File: `tests/connection/prt3/test_protocol.py`**

Pattern:
```python
from unittest.mock import MagicMock
from paradox.connections.prt3.protocol import PRT3Protocol

def test_complete_line():
    handler = MagicMock()
    p = PRT3Protocol(handler)
    p.data_received(b"COMM&ok\r")
    handler.on_message.assert_called_once_with(b"COMM&ok\r")

def test_line_in_chunks():
    handler = MagicMock()
    p = PRT3Protocol(handler)
    p.data_received(b"COMM")
    p.data_received(b"&ok\r")
    handler.on_message.assert_called_once_with(b"COMM&ok\r")

def test_two_lines_in_one_chunk():
    handler = MagicMock()
    p = PRT3Protocol(handler)
    p.data_received(b"COMM&ok\rG001N005A001\r")
    assert handler.on_message.call_count == 2
```

Required cases:
- Single complete line
- Line split across N chunks
- Two lines in one chunk
- Empty (no `\r`) input: handler not called
- Lines ending `\r\n` (strip `\n` too, just in case)
- Garbage bytes before first `\r`: no crash, no spurious calls
- `send_message()` writes bytes directly

### 5.2 Parser tests — follow `tests/hardware/evo/test_action.py` (pure input/output)

**File: `tests/hardware/prt3/test_parser.py`**

Pattern: plain `assert`, parametrize where patterns repeat.
```python
import pytest
from paradox.hardware.prt3.parser import parse_line, PRT3AreaStatus, PRT3ZoneStatus, ...

def test_comm_ok():
    result = parse_line("COMM&ok")
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is True

def test_comm_fail():
    result = parse_line("COMM&fail")
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is False

def test_area_status_disarmed():
    result = parse_line("RA001DOOOOOO")
    assert isinstance(result, PRT3AreaStatus)
    assert result.area == 1
    assert result.armed == "D"
    assert result.alarm is False
    assert result.trouble is False

def test_area_status_armed():
    result = parse_line("RA001AOOOOOO")
    assert result.armed == "A"

@pytest.mark.parametrize("line,zone,status,alarm", [
    ("RZ001COOOO",  1, "C", False),
    ("RZ001OOOOO",  1, "O", False),
    ("RZ001TOOOO",  1, "T", False),
    ("RZ001OAOOO",  1, "O", True),
    ("RZ192COOOO",  192, "C", False),
])
def test_zone_status(line, zone, status, alarm):
    result = parse_line(line)
    assert isinstance(result, PRT3ZoneStatus)
    assert result.zone == zone
    assert result.status == status
    assert result.alarm == alarm

def test_zone_label():
    result = parse_line("ZL001Front Door      ")
    assert isinstance(result, PRT3LabelReply)
    assert result.kind == "ZL"
    assert result.index == 1
    assert result.label == "Front Door"

def test_system_event():
    result = parse_line("G001N005A006")
    assert isinstance(result, PRT3SystemEvent)
    assert result.group == 1
    assert result.number == 5
    assert result.area == 6

def test_unknown_line_returns_none():
    assert parse_line("JUNK") is None
    assert parse_line("") is None
```

Fixture file: `tests/hardware/prt3/fixtures/session_events.txt` — one raw line per line, used as a replay corpus.

### 5.3 Encoder tests — follow `tests/hardware/evo/test_action.py`

**File: `tests/hardware/prt3/test_encoder.py`**

```python
from paradox.hardware.prt3.encoder import (
    encode_request_area_status, encode_arm, encode_disarm, ...
)

def test_encode_request_area_status():
    assert encode_request_area_status(1) == b"RA001\r"
    assert encode_request_area_status(8) == b"RA008\r"

def test_encode_request_zone_status():
    assert encode_request_zone_status(1)   == b"RZ001\r"
    assert encode_request_zone_status(192) == b"RZ192\r"

def test_encode_arm_regular():
    assert encode_arm(1, "A", "1234") == b"AA01A1234\r"

def test_encode_arm_stay():
    assert encode_arm(2, "S", "123456") == b"AA02S123456\r"

def test_encode_disarm():
    assert encode_disarm(1, "1234") == b"AD011234\r"

def test_encode_quick_arm():
    assert encode_quick_arm(1, "A") == b"AQ01A\r"

def test_encode_panic_emergency():
    assert encode_panic_emergency(1) == b"PE01\r"

def test_encode_utility_key():
    assert encode_utility_key(1)   == b"UK001\r"
    assert encode_utility_key(251) == b"UK251\r"
```

### 5.4 Panel integration tests — follow `tests/hardware/evo/test_initialize_communication.py`

**File: `tests/hardware/prt3/test_panel.py`**

Uses `unittest.mock.MagicMock` for the `core` (`Paradox` instance) and monkey-patches `_prt3_send_wait`.

```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from paradox.hardware.prt3.panel import PRT3Panel

@pytest.fixture
def mock_core():
    core = MagicMock()
    core._prt3_send_wait = AsyncMock()
    core.storage = MagicMock()
    return core

@pytest.mark.asyncio
async def test_request_area_status_disarmed(mock_core):
    from paradox.hardware.prt3.parser import PRT3AreaStatus
    mock_core._prt3_send_wait.return_value = PRT3AreaStatus(
        area=1, armed="D", programming=False, trouble=False,
        ready=True, alarm=False, strobe=False, alarm_in_memory=False
    )
    panel = PRT3Panel(mock_core)
    result = await panel.request_status(1)
    assert result["partition_arm"][1] is False
    assert result["partition_alarm"][1] is False

@pytest.mark.asyncio
async def test_request_area_status_armed(mock_core):
    from paradox.hardware.prt3.parser import PRT3AreaStatus
    mock_core._prt3_send_wait.return_value = PRT3AreaStatus(
        area=1, armed="A", programming=False, trouble=False,
        ready=True, alarm=False, strobe=False, alarm_in_memory=False
    )
    panel = PRT3Panel(mock_core)
    result = await panel.request_status(1)
    assert result["partition_arm"][1] is True

@pytest.mark.asyncio
async def test_control_partitions_arm(mock_core):
    from paradox.hardware.prt3.parser import PRT3CommandEcho
    mock_core._prt3_send_wait.return_value = PRT3CommandEcho(
        prefix="AA01A", ok=True, payload=""
    )
    panel = PRT3Panel(mock_core)
    result = await panel.control_partitions([1], "arm")
    assert result is True
```

### 5.5 Event map tests — follow `tests/hardware/spectra_magellan/test_event_parsing.py`

**File: `tests/hardware/prt3/test_parser.py`** (add to same file or separate `test_events.py`)

```python
from paradox.hardware.prt3.event import EVENT_MAP
from paradox.hardware.prt3.runtime import PRT3Event
from paradox.hardware.prt3.parser import PRT3SystemEvent

def test_zone_open_event():
    raw = PRT3SystemEvent(group=1, number=5, area=2)
    evt = PRT3Event(raw, EVENT_MAP)
    assert evt.type == "zone"
    assert evt.change == {"open": True}

def test_zone_alarm_event():
    raw = PRT3SystemEvent(group=24, number=3, area=1)
    evt = PRT3Event(raw, EVENT_MAP)
    assert evt.type == "zone"
    assert evt.change.get("alarm") is True

def test_arm_event():
    raw = PRT3SystemEvent(group=10, number=42, area=1)
    evt = PRT3Event(raw, EVENT_MAP)
    assert evt.type == "partition"
    assert evt.change.get("arm") is True
```

---

## 6. Design decisions and rationale

### 6.1 Why `asyncio.Queue` for reply routing (not `handler_registry`)

`handler_registry.handle()` logs `data.fields.value.po.command` when no handler matches. PRT3 messages are plain dataclasses, not `Construct Container`s. Routing them through `handler_registry` would require either faking the `.fields.value.po.command` shape (fragile) or silencing the no-handler error globally (hides bugs). A dedicated `asyncio.Queue` keeps reply routing entirely inside PRT3-specific code with zero risk to existing behaviour.

### 6.2 Why `PRT3Paradox(Paradox)` subclass (not `connect()` guard)

The guard approach (`if cfg.CONNECTION_TYPE == "PRT3": return early`) pollutes `paradox.py` with repeated guards. A subclass puts all PRT3-specific orchestration in one file with a clean `super()` boundary. It also makes `main.py` changes minimal (one import line).

### 6.3 Why `SerialCommunication` is reused as base for `PRT3SerialConnection`

`SerialCommunication.connect()` handles: permissions check+fix, `connected_future`, timeout handler, `serial_asyncio.create_serial_connection()`, exception mapping. All of this is wanted. Only `make_protocol()` differs. Subclassing avoids duplicating ~40 lines of robust serial open code.

### 6.4 Why `property_map` is imported from `spectra_magellan`

The PAI property names (`open`, `arm`, `arm_stay`, `alarm`, `trouble`, `exit_delay`, etc.) are protocol-independent — they describe alarm state semantics. The Spectra map has all the properties PRT3 needs. Sharing it avoids drift between two copies of the same data. If PRT3 introduces new properties, they can be added to a local map that extends the shared one.

### 6.5 Why `load_memory()` is fully overridden (not `load_labels()`)

`Panel.load_memory()` calls `load_definitions()` then `load_labels()`. Both rely on `_eeprom_batch_reader()` → `send_wait(ReadEEPROM, ...)`. PRT3 has no EEPROM read facility. Overriding only `load_labels()` would leave `load_definitions()` attempting EEPROM reads and failing. It is cleaner and safer to override `load_memory()` entirely.

### 6.6 Why `request_status()` returns a flat dict (not a Container)

`Paradox.loop()` calls `deep_merge(*results)` then `_process_status(merged)` → `convert_raw_status()`. `convert_raw_status()` requires dict keys of the form `{type}_{property}` with `int`-keyed sub-dicts. This is a stable, documented internal format. Returning a plain Python dict in this format from PRT3 `request_status()` means the entire downstream status pipeline (`ps.sendMessage("status_update")`, `_on_status_update`, `MemoryStorage.update_container_object`, `Change` events, MQTT publish) works without modification.

---

## 7. Phased implementation plan

Each phase is independently testable before the next begins.

### Phase 1 — ASCII framer (transport layer)
**Files**: `connections/prt3/protocol.py`, `connections/prt3/connection.py`, `connections/prt3/__init__.py`
**Tests**: `tests/connection/prt3/test_protocol.py`
**Completion criteria**: `PRT3Protocol` passes all framer tests; no PAI runtime code touched.

### Phase 2 — Pure protocol layer (parser + encoder)
**Files**: `hardware/prt3/parser.py`, `hardware/prt3/encoder.py`
**Tests**: `tests/hardware/prt3/test_parser.py`, `tests/hardware/prt3/test_encoder.py`
**Completion criteria**: All parse and encode functions pass unit tests with fixture strings from the protocol reference. 100% coverage of the protocol table.

### Phase 3 — Event and property maps
**Files**: `hardware/prt3/event.py`, `hardware/prt3/property.py`
**Tests**: event map tests in `test_parser.py` or `test_events.py`
**Completion criteria**: All G-group codes in the protocol reference have entries; `PRT3Event` constructs cleanly from each.

### Phase 4 — Panel adapter
**Files**: `hardware/prt3/panel.py`, `hardware/prt3/__init__.py`
**Tests**: `tests/hardware/prt3/test_panel.py`
**Completion criteria**: `request_status()`, `load_memory()`, `control_partitions()`, `send_panic()` pass tests against mock core; unsupported methods raise `NotImplementedError`.

### Phase 5 — Runtime integration
**Files**: `hardware/prt3/runtime.py` (`PRT3Paradox`), `config.py` (2 insertions), `paradox.py` (2 insertions)
**Tests**: extend `test_panel.py` with `PRT3Paradox` integration test using a mock serial transport
**Completion criteria**: `PRT3Paradox.connect()` flows correctly with a simulated `COMM&ok` response; label load and status poll dispatch to storage; no existing tests break (`pytest tests/` clean).

### Phase 6 — End-to-end replay test
**Files**: `tests/hardware/prt3/fixtures/*.txt`, `tests/hardware/prt3/test_panel.py`
**Tests**: replay-based test that feeds a session transcript through `PRT3Protocol` + `PRT3Paradox.on_connection_message()` and asserts final storage state
**Completion criteria**: storage state after replay matches expected partition arm states and zone open states.

### Phase 7 — Config example and docs
**Files**: `config/pai-prt3.conf.example`; update `docs/prt3-architecture.md` if anything changed
**Completion criteria**: config example is loadable by `cfg.load()`; no undocumented limitations.

---

## 8. Risk register

| Risk | Mitigation |
|---|---|
| `_process_status` format changes in future PAI | Our flat-dict format matches the existing contract; any upstream change affects all backends equally |
| `HandlerRegistry` error path on `data.fields.value.po.command` | Fully avoided by reply-queue design; existing `handler_registry` is never fed PRT3 messages |
| `LiveEvent.__init__` asserts `po.command == 0xE` | Fully avoided by `PRT3Event(Event)` subclass; `LiveEvent` is never called for PRT3 events |
| `SerialCommunication.connect()` changes upstream | Only `make_protocol()` is overridden; any fix to the open logic is automatically inherited |
| `load_memory()` EEPROM path called for PRT3 | Fully avoided by overriding `load_memory()` entirely |
| Existing tests broken by config.py change | `CONNECTION_TYPE` constraint is widened, not narrowed; all existing tests pass `"Serial"` or `"IP"` |
| Baud mismatch (panel default 9600, control4 guide recommends 19200) | Documented in limitations; `PRT3_SERIAL_BAUD` config key lets user set either |
