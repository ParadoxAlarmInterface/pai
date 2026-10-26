"""``E0FESerialConnectionProtocol`` against a recording transport.

Vectors come from ``e0fe_vectors`` (synthetic, generated independently).
"""

import asyncio
from typing import List
from unittest.mock import MagicMock

import pytest

from paradox.connections.serial.e0fe_protocol import E0FESerialConnectionProtocol

from tests.connection.serial import e0fe_vectors as v


class RecordingTransport(asyncio.Transport):
    def __init__(self) -> None:
        super().__init__()
        self.tx: List[bytes] = []
        self.closed = False
        self.fail = False

    def write(self, data: bytes) -> None:
        if self.fail:
            raise OSError("write failed")
        self.tx.append(bytes(data))

    def close(self) -> None:
        self.closed = True

    def is_closing(self) -> bool:
        return self.closed


@pytest.fixture
async def link():
    handler = MagicMock()
    protocol = E0FESerialConnectionProtocol(handler)
    transport = RecordingTransport()
    protocol.connection_made(transport)
    return protocol, transport, handler


def received(handler: MagicMock) -> List[bytes]:
    return [c.args[0] for c in handler.on_message.call_args_list]


async def test_plain_until_wrapping_starts(link):
    protocol, transport, handler = link

    protocol.send_message(v.INITIATE)
    protocol.data_received(v.RX_EVENT_A + v.IDENTIFY)
    protocol.start_wrapping()
    protocol.send_message(v.ECHO)

    assert transport.tx == [v.INITIATE, v.TX_ECHO]
    assert received(handler) == [v.IDENTIFY]


async def test_every_valid_frame_sets_the_state(link):
    protocol, transport, handler = link
    protocol.start_wrapping()

    protocol.data_received(v.RX_EVENT_ELSEWHERE)
    protocol.send_message(v.READ_RAM16)

    assert received(handler) == [v.EVENT_A]
    assert transport.tx == [v.TX_READ_RAM16_ELSEWHERE]


async def test_one_request_at_a_time(link):
    protocol, transport, handler = link
    protocol.start_wrapping()
    protocol.data_received(v.RX_START_REPLY)
    protocol.data_received(v.RX_LOGIN_OK)
    protocol.send_message(v.READ_RAM16)

    with pytest.raises(ConnectionError):
        protocol.send_message(v.CLOSE)
    assert protocol.awaiting_reply_to(v.READ_RAM16)
    protocol.data_received(v.RX_EVENT_B)
    assert protocol.awaiting_reply_to(v.READ_RAM16)
    protocol.data_received(v.RX_RAM16)
    assert not protocol.awaiting_reply_to(v.READ_RAM16)
    protocol.send_message(v.CLOSE)

    assert transport.tx == [v.TX_READ_RAM16, v.TX_CLOSE]
    assert protocol.awaiting_reply_to(v.CLOSE)
    assert protocol.is_active()


async def test_bad_frame_invalidates(link):
    protocol, transport, handler = link
    protocol.start_wrapping()

    protocol.data_received(v.RX_BAD_INNER_CHECKSUM + v.RX_EVENT_B)

    assert received(handler) == []
    assert not protocol.is_active()
    assert transport.closed
    with pytest.raises(ConnectionError):
        protocol.send_message(v.READ_RAM16)
    protocol.data_received(v.RX_EVENT_B)
    assert received(handler) == []
    assert transport.tx == []


async def test_failed_write_invalidates(link):
    protocol, transport, handler = link
    protocol.start_wrapping()
    transport.fail = True

    with pytest.raises(ConnectionError):
        protocol.send_message(v.READ_RAM16)

    transport.fail = False
    assert not protocol.is_active()
    with pytest.raises(ConnectionError):
        protocol.send_message(v.READ_RAM16)
    assert transport.tx == []


async def test_invalid_message_is_not_sent(link):
    protocol, transport, handler = link
    protocol.start_wrapping()

    with pytest.raises(ValueError):
        protocol.send_message(b"\x50\x00")

    assert transport.tx == []
    protocol.data_received(v.RX_START_REPLY)
    protocol.data_received(v.RX_LOGIN_OK)
    protocol.send_message(v.READ_RAM16)
    assert transport.tx == [v.TX_READ_RAM16]
