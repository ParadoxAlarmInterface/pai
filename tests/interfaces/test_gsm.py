import asyncio
from unittest import mock

import pytest

from paradox.config import config as cfg
from paradox.connections.gsm.connection import GsmSerialConnection
from paradox.event import EventLevel
from paradox.interfaces.text import gsm
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


@pytest.mark.asyncio
async def test_concurrent_sends_are_serialised(gsm_interface):
    """Two AT commands in flight at once make the second the first SMS's body."""
    comm = gsm_interface.port

    with mock.patch.object(comm._protocol, "transport") as transport:
        first = asyncio.ensure_future(gsm_interface._send_sms("+1", "one"))
        second = asyncio.ensure_future(gsm_interface._send_sms("+2", "two"))
        await settle()

        # Only the first exchange has reached the modem.
        assert [c.args[0] for c in transport.write.call_args_list] == [
            b'AT+CMGS="+1"\r\n'
        ]

        modem_says(comm, b"\r\n> ")
        await settle()
        modem_says(comm, b"OK\r\n")
        await first

        # The second waits its turn rather than interleaving.
        await settle()
        assert transport.write.call_args_list[-1].args[0] == b'AT+CMGS="+2"\r\n'

        modem_says(comm, b"\r\n> ")
        await settle()
        modem_says(comm, b"OK\r\n")
        await second


@pytest.mark.asyncio
async def test_at_command_reports_a_rejection_immediately(gsm_interface):
    """An ERROR used to be swallowed and cost a full command timeout."""
    comm = gsm_interface.port
    comm.set_recv_callback(None)

    with mock.patch.object(comm._protocol, "transport"):
        task = asyncio.ensure_future(gsm_interface._at_command(b"AT+CUSD=1"))
        await settle()
        modem_says(comm, b"+CME ERROR: operation not supported\r\n")

        with pytest.raises(ValueError, match="rejected"):
            await task


@pytest.mark.asyncio
async def test_at_command_skips_informational_lines(gsm_interface):
    comm = gsm_interface.port
    comm.set_recv_callback(None)

    with mock.patch.object(comm._protocol, "transport"):
        task = asyncio.ensure_future(gsm_interface._at_command(b"AT+CSQ"))
        await settle()
        modem_says(comm, b"+CSQ: 19,99\r\nOK\r\n")

        assert await task == b"OK"


@pytest.mark.asyncio
async def test_run_reconnects_after_the_modem_drops(gsm_interface):
    """on_connection_loss clears only the transport's flag; run() must notice."""
    connects = []

    async def fake_connect():
        connects.append(True)
        gsm_interface.modem_connected = True
        gsm_interface.port.connected = True
        return True

    with mock.patch.object(gsm, "MODEM_POLL_INTERVAL", 0), mock.patch.object(
        gsm_interface, "connect", side_effect=fake_connect
    ):
        task = asyncio.ensure_future(gsm_interface.run())
        await settle()
        assert connects == []  # already connected, nothing to do

        gsm_interface.port.connected = False  # modem unplugged
        await settle()

        task.cancel()

    assert connects, "run() never reconnected after the port dropped"


@pytest.mark.asyncio
async def test_connect_closes_the_previous_port(gsm_interface):
    """A failed retry used to leak the previous connection object."""
    old = gsm_interface.port

    with mock.patch.object(
        old, "close", new_callable=mock.AsyncMock
    ) as close, mock.patch.object(
        gsm.GsmSerialConnection, "connect", new_callable=mock.AsyncMock
    ) as connect:
        connect.return_value = False
        assert await gsm_interface.connect() is False

    close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_cancels_in_flight_sends(gsm_interface):
    comm = gsm_interface.port

    with mock.patch.object(comm._protocol, "transport"), mock.patch.object(
        cfg, "GSM_CONTACTS", ["+1"]
    ):
        gsm_interface.send_message("Alarm!", EventLevel.INFO)
        await settle()
        task = next(iter(gsm_interface._send_tasks))

        gsm_interface.stop()
        await settle()

    assert task.cancelled()


@pytest.mark.asyncio
async def test_a_stale_ok_does_not_satisfy_the_next_command(gsm_interface):
    """The late answer to a timed-out command used to be handed to the next."""
    comm = gsm_interface.port
    comm.set_recv_callback(None)

    with mock.patch.object(comm._protocol, "transport"):
        with pytest.raises(asyncio.TimeoutError):
            await gsm_interface._at_command(b"AT+A", timeout=0.01)

        modem_says(comm, b"OK\r\n")  # A's answer, arriving too late

        task = asyncio.ensure_future(gsm_interface._at_command(b"AT+B"))
        await settle()
        assert not task.done(), "the stale OK was taken as B's reply"

        modem_says(comm, b"OK\r\n")
        assert await task == b"OK"


@pytest.mark.asyncio
async def test_a_stale_line_is_not_mistaken_for_the_sms_prompt(gsm_interface):
    comm = gsm_interface.port
    comm.on_message(b"stale")  # left behind by an earlier timeout

    with mock.patch.object(comm._protocol, "transport"):
        task = asyncio.ensure_future(gsm_interface._send_sms("+1", "hi"))
        await settle()
        modem_says(comm, b"\r\n> ")
        await settle()
        modem_says(comm, b"OK\r\n")

        await task
