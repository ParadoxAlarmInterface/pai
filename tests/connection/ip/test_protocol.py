"""Tests for the IP150 protocol glue.

Framing itself is covered in test_framing.py; these cover dispatch.
"""

import binascii

import pytest

from paradox.connections.handler import IPConnectionHandler
from paradox.connections.ip.parsers import (
    IPMessageCommand,
    IPMessageRequest,
    IPMessageType,
)
from paradox.connections.ip.protocol import IPConnectionProtocol

PASSWORD = b"paradox"


@pytest.fixture
def handler(mocker):
    return mocker.MagicMock(spec=IPConnectionHandler)


@pytest.fixture
async def protocol(handler, mocker):
    p = IPConnectionProtocol(handler, PASSWORD)
    p.connection_made(mocker.MagicMock())
    return p


def build(payload, message_type, command=IPMessageCommand.passthrough):
    return IPMessageRequest.build(
        dict(
            header=dict(
                length=len(payload),
                message_type=message_type,
                flags=dict(installer_mode=True),
                command=command,
                wt=100,
                cryptor_code="aes_256_ecb",
            ),
            payload=payload,
        ),
        password=PASSWORD,
    )


async def test_passthrough_response_reaches_on_message(protocol, handler):
    payload = b"\x52\x0a\x00" + b"\x00" * 33 + b"\x8c"
    protocol.data_received(build(payload, IPMessageType.serial_passthrough_response))
    handler.on_message.assert_called_once_with(payload)


async def test_ip_response_reaches_on_ip_message(protocol, handler):
    protocol.data_received(build(b"\x01\x02", IPMessageType.ip_response))
    handler.on_ip_message.assert_called_once()
    handler.on_message.assert_not_called()


async def test_pipelined_messages_are_both_dispatched(protocol, handler):
    a = b"\x52" + b"\x00" * 35 + b"\x52"
    b = b"\x53" + b"\x00" * 35 + b"\x53"
    raw = build(a, IPMessageType.serial_passthrough_response) + build(
        b, IPMessageType.serial_passthrough_response
    )
    protocol.data_received(raw)
    assert [c[0][0] for c in handler.on_message.call_args_list] == [a, b]


async def test_message_split_across_callbacks_is_dispatched(protocol, handler):
    payload = b"\x52" + b"\x00" * 35 + b"\x52"
    raw = build(payload, IPMessageType.serial_passthrough_response)
    protocol.data_received(raw[:10])
    handler.on_message.assert_not_called()
    protocol.data_received(raw[10:])
    handler.on_message.assert_called_once_with(payload)


async def test_empty_data_is_ignored(protocol, handler):
    protocol.data_received(b"")
    handler.on_message.assert_not_called()


async def test_garbage_is_dropped_without_dispatch(protocol, handler):
    protocol.data_received(b"\xbb" * 40)
    handler.on_message.assert_not_called()
    assert protocol.buffer == b""


async def test_send_message_writes_a_framed_request(protocol):
    payload = b"\x52" + b"\x00" * 35 + b"\x52"
    protocol.send_message(payload)
    written = protocol.transport.write.call_args[0][0]
    assert written[0] == 0xAA
    assert written[1] | (written[2] << 8) == len(payload)


async def test_send_raw_writes_verbatim(protocol):
    protocol.send_raw(b"\xaa\xbb")
    protocol.transport.write.assert_called_once_with(b"\xaa\xbb")


async def test_send_message_after_close_raises(protocol):
    protocol.connection_lost(None)
    with pytest.raises(ConnectionError):
        protocol.send_message(b"\x00" * 37)


async def test_unknown_message_type_is_logged(protocol, handler, caplog):
    protocol.data_received(build(b"\x01", IPMessageType.ip_request))
    handler.on_message.assert_not_called()
    handler.on_ip_message.assert_not_called()
    assert [r for r in caplog.records if r.levelname == "ERROR"]


async def test_raw_dump_logging_does_not_raise(protocol, mocker):
    from paradox.config import config as cfg

    mocker.patch.object(cfg, "LOGGING_DUMP_PACKETS", True)
    payload = b"\x52" + b"\x00" * 35 + b"\x52"
    protocol.data_received(build(payload, IPMessageType.serial_passthrough_response))
    assert binascii.hexlify(payload)
