import asyncio
from unittest import mock

import pytest

from paradox.config import config as cfg
from paradox.connections.gsm.connection import GsmSerialConnection
from paradox.event import EventLevel
from paradox.interfaces.text.gsm import GSMTextInterface


@pytest.fixture
async def connected_gsm_connection():
    comm = GsmSerialConnection("test_port", 9600, 5)

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
        assert await comm.connect()

    return comm


# Test GSMTextInterface class
@pytest.mark.asyncio
async def test_gsm_text_interface(connected_gsm_connection):
    alarm = mock.MagicMock()
    event = asyncio.Event()

    async def control_partition(partition, command):
        assert partition == "outside"
        assert command == "arm"
        event.set()

        return True

    interface = GSMTextInterface(alarm)
    interface.port = connected_gsm_connection
    interface.modem_connected = True

    data = b"+CMT: test_data"
    interface.data_received(data)
    assert interface.message_cmt == data.decode()

    # level = EventLevel.INFO
    # await interface.send_message("bla", level)

    header = '+CMT: "+1234567890","","24/09/17,10:30:00+32"'
    text = "partition outside arm"
    alarm.control_partition.side_effect = control_partition
    interface.process_cmt(header, text)
    await asyncio.wait_for(event.wait(), timeout=0.1)


@pytest.mark.asyncio
async def test_gsm_text_interface_discards_undecodable_line():
    interface = GSMTextInterface(mock.MagicMock())

    assert interface.data_received(b"\xff\xfe")
    assert interface.message_cmt is None


@pytest.mark.asyncio
async def test_gsm_text_interface_does_not_keep_a_malformed_cmt_header():
    """A header left in place would eat every following line as its body."""
    interface = GSMTextInterface(mock.MagicMock())

    interface.data_received(b"+CMT: not-json")
    assert interface.message_cmt == "+CMT: not-json"

    assert interface.data_received(b"body")
    assert interface.message_cmt is None


@pytest.mark.asyncio
async def test_gsm_text_interface_survives_a_malformed_cusd():
    interface = GSMTextInterface(mock.MagicMock())

    assert interface.data_received(b"+CUSD: not-json")


@pytest.mark.asyncio
async def test_gsm_text_interface_stop_closes_the_port(connected_gsm_connection):
    """stop() used to be a no-op, leaking the serial port for the process."""
    interface = GSMTextInterface(mock.MagicMock())
    interface.port = connected_gsm_connection
    interface.modem_connected = True

    with mock.patch.object(
        connected_gsm_connection, "close", new_callable=mock.AsyncMock
    ) as close:
        interface.stop()
        await asyncio.sleep(0)

    close.assert_awaited_once()
    assert interface.port is None
    assert not interface.modem_connected


@pytest.fixture
async def gsm_interface(connected_gsm_connection):
    interface = GSMTextInterface(mock.MagicMock())
    interface.port = connected_gsm_connection
    interface.modem_connected = True
    connected_gsm_connection.set_recv_callback(interface.data_received)
    return interface


async def settle(iterations=6):
    """Give scheduled tasks room to run without depending on wall-clock time."""
    for _ in range(iterations):
        await asyncio.sleep(0)


def modem_says(comm, *lines):
    """Feed modem output through the real protocol, as the serial port would."""
    for line in lines:
        comm._protocol.data_received(line)


@pytest.mark.asyncio
async def test_data_received_declines_command_replies():
    """Lines the interface does not consume must reach the command waiter."""
    interface = GSMTextInterface(mock.MagicMock())

    assert interface.data_received(b"OK") is False
    assert interface.data_received(b"+CMGS: 42") is False
    assert interface.data_received(b"ERROR") is False


@pytest.mark.asyncio
async def test_data_received_consumes_unsolicited_results():
    interface = GSMTextInterface(mock.MagicMock())

    assert interface.data_received(b"+CUSD: 1") is True
    assert interface.data_received(b'+CMT: "+1","","24/09/17,10:30:00+32"') is True
    assert interface.data_received(b"body") is True


@pytest.mark.asyncio
async def test_send_message_is_synchronous(gsm_interface):
    """An async override left every notification as a dropped coroutine."""
    assert not asyncio.iscoroutinefunction(gsm_interface.send_message)


@pytest.mark.asyncio
async def test_send_message_schedules_a_send_to_every_contact(gsm_interface):
    with mock.patch.object(cfg, "GSM_CONTACTS", ["+1", "+2"]), mock.patch.object(
        gsm_interface, "_send_sms", new_callable=mock.AsyncMock
    ) as send_sms:
        gsm_interface.send_message("Alarm!", EventLevel.INFO)
        await settle()

    assert [c.args for c in send_sms.await_args_list] == [
        ("+1", "Alarm!"),
        ("+2", "Alarm!"),
    ]


@pytest.mark.asyncio
async def test_send_message_is_a_no_op_while_disconnected(gsm_interface):
    gsm_interface.modem_connected = False

    with mock.patch.object(
        gsm_interface, "_send_sms", new_callable=mock.AsyncMock
    ) as send_sms:
        gsm_interface.send_message("Alarm!", EventLevel.INFO)
        await settle()

    send_sms.assert_not_awaited()


@pytest.mark.asyncio
async def test_sms_is_a_two_stage_exchange(gsm_interface):
    """Sending command and body together leaves the modem stuck in entry mode."""
    comm = gsm_interface.port

    with mock.patch.object(comm._protocol, "transport") as transport:
        task = asyncio.ensure_future(gsm_interface._send_sms("+1234567890", "Alarm!"))
        await settle()

        # Stage one: the command, answered by an unterminated entry prompt.
        transport.write.assert_called_once_with(b'AT+CMGS="+1234567890"\r\n')
        transport.write.reset_mock()

        modem_says(comm, b"\r\n> ")
        await settle()

        # Stage two: the body, ended by Ctrl-Z and with no line terminator.
        transport.write.assert_called_once_with(b"Alarm!\x1a")

        modem_says(comm, b"+CMGS: 42\r\nOK\r\n")
        await task

    assert comm.queue.empty()


@pytest.mark.asyncio
async def test_sms_failure_is_reported(gsm_interface):
    comm = gsm_interface.port

    with mock.patch.object(comm._protocol, "transport"):
        task = asyncio.ensure_future(gsm_interface._send_sms("+1234567890", "Alarm!"))
        await settle()
        modem_says(comm, b"\r\n> ")
        await settle()
        modem_says(comm, b"+CMS ERROR: 500\r\n")

        with pytest.raises(ValueError, match="rejected"):
            await task


@pytest.mark.asyncio
async def test_entry_mode_is_abandoned_when_no_prompt_arrives(gsm_interface):
    comm = gsm_interface.port

    with mock.patch.object(comm._protocol, "transport") as transport:
        task = asyncio.ensure_future(gsm_interface._send_sms("+1234567890", "Alarm!"))
        await settle()
        transport.write.reset_mock()

        modem_says(comm, b"+CMS ERROR: 310\r\n")

        with pytest.raises(ValueError, match="did not ask"):
            await task

    # ESC, so the next command is not swallowed as SMS text.
    transport.write.assert_called_once_with(b"\x1b")


@pytest.mark.asyncio
async def test_unsolicited_lines_do_not_satisfy_a_pending_command(gsm_interface):
    """An SMS arriving mid-send must not be mistaken for the modem's reply."""
    comm = gsm_interface.port

    with mock.patch.object(comm._protocol, "transport") as transport:
        task = asyncio.ensure_future(gsm_interface._send_sms("+1234567890", "Alarm!"))
        await settle()
        transport.write.reset_mock()

        modem_says(comm, b'+CUSD: 1,"registered",0\r\n')
        await settle()
        transport.write.assert_not_called()

        modem_says(comm, b"\r\n> ")
        await settle()
        transport.write.assert_called_once_with(b"Alarm!\x1a")

        modem_says(comm, b"OK\r\n")
        await task
