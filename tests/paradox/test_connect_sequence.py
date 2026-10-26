"""Byte-exact record of what ``Paradox.connect()``/``disconnect()`` transmit.

Real connection objects and ``SerialConnectionProtocol`` run over a scripted
transport that answers each request by its command byte, so the tests cover
everything between ``Paradox`` and the wire: message building, framing
switches after panel detection and the login of the detected panel family.
The IP150 case starts after the IP module login and checks the serial
payloads it carries.
"""

import asyncio
from typing import Dict, List, Optional, Union

from construct import Container
import pytest

from paradox.config import config as cfg
from paradox.connections.connection import Connection, Exchange
from paradox.connections.ip.connection import BareIPConnection, LocalIPConnection
from paradox.connections.serial.connection import SerialCommunication
from paradox.connections.serial.protocol import SerialConnectionProtocol
from paradox.hardware.mg6250 import Panel as MG6250Panel
from paradox.paradox import Paradox


def _with_checksum(body: bytes) -> bytes:
    return body + bytes([sum(body) % 256])


def identify_reply(product_id: int, label: bytes) -> bytes:
    """A 37 byte InitiateCommunication reply."""
    body = (
        bytes([0x72, 0xFF, 0x00, 0x01, 0x00, 0x00, 0x00, product_id, 0x01])
        + bytes([0x07, 0x86, 0x01])  # application version
        + bytes.fromhex("0a0b0c0d")  # serial number
        + bytes(10)  # hardware, bootloader, processor and encryption ids
        + bytes(2)
        + label
    )
    assert len(body) == 36
    return _with_checksum(body)


def start_reply(product_id: int) -> bytes:
    """A 37 byte StartCommunication reply."""
    body = bytearray(36)
    body[4] = product_id
    body[5:8] = bytes([0x07, 0x86, 0x01])
    body[8:10] = bytes.fromhex("1234")
    body[17:21] = bytes.fromhex("0a0b0c0d")
    return _with_checksum(bytes(body))


EVO192 = 5
SP6000 = 22
MG6250 = 100

EVO_REPLIES = {
    0x72: identify_reply(EVO192, b"EVO192  "),
    0x5F: start_reply(EVO192),
    0x00: _with_checksum(bytes.fromhex("1206000000")),
}

SP_REPLIES = {
    0x72: identify_reply(SP6000, b"SP6000  "),
    0x5F: start_reply(SP6000),
    0x00: _with_checksum(bytes([0x10]) + bytes(35)),
}

MG6250_REPLIES = {
    0x72: identify_reply(MG6250, b"MG6250  "),
}


class ScriptedTransport(asyncio.Transport):
    """Records every write and answers it from ``replies`` by command byte."""

    def __init__(self, protocol: asyncio.Protocol, replies: Dict[int, bytes]):
        super().__init__()
        self.protocol = protocol
        self.replies = replies
        self.tx: List[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.tx.append(bytes(data))
        reply = self.replies.get(data[0])
        if reply is not None:
            asyncio.get_running_loop().call_soon(self.protocol.data_received, reply)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            asyncio.get_running_loop().call_soon(self.protocol.connection_lost, None)

    def is_closing(self) -> bool:
        return self.closed


class ScriptedSerial(SerialCommunication):
    """``SerialCommunication`` whose port is a ``ScriptedTransport``."""

    def __init__(self, replies: Dict[int, bytes]):
        super().__init__(port="/nonexistent")
        self.replies = replies
        self.transport: Optional[ScriptedTransport] = None

    async def connect(self) -> bool:
        self.connected_future = asyncio.get_running_loop().create_future()
        protocol = self.make_protocol()
        self.transport = ScriptedTransport(protocol, self.replies)
        self._protocol = protocol
        protocol.connection_made(self.transport)
        return await self.connected_future


class ScriptedBareIP(BareIPConnection):
    """``BareIPConnection`` whose socket is a ``ScriptedTransport``."""

    def __init__(self, replies: Dict[int, bytes]):
        super().__init__()
        self.replies = replies
        self.transport: Optional[ScriptedTransport] = None

    async def _try_connect(self) -> None:
        protocol = self._make_protocol()
        self.transport = ScriptedTransport(protocol, self.replies)
        self._protocol = protocol
        protocol.connection_made(self.transport)
        self.connected = True


class ScriptedIP150(LocalIPConnection):
    """``LocalIPConnection`` past the IP150 login, carrying serial payloads."""

    def __init__(self, replies: Dict[int, bytes]):
        super().__init__(host="127.0.0.1", port=10000, password="paradox")
        self.replies = replies
        self.transport: Optional[ScriptedTransport] = None

    async def _try_connect(self) -> None:
        protocol = SerialConnectionProtocol(self)
        self.transport = ScriptedTransport(protocol, self.replies)
        self._protocol = protocol
        protocol.connection_made(self.transport)
        self.connected = True


def make_alarm(connection: Connection) -> Paradox:
    alarm = Paradox()
    alarm._connection = connection
    alarm._register_connection_handlers()
    return alarm


Scripted = Union[ScriptedSerial, ScriptedBareIP, ScriptedIP150]


async def run_session(connection: Scripted) -> List[str]:
    alarm = make_alarm(connection)
    assert await alarm.connect()
    await alarm.disconnect()
    assert connection.transport is not None
    return [m.hex() for m in connection.transport.tx]


@pytest.fixture(autouse=True)
def plain_serial(monkeypatch):
    monkeypatch.setattr(cfg, "CONNECTION_TYPE", "Serial")
    monkeypatch.setattr(cfg, "SERIAL_ENCRYPTED", False)
    monkeypatch.setattr(cfg, "PASSWORD", "1234")


INITIATE = "72" + "00" * 35 + "72"
START = "5f20" + "00" * 31 + "020000" + "81"

EVO_TX = [
    INITIATE,
    START,
    "00000000050786011234123400000000000a0b0c0d0000000000000000000000000000004d",
    "70040579",
]

SP_TX = [
    INITIATE,
    START,
    "0000000016078601123412341900000000000000000000000000000000000000000200004b",
    "70000000000000000000000000000000000000000000000000000000000000000501000076",
]


@pytest.mark.asyncio
async def test_evo_serial_bytes():
    connection = ScriptedSerial(EVO_REPLIES)
    assert await run_session(connection) == EVO_TX


@pytest.mark.asyncio
async def test_spectra_serial_bytes():
    connection = ScriptedSerial(SP_REPLIES)
    assert await run_session(connection) == SP_TX


@pytest.mark.asyncio
async def test_evo_bare_ip_bytes(monkeypatch):
    monkeypatch.setattr(cfg, "CONNECTION_TYPE", "IP")
    connection = ScriptedBareIP(EVO_REPLIES)
    assert await run_session(connection) == EVO_TX


@pytest.mark.asyncio
async def test_evo_ip150_payloads(monkeypatch):
    monkeypatch.setattr(cfg, "CONNECTION_TYPE", "IP")
    connection = ScriptedIP150(EVO_REPLIES)
    assert await run_session(connection) == EVO_TX


@pytest.mark.asyncio
async def test_mg6250_serial_skips_start_communication(mocker):
    mocker.patch.object(
        MG6250Panel, "initialize_communication", mocker.AsyncMock(return_value=True)
    )
    connection = ScriptedSerial(MG6250_REPLIES)
    tx = await run_session(connection)
    assert tx == [
        INITIATE,
        "70250000000000000000000000000000000000000000000000000000000000000000000095",
    ]


@pytest.mark.asyncio
async def test_start_communication_source_id_comes_from_connection():
    class SourceZero(ScriptedSerial):
        start_communication_source_id = 0x0

    connection = SourceZero(EVO_REPLIES)
    tx = await run_session(connection)

    assert tx[1] == "5f20" + "00" * 31 + "000000" + "7f"
    assert tx[2:] == EVO_TX[2:]


async def _request_without_reply(connection: ScriptedSerial) -> List[str]:
    alarm = make_alarm(connection)
    assert await alarm.connect()
    assert connection.transport is not None
    connection.transport.tx.clear()

    with pytest.raises(asyncio.TimeoutError):
        await alarm.send_wait(
            message=bytes.fromhex("5000"), reply_expected=0x5, timeout=0.001
        )
    return [m.hex() for m in connection.transport.tx]


@pytest.mark.asyncio
async def test_send_wait_retransmits_by_default():
    assert await _request_without_reply(ScriptedSerial(EVO_REPLIES)) == ["5000"] * 5


@pytest.mark.asyncio
async def test_send_wait_does_not_retransmit_when_connection_forbids_it():
    class NoRetransmit(ScriptedSerial):
        retransmit_requests = False

    assert await _request_without_reply(NoRetransmit(EVO_REPLIES)) == ["5000"]


class HookedSerial(ScriptedSerial):
    """Records the connection hooks ``Paradox`` calls."""

    def __init__(self, replies: Dict[int, bytes]):
        super().__init__(replies)
        self.initiate_replies: List[Container] = []
        self.echoes: List[Optional[Container]] = []

    def sent(self) -> List[str]:
        assert self.transport is not None
        return [m.hex() for m in self.transport.tx]

    async def on_initiate_communication(
        self, reply: Container, exchange: Exchange
    ) -> None:
        self.initiate_replies.append(reply)
        assert self.sent() == [INITIATE]
        raw = reply.fields.data + reply.checksum
        self.echoes.append(
            await exchange(raw, lambda m: m.fields.value.po.command == 0x7)
        )


@pytest.mark.asyncio
async def test_initiate_hook_runs_once_before_start_communication():
    connection = HookedSerial(EVO_REPLIES)
    alarm = make_alarm(connection)

    assert await alarm.connect()

    assert len(connection.initiate_replies) == 1
    reply = connection.initiate_replies[0]
    assert reply.fields.data + reply.checksum == EVO_REPLIES[0x72]
    echo = connection.echoes[0]
    assert echo is not None and echo.fields.data == reply.fields.data
    assert connection.sent()[:3] == [INITIATE, EVO_REPLIES[0x72].hex(), START]


@pytest.mark.asyncio
async def test_initiate_hook_can_abort_connect():
    class Refusing(ScriptedSerial):
        async def on_initiate_communication(
            self, reply: Container, exchange: Exchange
        ) -> None:
            raise ConnectionError("refused")

    connection = Refusing(EVO_REPLIES)
    alarm = make_alarm(connection)

    assert not await alarm.connect()
    assert connection.transport is not None
    assert [m.hex() for m in connection.transport.tx] == [INITIATE]


@pytest.mark.asyncio
async def test_end_session_runs_once_between_close_message_and_transport_close():
    seen: List[List[str]] = []

    class Ending(ScriptedSerial):
        async def end_session(self) -> None:
            assert self.transport is not None and not self.transport.closed
            seen.append([m.hex() for m in self.transport.tx])

    connection = Ending(EVO_REPLIES)
    alarm = make_alarm(connection)
    assert await alarm.connect()

    await alarm.disconnect()
    await alarm.disconnect()

    assert seen == [EVO_TX]
    assert connection.transport is not None and connection.transport.closed


@pytest.mark.asyncio
async def test_transport_closes_when_end_session_fails():
    class Failing(ScriptedSerial):
        async def end_session(self) -> None:
            raise RuntimeError("no ack")

    connection = Failing(EVO_REPLIES)
    alarm = make_alarm(connection)
    assert await alarm.connect()

    await alarm.disconnect()

    assert connection.transport is not None and connection.transport.closed
    assert not connection.connected


@pytest.mark.asyncio
async def test_transport_closes_when_disconnect_is_cancelled():
    entered = asyncio.Event()

    class Waiting(ScriptedSerial):
        async def end_session(self) -> None:
            entered.set()
            await asyncio.sleep(3600)

    connection = Waiting(EVO_REPLIES)
    alarm = make_alarm(connection)
    assert await alarm.connect()

    task = asyncio.ensure_future(alarm.disconnect())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert connection.transport is not None and connection.transport.closed


@pytest.mark.asyncio
async def test_initiate_hook_exchange_follows_retransmit_requests():
    class StrictEcho(ScriptedSerial):
        retransmit_requests = False

        async def on_initiate_communication(
            self, reply: Container, exchange: Exchange
        ) -> None:
            await exchange(reply.fields.data + reply.checksum, lambda m: False)

    connection = StrictEcho(EVO_REPLIES)
    alarm = make_alarm(connection)

    assert not await alarm.connect()
    assert connection.transport is not None
    assert [m.hex() for m in connection.transport.tx] == [
        INITIATE,
        EVO_REPLIES[0x72].hex(),
    ]
