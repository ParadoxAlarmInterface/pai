"""``Paradox`` sessions over a link in ``E0 FE`` mode.

The real connection, protocol, codec and EVO panel run over a transport that
plays a script: each expected transmission is answered with panel frames.
Every vector comes from ``e0fe_vectors`` (synthetic, generated independently).
"""

import asyncio
import logging
import os
from typing import List, Sequence, Tuple

import pytest

from paradox.config import config as cfg
from paradox.connections.connection import Connection
from paradox.connections.ip.connection import E0FEBareIPConnection
from paradox.connections.serial import connection as serial_connection, e0fe_connection
from paradox.connections.serial.connection import E0FESerialCommunication
from paradox.connections.serial.e0fe_protocol import E0FESerialConnectionProtocol
from paradox.exceptions import AuthenticationFailed, PAICriticalException
from paradox.hardware.evo.panel import Panel_EVOBase
from paradox.lib.handlers import PersistentHandler
from paradox.paradox import Paradox, RunState

from tests.connection.serial import e0fe_vectors as v

Step = Tuple[bytes, Sequence[bytes]]

HANDSHAKE: List[Step] = [
    (v.INITIATE, [v.IDENTIFY]),
    (v.TX_ECHO, [v.RX_EVENT_A, v.RX_ANSWER]),
    (v.TX_START, [v.RX_START_REPLY]),
    (v.TX_LOGIN, [v.RX_LOGIN_OK]),
]
STATUS: Step = (v.TX_READ_RAM16, [v.RX_EVENT_B, v.RX_RAM16])
CLOSE: Step = (v.TX_CLOSE, [v.RX_CLOSE_ACK])


class ScriptedTransport(asyncio.Transport):
    """Answers each expected write with its panel frames, byte by byte."""

    def __init__(self, protocol: asyncio.Protocol, script: Sequence[Step]):
        super().__init__()
        self.protocol = protocol
        self.script = list(script)
        self.tx: List[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.tx.append(bytes(data))
        if not self.script:
            return
        expected, replies = self.script.pop(0)
        if data != expected:
            self.script.clear()
            return
        loop = asyncio.get_running_loop()
        for reply in replies:
            for i in range(len(reply)):
                loop.call_soon(self._receive, reply[i : i + 1])

    def _receive(self, data: bytes) -> None:
        if not self.closed:
            self.protocol.data_received(data)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            asyncio.get_running_loop().call_soon(self.protocol.connection_lost, None)

    def is_closing(self) -> bool:
        return self.closed


class ScriptedMixin:
    """Each ``connect()`` gets the next script and a new protocol."""

    _protocol: E0FESerialConnectionProtocol
    scripts: List[Sequence[Step]]
    transports: List[ScriptedTransport]

    @property
    def transport(self) -> ScriptedTransport:
        return self.transports[-1]

    @property
    def protocol(self) -> E0FESerialConnectionProtocol:
        return self._protocol

    def _open(self, protocol: E0FESerialConnectionProtocol) -> None:
        transport = ScriptedTransport(protocol, self.scripts.pop(0))
        self.transports.append(transport)
        self._protocol = protocol
        protocol.connection_made(transport)


class ScriptedSerial(ScriptedMixin, E0FESerialCommunication):
    def __init__(self, *scripts: Sequence[Step]) -> None:
        super().__init__(port=os.devnull)
        self.scripts = list(scripts)
        self.transports = []


async def create_scripted_serial_connection(loop, protocol_factory, port, baud):
    connection = protocol_factory.__self__
    protocol = protocol_factory()
    connection._open(protocol)
    return connection.transport, protocol


class ScriptedBareIP(ScriptedMixin, E0FEBareIPConnection):
    def __init__(self, *scripts: Sequence[Step]) -> None:
        super().__init__()
        self.scripts = list(scripts)
        self.transports = []

    async def _try_connect(self) -> None:
        self._open(self._make_protocol())
        self.connected = True


@pytest.fixture(autouse=True)
def e0fe_serial(monkeypatch):
    monkeypatch.setattr(
        serial_connection.serial_asyncio,
        "create_serial_connection",
        create_scripted_serial_connection,
    )
    monkeypatch.setattr(cfg, "CONNECTION_TYPE", "Serial")
    monkeypatch.setattr(cfg, "PASSWORD", v.PASSWORD)
    monkeypatch.setattr(cfg, "KEEP_ALIVE_INTERVAL", 0)


def make_alarm(connection: Connection) -> Tuple[Paradox, List[bytes]]:
    """A ``Paradox`` on ``connection`` and the list of raw messages it sees."""
    alarm = Paradox()
    alarm._connection = connection
    alarm._register_connection_handlers()
    received: List[bytes] = []
    connection.register_raw_handler(PersistentHandler(received.append))
    return alarm, received


async def read_ram16(alarm: Paradox):
    return await alarm.send_wait(
        message=v.READ_RAM16,
        reply_expected=lambda m: Panel_EVOBase._request_status_reply_check(m, 16),
    )


def sent(connection: ScriptedMixin, index: int = -1) -> List[bytes]:
    return connection.transports[index].tx


@pytest.mark.parametrize(
    "connection_type, make",
    [("Serial", ScriptedSerial), ("IP", ScriptedBareIP)],
)
async def test_session_bytes(monkeypatch, connection_type, make):
    monkeypatch.setattr(cfg, "CONNECTION_TYPE", connection_type)
    connection = make(HANDSHAKE + [STATUS, CLOSE])
    alarm, received = make_alarm(connection)

    assert await alarm.connect()
    reply = await read_ram16(alarm)
    await asyncio.wait_for(alarm.disconnect(), e0fe_connection.CLOSE_ACK_TIMEOUT / 4)

    assert reply is not None and reply.fields.data + reply.checksum == v.RAM16
    assert sent(connection) == [step[0] for step in HANDSHAKE + [STATUS, CLOSE]]
    assert received == [
        v.IDENTIFY,
        v.EVENT_A,
        v.ANSWER,
        v.START_REPLY,
        v.LOGIN_OK,
        v.EVENT_B,
        v.RAM16,
        v.CLOSE_ACK,
    ]
    assert connection.transport.closed


async def test_login_copies_the_start_communication_reply():
    connection = ScriptedSerial(HANDSHAKE)
    alarm, _ = make_alarm(connection)

    assert await alarm.connect()

    login = alarm.panel.get_message("InitializeCommunication").build(
        dict(fields=dict(value=alarm.panel.settings))
    )
    assert login == v.LOGIN


async def test_untested_firmware_is_a_warning(caplog):
    connection = ScriptedSerial([(v.INITIATE, [v.IDENTIFY_OTHER_FIRMWARE])])
    alarm, _ = make_alarm(connection)

    with caplog.at_level(logging.WARNING):
        assert not await alarm.connect()

    assert "7.90.002" in caplog.text
    assert sent(connection) == [v.INITIATE, v.TX_ECHO_OTHER_FIRMWARE]


@pytest.mark.parametrize(
    "mode",
    [0x00, 0xBA, 0xA1],
)
async def test_panel_not_in_e0fe_mode_is_critical(mode):
    identify = bytearray(v.IDENTIFY[:36])
    identify[35] = mode
    identify.append(sum(identify) & 0xFF)
    connection = ScriptedSerial([(v.INITIATE, [bytes(identify)])])
    alarm, _ = make_alarm(connection)

    with pytest.raises(PAICriticalException, match="E0 FE serial mode"):
        await alarm.connect()

    assert sent(connection) == [v.INITIATE]


@pytest.mark.parametrize(
    "answers",
    [
        [v.RX_EVENT_A],
        [v.IDENTIFY],
        [v.RX_ANSWER_WRONG],
    ],
    ids=["event", "plain_identify", "wrong_answer"],
)
async def test_echo_needs_the_matching_answer(answers):
    connection = ScriptedSerial([(v.INITIATE, [v.IDENTIFY]), (v.TX_ECHO, answers)])
    alarm, _ = make_alarm(connection)

    assert not await alarm.connect()

    assert sent(connection) == [v.INITIATE, v.TX_ECHO]
    assert not connection.connected
    assert connection.transport.closed


async def test_wrong_password_is_critical_and_closes_the_session():
    connection = ScriptedSerial(
        HANDSHAKE[:-1]
        + [(v.TX_LOGIN, [v.RX_LOGIN_REFUSED]), (v.TX_CLOSE_AFTER_REFUSAL, [])]
    )
    alarm, _ = make_alarm(connection)

    with pytest.raises(AuthenticationFailed):
        await alarm.connect()
    await alarm.disconnect()

    assert sent(connection) == [step[0] for step in HANDSHAKE] + [
        v.TX_CLOSE_AFTER_REFUSAL
    ]


async def test_timeout_ends_the_session_and_reconnect_starts_fresh():
    connection = ScriptedSerial(
        HANDSHAKE + [(v.TX_READ_RAM16, [v.RX_EVENT_B])],
        HANDSHAKE + [STATUS, CLOSE],
    )
    alarm, _ = make_alarm(connection)
    assert await alarm.connect()

    with pytest.raises(ConnectionError, match="no reply"):
        await read_ram16(alarm)

    assert not connection.connected
    with pytest.raises(ConnectionError):
        await read_ram16(alarm)
    with pytest.raises(ConnectionError):
        connection.protocol.send_message(v.READ_RAM16)
    assert sent(connection, 0) == [step[0] for step in HANDSHAKE] + [v.TX_READ_RAM16]
    assert connection.transports[0].closed

    first_protocol = connection.protocol
    assert await alarm.connect()
    assert connection.protocol is not first_protocol
    assert await read_ram16(alarm) is not None
    await alarm.disconnect()

    assert sent(connection, 0) == [step[0] for step in HANDSHAKE] + [v.TX_READ_RAM16]
    assert sent(connection, 1) == [step[0] for step in HANDSHAKE + [STATUS, CLOSE]]


async def test_late_timeout_spares_the_next_session():
    connection = ScriptedSerial(
        HANDSHAKE + [(v.TX_READ_RAM16, [])],
        HANDSHAKE + [STATUS, CLOSE],
    )
    alarm, _ = make_alarm(connection)
    assert await alarm.connect()
    request = asyncio.ensure_future(read_ram16(alarm))
    await asyncio.sleep(0)

    connection.protocol.connection_lost(ConnectionResetError())
    assert await alarm.connect()
    with pytest.raises(ConnectionError):
        await request

    assert connection.connected
    assert await read_ram16(alarm) is not None
    await alarm.disconnect()
    assert sent(connection, 1) == [step[0] for step in HANDSHAKE + [STATUS, CLOSE]]


async def test_reconnect_after_transport_error():
    connection = ScriptedSerial(HANDSHAKE, HANDSHAKE + [STATUS, CLOSE])
    alarm, _ = make_alarm(connection)
    assert await alarm.connect()

    connection.protocol.connection_lost(ConnectionResetError())
    assert not connection.connected

    assert await alarm.connect()
    assert await read_ram16(alarm) is not None
    await alarm.disconnect()
    assert sent(connection, 1) == [step[0] for step in HANDSHAKE + [STATUS, CLOSE]]


async def test_bad_frame_ends_the_session():
    connection = ScriptedSerial(
        HANDSHAKE + [(v.TX_READ_RAM16, [v.RX_BAD_INNER_CHECKSUM, v.RX_RAM16])]
    )
    alarm, received = make_alarm(connection)
    assert await alarm.connect()
    received.clear()

    with pytest.raises(ConnectionError):
        await read_ram16(alarm)

    assert received == []
    assert not connection.connected
    assert connection.transport.closed
    await alarm.disconnect()
    assert sent(connection) == [step[0] for step in HANDSHAKE] + [v.TX_READ_RAM16]


async def test_loop_hands_a_lost_session_to_reconnect(monkeypatch, mocker):
    monkeypatch.setattr(cfg, "KEEP_ALIVE_INTERVAL", 10)
    connection = ScriptedSerial(HANDSHAKE + [(v.TX_READ_RAM16, [v.RX_EVENT_B])])
    alarm, _ = make_alarm(connection)
    assert await alarm.connect()
    mocker.patch.object(
        alarm.panel,
        "get_status_requests",
        lambda: [alarm.panel.request_status(16), alarm.panel.request_status(17)],
    )
    alarm.run_state = RunState.RUN

    with pytest.raises(ConnectionError):
        await asyncio.wait_for(alarm.loop(), 4 * cfg.IO_TIMEOUT)

    assert sent(connection) == [step[0] for step in HANDSHAKE] + [v.TX_READ_RAM16]


async def test_close_without_acknowledgement_is_bounded(monkeypatch, caplog):
    monkeypatch.setattr(e0fe_connection, "CLOSE_ACK_TIMEOUT", 0.05)
    connection = ScriptedSerial(HANDSHAKE + [STATUS, (v.TX_CLOSE, [])])
    alarm, _ = make_alarm(connection)
    assert await alarm.connect()
    assert await read_ram16(alarm) is not None

    with caplog.at_level(logging.WARNING):
        await asyncio.wait_for(alarm.disconnect(), 1)

    assert "did not acknowledge" in caplog.text
    assert sent(connection)[-1] == v.TX_CLOSE
    assert connection.transport.closed


async def test_end_session_twice():
    connection = ScriptedSerial(HANDSHAKE + [STATUS, CLOSE])
    alarm, received = make_alarm(connection)
    assert await alarm.connect()
    assert await read_ram16(alarm) is not None

    alarm._clean_session()
    await asyncio.wait_for(connection.end_session(), 1)
    await asyncio.wait_for(connection.end_session(), 0.01)
    await connection.close()
    await connection.end_session()
    await alarm.disconnect()

    assert received[-1] == v.CLOSE_ACK
    assert sent(connection) == [step[0] for step in HANDSHAKE + [STATUS, CLOSE]]
    assert connection.transport.closed


async def test_no_close_while_a_request_is_unanswered():
    connection = ScriptedSerial(HANDSHAKE + [(v.TX_READ_RAM16, [])])
    alarm, _ = make_alarm(connection)
    assert await alarm.connect()

    request = asyncio.ensure_future(read_ram16(alarm))
    await asyncio.sleep(0)
    await asyncio.wait_for(alarm.disconnect(), 0.5)

    assert sent(connection) == [step[0] for step in HANDSHAKE] + [v.TX_READ_RAM16]
    assert connection.transport.closed
    with pytest.raises(ConnectionError):
        await request


async def test_no_close_on_an_invalid_session():
    connection = ScriptedSerial(
        HANDSHAKE + [(v.TX_READ_RAM16, [v.RX_BAD_INNER_CHECKSUM])]
    )
    alarm, _ = make_alarm(connection)
    assert await alarm.connect()
    request = asyncio.ensure_future(read_ram16(alarm))
    for _ in range(100):
        await asyncio.sleep(0)

    await asyncio.wait_for(alarm.disconnect(), 0.5)

    assert sent(connection)[-1] == v.TX_READ_RAM16
    with pytest.raises(ConnectionError):
        await request
