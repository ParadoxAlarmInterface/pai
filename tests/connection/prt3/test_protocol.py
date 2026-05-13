"""
Tests for paradox.connections.prt3.protocol — PRT3Protocol framer.

Coverage:
  - Module imports and type hierarchy (smoke)
  - data_received(): complete line, two-in-one-chunk, split-across-chunks,
    partial (no \\r yet), empty / whitespace-only lines are discarded
  - variable_message_length(): no-op (does not raise)
  - send_message(): delegates to transport.write(); raises ConnectionError when
    no active transport
"""

from typing import List, Tuple
from unittest.mock import MagicMock

import pytest

from paradox.connections.protocols import ConnectionProtocol
from paradox.connections.prt3.connection import PRT3SerialConnection
from paradox.connections.prt3.protocol import PRT3Protocol
from paradox.connections.serial_connection import SerialCommunication

# ---------------------------------------------------------------------------
# Smoke / type hierarchy
# ---------------------------------------------------------------------------


def test_prt3_protocol_is_connection_protocol():
    assert issubclass(PRT3Protocol, ConnectionProtocol)


def test_prt3_serial_connection_is_serial_communication():
    assert issubclass(PRT3SerialConnection, SerialCommunication)


def test_prt3_serial_connection_make_protocol_returns_prt3_protocol():
    conn = PRT3SerialConnection.__new__(PRT3SerialConnection)
    proto = conn.make_protocol()
    assert isinstance(proto, PRT3Protocol)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Handler:
    """Minimal ConnectionHandler that records on_message() calls."""

    def __init__(self):
        self.messages: List[bytes] = []

    def on_message(self, raw: bytes):
        self.messages.append(raw)

    def on_connection(self):
        # Required by ConnectionHandler interface; no-op in test stub.
        pass

    def on_connection_loss(self):
        # Required by ConnectionHandler interface; no-op in test stub.
        pass


def _make_proto() -> Tuple[PRT3Protocol, _Handler]:
    handler = _Handler()
    proto = PRT3Protocol(handler)
    return proto, handler


# ---------------------------------------------------------------------------
# Framing: data_received()
# ---------------------------------------------------------------------------


def test_complete_line_emitted():
    proto, handler = _make_proto()
    proto.data_received(b"COMM&ok\r")
    assert handler.messages == [b"COMM&ok\r"]


def test_cr_included_in_emitted_bytes():
    proto, handler = _make_proto()
    proto.data_received(b"G001N002A003\r")
    assert handler.messages[0].endswith(b"\r")


def test_two_lines_in_one_chunk():
    proto, handler = _make_proto()
    proto.data_received(b"COMM&ok\rG001N002A003\r")
    assert len(handler.messages) == 2
    assert handler.messages[0] == b"COMM&ok\r"
    assert handler.messages[1] == b"G001N002A003\r"


def test_line_split_across_two_chunks():
    proto, handler = _make_proto()
    proto.data_received(b"COMM&")
    assert handler.messages == []  # incomplete — not yet emitted
    proto.data_received(b"ok\r")
    assert handler.messages == [b"COMM&ok\r"]


def test_partial_line_not_emitted_until_cr():
    proto, handler = _make_proto()
    proto.data_received(b"COMM&ok")
    assert handler.messages == []


def test_buffer_drained_after_complete_line():
    proto, _ = _make_proto()
    proto.data_received(b"COMM&ok\r")
    assert proto.buffer == b""


def test_partial_remainder_kept_in_buffer():
    proto, handler = _make_proto()
    proto.data_received(b"COMM&ok\rG001N002")
    assert len(handler.messages) == 1
    assert proto.buffer == b"G001N002"


def test_empty_line_discarded():
    """A bare \\r with no payload must not call on_message()."""
    proto, handler = _make_proto()
    proto.data_received(b"\r")
    assert handler.messages == []


def test_whitespace_only_line_discarded():
    proto, handler = _make_proto()
    proto.data_received(b"   \r")
    assert handler.messages == []


def test_empty_line_between_real_lines():
    proto, handler = _make_proto()
    proto.data_received(b"COMM&ok\r\rG001N002A003\r")
    assert len(handler.messages) == 2
    assert handler.messages[0] == b"COMM&ok\r"
    assert handler.messages[1] == b"G001N002A003\r"


def test_multiple_splits():
    """Three lines arriving byte-by-byte."""
    proto, handler = _make_proto()
    payload = b"A\rB\rC\r"
    for byte in payload:
        proto.data_received(bytes([byte]))
    assert handler.messages == [b"A\r", b"B\r", b"C\r"]


# ---------------------------------------------------------------------------
# variable_message_length() is a no-op
# ---------------------------------------------------------------------------


def test_variable_message_length_noop():
    proto, _ = _make_proto()
    proto.variable_message_length(True)  # should not raise
    proto.variable_message_length(False)  # should not raise
    proto.variable_message_length(42)  # arbitrary arg — should not raise


# ---------------------------------------------------------------------------
# send_message() raises when transport is not active
# ---------------------------------------------------------------------------


def test_send_message_raises_when_not_active():
    proto, _ = _make_proto()
    # transport is None (not connected) → ConnectionError
    with pytest.raises(ConnectionError):
        proto.send_message(b"AQ001A\r")


def test_send_message_delegates_to_transport():
    proto, _ = _make_proto()
    transport = MagicMock()
    proto.transport = transport
    # Provide a mock _closed future so is_active() returns True
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        proto._closed = loop.create_future()
        proto.send_message(b"AQ001A\r")
        transport.write.assert_called_once_with(b"AQ001A\r")
    finally:
        loop.close()


@pytest.mark.parametrize(
    "cmd_bytes",
    [
        b"AA0011234\r",  # arm partition 1 with user code 1234
        b"AD0011234\r",  # disarm partition 1 with user code 1234
    ],
)
def test_send_message_redacts_user_code_in_dump(monkeypatch, caplog, cmd_bytes):
    """AA/AD payloads contain the user code; the dump must not log it."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "LOGGING_DUMP_PACKETS", True)

    proto, _ = _make_proto()
    transport = MagicMock()
    proto.transport = transport
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        proto._closed = loop.create_future()
        with caplog.at_level("DEBUG", logger="PAI.paradox.connections.prt3.protocol"):
            proto.send_message(cmd_bytes)

        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "1234" not in joined
        assert "31323334" not in joined  # hex(b"1234")
        assert "<redacted>" in joined
        transport.write.assert_called_once_with(cmd_bytes)
    finally:
        loop.close()


def test_send_message_does_not_redact_non_code_commands(monkeypatch, caplog):
    """Commands without user codes (AQ/PE/RA/...) dump in full as before."""
    from paradox.config import config as cfg

    monkeypatch.setattr(cfg, "LOGGING_DUMP_PACKETS", True)

    proto, _ = _make_proto()
    transport = MagicMock()
    proto.transport = transport
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        proto._closed = loop.create_future()
        with caplog.at_level("DEBUG", logger="PAI.paradox.connections.prt3.protocol"):
            proto.send_message(b"AQ001A\r")

        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "<redacted>" not in joined
    finally:
        loop.close()
