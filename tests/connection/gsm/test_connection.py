"""Tests for the GSM modem serial transport."""

import asyncio
from unittest import mock

import pytest

from paradox.connections.gsm.connection import GsmSerialConnection


@pytest.fixture
async def connected_gsm_connection():
    comm = GsmSerialConnection("test_port", 9600, 5)

    assert comm.queue.empty()

    async def mocked_create_serial_connection(loop, protocol_factory, *args, **kwargs):
        transport = mock.Mock()
        protocol = comm.make_protocol()
        asyncio.get_event_loop().call_soon(protocol.connection_made, transport)
        return (transport, protocol)

    with mock.patch("os.access", return_value=True), mock.patch(
        "serial_asyncio.create_serial_connection",
        new_callable=mock.AsyncMock,
        side_effect=mocked_create_serial_connection,
    ):
        result = await comm.connect()
        assert result

    assert comm.connected

    return comm


@pytest.mark.asyncio
async def test_connect_gives_up_when_the_port_open_hangs():
    """A hung create_serial_connection must not block connect() forever."""
    comm = GsmSerialConnection("test_port", 9600, 0.01)

    async def never_opens(*args, **kwargs):
        await asyncio.sleep(10)

    with mock.patch("os.access", return_value=True), mock.patch(
        "serial_asyncio.create_serial_connection",
        new_callable=mock.AsyncMock,
        side_effect=never_opens,
    ):
        assert await comm.connect() is False

    assert not comm.connected


@pytest.mark.asyncio
async def test_send_command_returns_the_next_modem_line(connected_gsm_connection):
    comm = connected_gsm_connection

    asyncio.get_event_loop().call_soon(comm.on_message, b"OK")
    assert await comm.send_command(b"AT") == b"OK"


@pytest.mark.asyncio
async def test_read_drains_the_queue(connected_gsm_connection):
    comm = connected_gsm_connection

    asyncio.get_event_loop().call_soon(comm.on_message, b"read_message")
    assert await comm.read() == b"read_message"
    assert comm.queue.empty()


@pytest.mark.asyncio
async def test_recv_callback_takes_precedence_over_the_queue(connected_gsm_connection):
    comm = connected_gsm_connection

    callback = mock.MagicMock()
    comm.set_recv_callback(callback)
    comm.on_message(b"+CMT: unsolicited")

    callback.assert_called_once_with(b"+CMT: unsolicited")
    assert comm.queue.empty()


@pytest.mark.asyncio
async def test_send_command_honours_its_timeout(connected_gsm_connection):
    """The timeout argument used to be accepted and then ignored.

    The old code hardcoded ``wait_for(..., timeout=5)``, so this raised too,
    just five seconds later. The elapsed check is what pins the fix.
    """
    comm = connected_gsm_connection

    loop = asyncio.get_event_loop()
    started = loop.time()
    with pytest.raises(asyncio.TimeoutError):
        await comm.send_command(b"AT", timeout=0.01)

    assert loop.time() - started < 1


@pytest.mark.asyncio
async def test_write_reaches_the_transport(connected_gsm_connection):
    """Connection.write() is inherited now that send_message is synchronous."""
    comm = connected_gsm_connection

    with mock.patch.object(comm._protocol, "transport") as transport:
        comm.write(b"AT")

    transport.write.assert_called_once_with(b"AT\r\n")


@pytest.mark.asyncio
async def test_connection_loss_after_connect_does_not_raise(connected_gsm_connection):
    """The connected_future is already resolved by then."""
    comm = connected_gsm_connection

    comm.on_connection_loss()

    assert not comm.connected


@pytest.mark.asyncio
async def test_connect_fails_when_the_port_is_not_accessible():
    comm = GsmSerialConnection("test_port", 9600, 5)

    with mock.patch("os.access", return_value=False):
        assert await comm.connect() is False


@pytest.mark.asyncio
async def test_connect_gives_up_after_the_open_timeout():
    comm = GsmSerialConnection("test_port", 9600, 0.01)

    async def never_connects(loop, protocol_factory, *args, **kwargs):
        return (mock.Mock(), comm.make_protocol())

    with mock.patch("os.access", return_value=True), mock.patch(
        "serial_asyncio.create_serial_connection",
        new_callable=mock.AsyncMock,
        side_effect=never_connects,
    ):
        assert await comm.connect() is False

    assert not comm.connected


@pytest.mark.asyncio
async def test_clear_replaces_the_queue(connected_gsm_connection):
    comm = connected_gsm_connection

    comm.on_message(b"stale")
    comm.clear()

    assert comm.queue.empty()


@pytest.mark.asyncio
async def test_a_declined_line_still_reaches_the_command_waiter(
    connected_gsm_connection,
):
    """Routing every line to the callback used to starve send_command forever."""
    comm = connected_gsm_connection
    comm.set_recv_callback(lambda message: message.startswith(b"+CMT"))

    comm.on_message(b"+CMT: unsolicited")
    comm.on_message(b"OK")

    assert await comm.read(timeout=0.1) == b"OK"
    assert comm.queue.empty()


@pytest.mark.asyncio
async def test_a_consumed_line_is_not_queued(connected_gsm_connection):
    comm = connected_gsm_connection
    consumed = []

    def callback(message):
        consumed.append(message)
        return True

    comm.set_recv_callback(callback)
    comm.on_message(b"+CUSD: 1")

    assert consumed == [b"+CUSD: 1"]
    assert comm.queue.empty()


@pytest.mark.asyncio
async def test_send_command_can_arm_the_sms_prompt(connected_gsm_connection):
    comm = connected_gsm_connection

    with mock.patch.object(comm._protocol, "expect_prompt") as expect_prompt:
        asyncio.get_event_loop().call_soon(comm.on_message, b"> ")
        assert await comm.send_command(b'AT+CMGS="+1"', expect_prompt=True) == b"> "

    expect_prompt.assert_called_once_with()


@pytest.mark.asyncio
async def test_write_raw_bypasses_the_line_terminator(connected_gsm_connection):
    comm = connected_gsm_connection

    with mock.patch.object(comm._protocol, "transport") as transport:
        comm.write_raw(b"body\x1a")

    transport.write.assert_called_once_with(b"body\x1a")


@pytest.mark.asyncio
async def test_write_raw_requires_a_connection():
    comm = GsmSerialConnection("test_port", 9600, 5)

    with pytest.raises(ConnectionError):
        comm.write_raw(b"body\x1a")


@pytest.mark.asyncio
async def test_a_stale_reply_does_not_satisfy_the_next_command(
    connected_gsm_connection,
):
    """The late answer to a timed-out command used to be handed to the next."""
    comm = connected_gsm_connection

    with mock.patch.object(comm._protocol, "transport"):
        with pytest.raises(asyncio.TimeoutError):
            await comm.send_command(b"AT+A", timeout=0.01)

        comm.on_message(b"late-reply-to-A")

        asyncio.get_event_loop().call_soon(comm.on_message, b"reply-to-B")
        assert await comm.send_command(b"AT+B", timeout=0.5) == b"reply-to-B"


@pytest.mark.asyncio
async def test_a_timed_out_command_disarms_the_prompt(connected_gsm_connection):
    """A stuck expectation would read the next unterminated line as a prompt."""
    comm = connected_gsm_connection

    with mock.patch.object(comm._protocol, "transport"):
        with pytest.raises(asyncio.TimeoutError):
            await comm.send_command(b'AT+CMGS="+1"', timeout=0.01, expect_prompt=True)

    assert comm._protocol._prompt_expected is False


@pytest.mark.asyncio
async def test_send_command_requires_a_connection():
    comm = GsmSerialConnection("test_port", 9600, 5)

    with pytest.raises(ConnectionError):
        await comm.send_command(b"AT")


@pytest.mark.asyncio
async def test_clear_keeps_a_waiter_attached(connected_gsm_connection):
    """Replacing the queue object stranded anyone already blocked in read()."""
    comm = connected_gsm_connection

    reader = asyncio.ensure_future(comm.read(timeout=0.5))
    await asyncio.sleep(0)

    comm.clear()
    comm.on_message(b"OK")

    assert await reader == b"OK"
