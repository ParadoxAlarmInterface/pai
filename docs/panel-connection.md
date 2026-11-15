# Panel connection lifecycle

`Paradox` coordinates the lifecycle; it does not select panel families or build
their startup messages.

| Owner | Responsibility |
| --- | --- |
| `connections.create_connection()` | Choose the configured transport |
| `Connection` | Open/close the link, transport framing, link authentication |
| `hardware.detect_panel()` | Run the link's registered discovery strategies in order |
| Panel driver | Discovery, login, message parsing, protocol framing and logout |
| `Paradox` | Install the decoder, publish identity after login, run polling and state updates |

## Discovery contract

`Connection.panel_protocol` names the initial wire protocol (`binary` by default).
`hardware/registry.py` explicitly composes its ordered discovery callables and
the product maps declared by each family.

A discovery callable takes `core` and returns `(panel, DetectedPanel)` after
installing the driver with `core.install_panel(panel)`. It may return `None`
**only when its identification probe goes unanswered**. Errors after any reply,
including transport-handshake and StartCommunication timeouts, propagate:
they must not trigger another protocol's probe.

`BinaryPanel` implements the shared InitiateCommunication/StartCommunication
exchange and decoder. After identification it calls the connection's
`on_initiate_communication` hook, then the product driver's `start_communication`
override (if any). EVO and Spectra use the shared exchange; MG6250 skips
StartCommunication. Only a silent identification probe falls through to
Digiplex's source-zero discovery and bounded, line-silent busy-session retries.
PRT3 uses its own discovery and ASCII liveness check with no binary probes.

## Driver hooks

- `initialize_communication(password)` authenticates or checks link liveness.
- `variable_message_length` and `make_framer()` configure framing at installation.
  A `None` framer keeps the transport's existing framing, including E0FE wrapping.
- `build_close_connection()` returns logout bytes, or `None` when there is no logout.
  The coordinator then calls `Connection.end_session()` before closing the link.
- `supports_time_sync` gates clock synchronization.
- `handle_async_message(message)` handles additional unsolicited protocol messages.
  Its persistent dispatcher is registered once per connection, not per installation.
- `on_partition_command(partitions, command)` applies driver-specific state after an
  accepted command. `send_utility_key(key)` raises `NotImplementedError` by default.

For another binary product, implement a `BinaryPanel` subclass and add its product
mapping to its family's `PRODUCTS`. For another wire protocol, implement a `Panel`
driver and its discovery callable, name the link's initial protocol, and register
the strategy in `registry.py`. The coordinator and existing drivers need no edits.

`create_panel(core, response)` remains available to offline capture decoders.
Without a response it returns a `BinaryPanel` bootstrap decoder, not a bare `Panel`.
