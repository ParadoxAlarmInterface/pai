# PAI connection-stability evaluation

**Scope:** defects in the PAI codebase that could cause or worsen repeated loss of
connection to a Paradox panel, and slow/failed recovery afterwards.
**Base:** `ParadoxAlarmInterface/pai` @ `be1e46e` (branch `dev`).
**Method:** manual read of the connect/poll/reconnect paths — `main.py`, `paradox.py`,
`connections/*`, `lib/handlers.py`, `lib/async_message_manager.py`, `lib/stun.py`.

Findings are ordered by how likely they are to be contributing to a "regularly loses
connection" symptom. Line numbers are against the base commit.

---

## Tier 1 — most likely to be driving the symptom

### 1. `IO_TIMEOUT` from `pai.conf` is silently ignored on every request path

`cfg.IO_TIMEOUT` is used as a **default argument value**, which Python evaluates once at
import time:

- `paradox/paradox.py:497` — `send_wait(..., timeout=cfg.IO_TIMEOUT, ...)`
- `paradox/lib/async_message_manager.py:42` — `wait_for_message(..., timeout=cfg.IO_TIMEOUT)`
- `paradox/lib/handlers.py:97` — `wait_until_complete(self, handler, timeout=cfg.IO_TIMEOUT)`
- `paradox/connections/ip/connection.py:98` — `wait_for_ip_message(self, timeout=cfg.IO_TIMEOUT)`

`paradox/console_scripts/pai_run.py` imports `paradox.main` (which imports `Paradox`)
**before** `main()` calls `cfg.load()`. So all four defaults freeze at the built-in
default of `0.5` (`paradox/config.py:93`), regardless of what the user configures.

Consequence: the single most useful tuning knob for a marginal link is a no-op. Anyone
raising `IO_TIMEOUT` to cope with a slow IP150 or a busy panel sees no change and
concludes the problem is elsewhere.

Note the call sites that read `cfg.IO_TIMEOUT` at *call* time — `protocol_base.py:56`,
`hardware/prt3/panel.py` — do honour the config, so behaviour is inconsistent between
subsystems.

Fix: sentinel default (`timeout=None`) resolved to `cfg.IO_TIMEOUT` inside the function.

### 2. The poll cycle has no upper bound, and degrades into a poll storm

`Paradox.loop()` (`paradox/paradox.py:408-441`):

```python
tstart = time.time()
result = await asyncio.gather(*self.panel.get_status_requests())
...
max_wait_time = max((tstart + cfg.KEEP_ALIVE_INTERVAL) - time.time(), 0)
await asyncio.wait_for(self.loop_wait_event.wait(), max_wait_time)
```

Every status request is serialised behind `self.request_lock` (`paradox.py:508`) and
`send_wait` retries **5** times with a per-attempt budget of `timeout * 2`.

For EVO, `status_request_addresses` is 14 addresses (`hardware/evo/parsers.py:180`,
keys `1-11, 16, 57, 58`); Spectra/Magellan is 7. Worst case for EVO:

    14 addresses x 5 retries x (2 x 0.5 s) = ~70 s per cycle

against a `KEEP_ALIVE_INTERVAL` of 10 s. Once a cycle overruns the interval,
`max_wait_time` clamps to `0` and the loop immediately starts another full poll with no
idle gap — so a panel that is *momentarily* slow gets hit with back-to-back polls, which
is exactly the wrong response. There is no "skip this cycle, we're behind" guard and no
cap on cycle duration.

Fix: bound the whole cycle (e.g. `asyncio.wait_for(gather(...), KEEP_ALIVE_INTERVAL)`),
lower `retries` for status polls, and enforce a minimum idle gap between cycles.

### 3. Reconnect backoff is `2 ^ retry` — bitwise XOR, not exponentiation

`paradox/main.py:124`:

```python
retry_time_wait = 2 ^ retry
retry_time_wait = 30 if retry_time_wait > 30 else retry_time_wait
```

`^` is XOR in Python. The actual wait sequence is:

| retry | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wait (s) | 3 | **0** | 1 | 6 | 7 | 4 | 5 | 10 | 11 | 8 | 9 | 14 |

It is not monotonic, it never approaches the 30 s cap in any realistic number of
attempts, and the **second** retry waits **zero seconds**. An IP150 accepts a single
session at a time and needs time to tear the old one down; reconnecting immediately is
the reliable way to be refused and stay refused. Compounds directly with finding 4.

Fix: `retry_time_wait = min(2 ** retry, 30)`, ideally with jitter.

### 4. Failed IP connection attempts leak the previous socket

`MultiAttemptConnection.connect()` (`paradox/connections/ip/connection.py:24-49`) retries
`_try_connect()` up to 3 times. But `_try_connect` for both local and STUN connections
(`ip/connection.py:113-121` and `143-151`) assigns `self._protocol` as soon as
`create_connection` returns, *then* runs the module handshake:

```python
_, self._protocol = await asyncio.get_running_loop().create_connection(...)
await IPModuleConnectCommand(self).execute()   # <- can raise
self.connected = True
```

If the handshake raises (timeout, auth failure), the exception is caught in `connect()`
and the loop retries — overwriting `self._protocol` with a new connection **without
closing the previous transport**. The orphaned socket is only closed whenever GC gets
around to it; `ConnectionProtocol.__del__` (`protocol_base.py:89`) deliberately does not
close the transport.

Result: up to 3 orphaned TCP sessions per `connect()` call, each still occupying the IP
module's single session slot — so the retries are competing with PAI's own leaked
sockets. There is also **no delay** between the three attempts.

Fix: `await self.close()` in the exception path before retrying, and sleep between tries.

---

## Tier 2 — STUN / paradoxmyhome path (blocking I/O on the event loop)

### 5. `refresh_session_if_required()` does blocking socket I/O on the event loop

`StunSession.refresh_session_if_required()` (`connections/ip/stun_session.py:141-153`) is
called **synchronously** from `StunIPConnection.write()` (`ip/connection.py:136-141`),
which runs on the asyncio event loop. It calls `stun_control.send_refresh_request()` and
`receive_response()`.

`StunClient` (`paradox/lib/stun.py:305-311`) creates a plain blocking socket and never
calls `settimeout()`; `receive_response()` (`lib/stun.py:339-340`) is a bare
`self.sock.recv(2048)`.

So every ~500 s, a STUN user's entire event loop can block indefinitely inside `write()`
on a half-dead TURN control socket. Nothing else runs: no `data_received`, no keepalive,
no MQTT. When it finally returns, every pending request has timed out at once and the
session is torn down. This is a strong match for periodic, roughly-regular dropouts on
paradoxmyhome setups.

`StunClient.__init__` also does a blocking `sock.connect()` (`lib/stun.py:311`), reached
from `async def _stun_tcp_change_request` (`stun_session.py:110`).

Fix: `sock.settimeout(...)` on all STUN sockets, and run the refresh in an executor (or
convert to non-blocking) rather than inline in `write()`.

### 6. `time.sleep(5)` inside an async function, and an unbounded HTTP call

`StunSession._get_site_info` (`stun_session.py:180-198`) is `async def` but calls
`time.sleep(5)` (line 196) on retry — blocking the event loop for up to 25 s across 5
attempts. The `requests.get` on line 187 has **no timeout**, so a stalled SWAN API call
hangs the connect path forever with no recovery.

Fix: `await asyncio.sleep(5)`; pass `timeout=` to `requests.get`.

### 7. STUN response parsing assumes one `recv()` returns a whole message

`lib/stun.py:339-345`:

```python
buf = self.sock.recv(2048)
...
assert len(attributes) == body_length
```

TCP does not guarantee message boundaries. A segmented STUN response trips the assert,
which is swallowed by the generic `except Exception` in `MultiAttemptConnection.connect`
and reported as an unexplained connect failure. Needs a read-until-complete loop.

### 8. Failed STUN refresh does not mark the connection dead

`stun_session.py:151` sets `self.connected = False` — but `StunSession` has no
`connected` attribute (see `__init__`, lines 38-48) and nothing reads it. The assignment
just creates a stray attribute. The intent (propagate the dead session) is lost; only the
raised `StunSessionRefreshFailed` carries the signal.

---

## Tier 3 — smaller, still real

### 9. `busy.release()` can be called without holding the lock

`paradox/paradox.py:412` / `:428`:

```python
try:
    await self.busy.acquire()      # inside the try
    ...
finally:
    self.busy.release()            # runs even if acquire() never succeeded
```

`busy` is contended — the IP interface holds it at
`interfaces/ip_interface/client_connection.py:173`. If `acquire()` is cancelled (shutdown,
or a BabyWare client holding the lock while PAI is stopping), the `finally` raises
`RuntimeError: Lock is not acquired`, which escapes `loop()` and is caught by the generic
handler in `main.py:158` — turning a clean stop into an exception-driven restart.

Fix: `async with self.busy:` around the body.

### 10. `asyncio.gather` abandons sibling requests on first failure

`paradox.py:413`. `gather` without `return_exceptions` propagates the first
`StatusRequestException` but does **not** cancel the remaining status requests. They stay
queued on `request_lock` and overlap with the next cycle's requests, so a single slow
address compounds into cross-cycle contention rather than being isolated.

### 11. A failed close leaves the connection in a half-torn-down state

`connections/connection.py:52-56`:

```python
async def close(self):
    if self._protocol:
        await self._protocol.close()   # can raise
        self._protocol = None
    self.connected = False
```

`ConnectionProtocol.close()` (`protocol_base.py:47-57`) awaits `self._closed`, and
`connection_lost` sets an **exception** on that future when the transport died with an
error (`protocol_base.py:80-83`). Awaiting it therefore re-raises — which is the normal
case when closing after a fault. Neither `_protocol = None` nor `connected = False` runs.
The `asyncio.wait_for(..., cfg.IO_TIMEOUT)` on the same line can also raise
`TimeoutError` with the same effect.

Fix: wrap in `try/finally` so the state reset always happens.

### 12. A status parse failure crashes the merge instead of counting as a missing reply

`Panel.handle_status` (`hardware/panel.py:334-355`) returns `None` when the address has no
parser or the parse throws. `request_status` returns that `None` straight through
(`evo/panel.py:233`, `spectra_magellan/panel.py:239`), and `deep_merge`
(`lib/utils.py:66-69`) then calls `d2.items()` on `None` → `AttributeError`.

That is caught by the catch-all `except Exception: logger.exception("Loop")`
(`paradox.py:425`), so `replies_missing` is **not** incremented — the cycle's entire
status update is dropped silently and the health counter never notices.

### 13. `disconnect()` can construct a connection object during shutdown

`Paradox.disconnect()` (`paradox.py:913-920`) reaches `self.connection`, which is a lazy
property that *builds* a `Connection` and registers handlers when `_connection is None`
(`paradox.py:122-174`). `main._run`'s `exit_handler` calls `disconnect()`
unconditionally, so shutting down before a first connection constructs one just to ask
whether it is connected. Harmless today, but it makes the shutdown path depend on config
validity (`raise AssertionError(f"Invalid connection type: ...")` at `paradox.py:170`).

---

## Suggested order of work

1. Finding 1 (`IO_TIMEOUT`) — one-line-per-site fix, immediately gives users a working knob.
2. Finding 3 (`2 ^ retry`) — one-line fix, stops PAI hammering the module after a drop.
3. Finding 4 (socket leak) — stops PAI competing with itself for the module's session slot.
4. Finding 2 (poll cycle bound) — the structural fix; needs a little design.
5. Findings 5-7 if the deployment uses STUN/paradoxmyhome.

## Diagnostics worth collecting first

To confirm which path is in play, set `LOGGING_LEVEL_CONSOLE = 10` (DEBUG) and look for:

- `send/receive timeout in ...` lines from `paradox.py:551` — frequency tells you whether
  finding 1/2 is biting.
- `Loop: Replies missing: N` — how close each cycle gets to the forced-disconnect
  threshold of 3.
- `Connection recovered after ... down` / `Panel connection ended after ... up`
  (`main.py:105`, `:114`) — gives the actual uptime/outage distribution.
- `Connecting. Try n/3` bursts with no gap — finding 4.
- `STUN Session Refresh` immediately preceding a stall — finding 5.
