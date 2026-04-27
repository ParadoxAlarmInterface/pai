# Code Review: PR #596 — feat: add PRT3 ASCII serial connection type

> **Review authored by:** Copilot SWE Agent  
> **PR:** https://github.com/ParadoxAlarmInterface/pai/pull/596  
> **Branch:** `NaanyaBiz:feature/prt3-connection` → `ParadoxAlarmInterface:dev`  
> **Diff stats:** 5 595 additions, 17 deletions, 33 changed files

---

## High-Level Summary

PR #596 adds the Paradox PRT3 printer module as a third PAI connection backend, alongside the existing `Serial` (binary) and `IP` backends. The PRT3 uses a vendor-documented ASCII serial protocol over a standard serial cable. This is genuinely valuable: recent Paradox firmware versions have broken both native binary serial integrations (via encryption) and IP150 integrations (via third-party lockout). The PRT3 module is unaffected by both.

The core implementation — `parser.py`, `encoder.py`, `adapter.py`, `event.py` — is clean, well-tested, and self-contained. The integration layer has four blocking bugs and several architectural issues that need to be addressed before merging.

---

## 🔴 Blocking Issues

### Bug #1 — `async_message_manager.py`: Assertion removal weakens all callers

**File:** `paradox/lib/async_message_manager.py`

```python
# Before
def can_handle(self, data: Container) -> bool:
    assert isinstance(data, Container)   # ← safety net for the entire binary pipeline

# After (this PR)
def can_handle(self, data) -> bool:
    if not isinstance(data, Container):
        return False
```

**Problem:** The `assert` was a programmatic contract enforcer for the binary-protocol message pipeline. Replacing it with `return False` means any mis-routed object anywhere in the codebase now *silently drops a message* instead of crashing loudly during development. This is a correctness regression for all non-PRT3 users.

**Root cause:** PRT3 dataclasses should not be routed through `EventMessageHandler`/`ErrorMessageHandler` at all. The fix should be architectural — a separate handler path for PRT3 messages — not a weakened type guard on the existing binary-protocol handlers.

**Fix direction:** Register a dedicated `PRT3EventHandler` that only handles PRT3 dataclasses. Keep the `isinstance(data, Container)` assertion intact for binary-protocol handlers.

---

### Bug #2 — `mqtt/core.py`: Late-registrar `on_connect` passes `None` args to all MQTT handlers

**File:** `paradox/interfaces/mqtt/core.py`

```python
# Added by this PR
if self.connected:
    args = self._last_connect_args or (self.client, None, None, None, None)
    cls.on_connect(*args)
```

**Problem:** When `_last_connect_args` is `None` (MQTT broker not yet connected), every late-registering interface receives `reason_code=None`. Any handler that calls `reason_code.is_failure` or `reason_code.value` will throw `AttributeError` at runtime. This bug is *not PRT3-specific* — it affects every MQTT interface registered after startup.

No test covers the `_last_connect_args is None` branch.

**Fix direction:** Only replay `on_connect` if `_last_connect_args is not None`. If it's `None`, defer until the first real connect event rather than passing synthetic `None` args.

---

### Bug #3 — `panel.py`: `PRT3BufferFull` (`!`) has no fast-fail in `_prt3_send_wait`

**File:** `paradox/hardware/prt3/panel.py`

**Problem:** When the panel's receive buffer overflows it emits `!` (`PRT3BufferFull`). The predicate in `_prt3_send_wait` only matches `PRT3CommandEcho`, so a `PRT3BufferFull` is silently ignored and the caller waits the full `IO_TIMEOUT` before returning `None`.

During `load_labels` — which polls `AL`/`ZL`/`UL` one-by-one for every configured area, zone, and user — a single buffer overflow causes the *entire poll chain* to stall for `n_elements × IO_TIMEOUT` seconds. With default `PRT3_MAX_ZONES=96` + `PRT3_MAX_AREAS=8` + `PRT3_MAX_USERS=32` = 136 polls, a buffer overflow at startup causes a multi-minute freeze before the first connection fails over.

**Fix direction:** `_prt3_send_wait` should register a secondary predicate matching `PRT3BufferFull` and return it immediately (or raise a distinguishable exception) on receipt, allowing the caller to retry or abort quickly.

---

### Bug #4 — `panel.py` + `paradox.py`: Invalid `PRT3_USER_CODE` causes unhandled `ValueError` at arm time

**File:** `paradox/hardware/prt3/panel.py`, `paradox/paradox.py`

```python
# encoder._validate_code() raises ValueError on non-numeric or >6-digit code
# _build_partition_cmd() does NOT catch it
# paradox.py control_partition() does NOT catch it
# (contrast with control_utility_key() which correctly catches ValueError)
```

**Problem:** The config validator accepts any string for `PRT3_USER_CODE` (only type-checked, not format-validated). Setting `PRT3_USER_CODE = "abc"` or `"1234567"` (7 digits) and then issuing a disarm command causes an unhandled `ValueError` to propagate up the async task chain, potentially crashing the run loop.

**Fix direction:** Validate `PRT3_USER_CODE` format at config load time (startup), not at first use. A regex check `r'^\d{1,6}$'` or equivalent should be applied in `Config.__init__` or as a `Config.postprocess()` step.

---

## 🟡 Architecture Issues

### Architecture #1 — `PRT3Panel(Panel)` violates Liskov Substitution Principle

**File:** `paradox/hardware/prt3/panel.py`

`Panel` carries heavy binary-protocol surface: `_eeprom_read_address`, `_eeprom_batch_reader`, binary `parse_message`/`get_message` (which look up `construct` parsers). None of these are usable or meaningful in `PRT3Panel`. More critically, `control_zones()` and `control_module_pgm_outputs()` raise `NotImplementedError` — methods that callers (MQTT handlers) expect to return `bool`.

The correct model is a two-level hierarchy:

```
BasePanel (protocol-neutral abstract interface)
├── BinaryPanel(BasePanel)  — EEPROM helpers, binary framing, Container parsing
│   ├── EvoPanel(BinaryPanel)
│   └── SpectraPanel(BinaryPanel)
└── PRT3Panel(BasePanel)    — ASCII commands, no EEPROM surface
```

This is the right moment to extract `BinaryPanel`. Skipping it now means any future `CloudPanel`, `BLEPanel`, or other non-binary backend faces the same structural problem.

**Immediate mitigation (if refactor is deferred):** Change `control_zones()` and `control_module_pgm_outputs()` from `raise NotImplementedError` to `return False` with a `logger.warning`. This at least honours the `Panel` interface contract of returning `bool`.

---

### Architecture #2 — 9 `CONNECTION_TYPE == "PRT3"` string guards erode Panel polymorphism

**Files:** `paradox/paradox.py`, `paradox/interfaces/mqtt/basic.py`, `paradox/interfaces/mqtt/homeassistant.py`

The existing codebase has *zero* `== "Serial"` or `== "IP"` guards in the orchestrator layer — protocol differences are expressed through Panel subclass polymorphism. This PR adds 9 string comparisons in shared code.

Five of these nine guards are candidates for Panel interface methods rather than orchestrator conditionals:

| Guard location | Protocol difference | Suggested Panel method |
|---|---|---|
| `paradox.py` `sync_time()` | No SetTimeDate command | `Panel.supports_time_sync: bool` or no-op base |
| `paradox.py` `_clean_session()` | No binary CloseConnection frame | `Panel.send_close_connection()` with no-op override |
| `paradox.py` `_register_connection_handlers()` | PRT3 needs extra handler | `Panel.register_protocol_handlers(connection)` |
| `homeassistant.py` `_publish_when_ready()` | Utility key discovery | `Panel.get_utility_key_configs() -> dict` |
| `paradox.py` `control_utility_key()` | UK command | `Panel.send_utility_key(key) -> bool` in base, raises in non-PRT3 |

The three connection-selection branches (in the `connection` property) are genuinely structural and belong in `paradox.py`.

---

### Architecture #3 — `runtime.py` placeholder should be deleted

**File:** `paradox/hardware/prt3/runtime.py`

The PR adds an empty file with a docstring saying it is "reserved for future PRT3-specific runtime extensions." Empty placeholder files accumulate; future maintainers cannot distinguish intentionally empty files from abandoned work. Delete it; re-add it when it has content.

---

### Architecture #4 — `mqtt/core.py` late-registrar fix should be a separate commit

**File:** `paradox/interfaces/mqtt/core.py`

The `_last_connect_args` fix (firing `on_connect` for late-registering MQTT interfaces) is a legitimate general bug fix that benefits all connection types. Bundled into a PRT3 feature PR it cannot be independently cherry-picked, backported, or reverted. It should be its own commit/PR with its own rationale so its history is clear.

---

## 🟢 Minor Issues

### Minor #1 — `PRT3_SERIAL_BAUD` range accepts hardware-invalid values

**File:** `paradox/config.py`

```python
"PRT3_SERIAL_BAUD": (9600, int, (2400, 115200)),  # ← accepts 38400, 57600, etc.
```

The PRT3 module supports exactly 9600 baud and 19200 baud (hardware DIP switch). Values like 38400 are silently accepted by the config validator; the port opens, but the panel never responds. No error is surfaced until `PRT3_COMM_TIMEOUT` expires.

**Fix:** Use a set validator: `(9600, int, [9600, 19200])`, matching the pattern already used for `CONNECTION_TYPE`.

---

### Minor #2 — G065 per-N overrides bypass `EVENT_MAP`, invisible to maintainers

**File:** `paradox/hardware/prt3/event.py`

`EVENT_MAP` is presented as the authoritative lookup table for PRT3 G-group codes. However, `from_prt3()` contains an inline override for G065 (`exit_delay`, `entry_delay`) that bypasses `EVENT_MAP` entirely:

```python
if prt3_event.group == 65:
    if n == 1:
        descriptor = { "type": "partition", ... "exit_delay" }
    elif n == 2:
        descriptor = { "type": "partition", ... "entry_delay" }
```

Future maintainers reading `EVENT_MAP` miss the most important status events. Move the per-N overrides into `EVENT_MAP` as a nested `"number_overrides"` dict or document them with an explicit cross-reference comment.

---

### Minor #3 — `control_zones()` / `control_outputs()` raise instead of returning `False`

**File:** `paradox/hardware/prt3/panel.py`

```python
async def control_zones(self, zones: list, command: str) -> bool:
    raise NotImplementedError("PRT3 has no zone bypass command...")
```

The `Panel` interface contract returns `bool`. MQTT handlers for zone control do not wrap calls in `try/except NotImplementedError`. A user attempting to bypass a zone via MQTT will get an unhandled exception in the async task.

**Fix:** Return `False` with `logger.warning("Zone bypass not supported on PRT3")`.

---

### Minor #4 — Bare `except Exception` in event dispatch hides storage inconsistency

**File:** `paradox/paradox.py`

```python
def handle_prt3_event_message(self, message):
    ...
    try:
        evt = PRT3Event.from_prt3(...)
        self.storage.update_container_object(...)
        ps.sendEvent(evt)
        if evt.type == "partition":
            self._update_partition_states()
    except Exception:
        logger.exception("handle_prt3_event_message")
```

All exceptions are swallowed. If `storage.update_container_object` raises (e.g., unknown element type), storage is left inconsistent — zone alarm state not updated — with no indication to the caller that the event was dropped.

**Fix:** Break out expected exceptions (`KeyError`, `AttributeError`) explicitly. The catch-all can remain but should increment a metric or set a degraded-state flag.

---

### Minor #5 — User code safety claim is narrower than stated

**File:** `paradox/config.py` (comment)

The PR states "This value is never written to logs." This is true for explicit logger calls in `panel.py`. However, the raw command bytes `AA001A1234\r` (arm with user code) are passed to `connection.write()`. If the serial layer has byte-level debug tracing enabled, the user code is visible in the output.

**Fix:** Document this nuance. Consider masking: log `command_bytes[:5] + b"***"` in the retry warning path instead of the full bytes.

---

### Minor #6 — No tests for three critical runtime paths

**Files:** `tests/hardware/prt3/`

The test suite covers parser round-trips, encoder boundaries, and MQTT happy paths well. Three critical paths lack coverage:

1. **Reconnection:** `PRT3Panel` is re-instantiated on reconnect; the label cache is lost. No test verifies that reconnect cleanly rebuilds state.
2. **Buffer overflow:** No test exercises the `PRT3BufferFull` path during a command send, verifying whether fast-fail works or a full-timeout storm occurs.
3. **Bad config at arm time:** `PRT3_USER_CODE = "abc"` → disarm → `ValueError` propagation has no end-to-end test. The encoder's `_validate_code` is tested in isolation, but the config→arm→exception path is not.

---

## ✅ Strengths Worth Preserving

1. **Clean module architecture.** `parser.py`/`encoder.py`/`adapter.py` separation is correct and mirrors existing EVO/Spectra patterns.
2. **Strong test coverage** on the core parsing/encoding/adapting layer.
3. **Backward compatibility is near-perfect.** Zero regression risk to existing connection types.
4. **Security note on `PRT3_USER_CODE`** is exactly right.
5. **`handlers.py` fix** (catching `AttributeError` on `data.fields.value.po.command`) is elegant.
6. **Late-registrar MQTT fix** is a real bug fix worth keeping (just in its own commit).

---

## Summary Table

| # | Issue | Severity |
|---|-------|----------|
| Bug #1 | `async_message_manager` assertion removal weakens all callers | **Blocking** |
| Bug #2 | MQTT `on_connect` fallback passes `None` to all handlers | **Blocking** |
| Bug #3 | `PRT3BufferFull` has no fast-fail; causes full-timeout storm at startup | **Blocking** |
| Bug #4 | Invalid `PRT3_USER_CODE` raises uncaught `ValueError` at arm time | **Blocking** |
| Arch #1 | `PRT3Panel(Panel)` LSP violation; dead binary surface inherited | Major |
| Arch #2 | 9 string-guard conditionals erode Panel polymorphism pattern | Major |
| Arch #3 | `runtime.py` empty placeholder should be deleted | Minor |
| Arch #4 | `mqtt/core.py` fix should be a separate commit | Minor |
| Minor #1 | `PRT3_SERIAL_BAUD` range accepts hardware-invalid values | Minor |
| Minor #2 | G065 per-N overrides bypass `EVENT_MAP` | Minor |
| Minor #3 | `control_zones()`/`control_outputs()` raise instead of returning `False` | Minor |
| Minor #4 | Bare `except Exception` hides storage inconsistency | Minor |
| Minor #5 | User code safety claim is narrower than stated | Nitpick |
| Minor #6 | Missing tests: reconnect, buffer-full, bad config at arm time | Minor |

**Verdict:** Do not merge as-is. Address bugs #1–#4 before merge. The architectural issues (#1–#2) are strongly recommended before v1 ships to avoid compounding technical debt as more backends are added.
