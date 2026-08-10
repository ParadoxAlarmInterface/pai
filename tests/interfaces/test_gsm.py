import asyncio
from unittest import mock

import pytest

from paradox.interfaces.text.gsm import (
    GSMTextInterface,
    SerialCommunication,
    SerialConnectionProtocol,
)


@pytest.fixture
async def connected_serial_communication():
    port = "test_port"
    baud = 9600
    timeout = 5
    comm = SerialCommunication(port, baud, timeout)

    assert comm.queue.empty()

    async def mocked_create_serial_connection(loop, protocol_factory, *args, **kwargs):
        transport = mock.Mock()
        protocol = comm.make_protocol()
        asyncio.get_event_loop().call_soon(protocol.connection_made, transport)
        return (transport, protocol)

    with mock.patch(
        "serial_asyncio.create_serial_connection",
        new_callable=mock.AsyncMock,
        side_effect=mocked_create_serial_connection,
    ):
        asyncio.get_event_loop().call_soon(comm.on_connection)
        result = await comm.connect()
        assert result

    assert comm.connected

    return comm


# Test SerialConnectionProtocol class
@pytest.mark.asyncio
async def test_serial_connection_protocol():
    handler = mock.MagicMock()
    protocol = SerialConnectionProtocol(handler)

    transport = mock.MagicMock()
    protocol.connection_made(transport)
    handler.on_connection.assert_called_once()

    message = b"test_message"
    await protocol.send_message(message)
    transport.write.assert_called_once_with(message + b"\r\n")

    recv_data = b"test_data\r\n"
    protocol.data_received(recv_data)
    handler.on_message.assert_called_once_with(b"test_data")

    exc = Exception("test_exception")
    protocol.connection_lost(exc)
    handler.on_connection_loss.assert_called_once_with()


@pytest.mark.asyncio
async def test_serial_connection_protocol_reassembles_split_frames():
    # Characterization test: pins the existing framing contract so the buffer
    # can later be swapped for a shared framer. Not a regression test -- the
    # pre-refactor loop passed this too.
    handler = mock.MagicMock()
    protocol = SerialConnectionProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    protocol.data_received(b"par")
    handler.on_message.assert_not_called()

    protocol.data_received(b"tial\r\n\r\nOK\r\ntrail")

    assert handler.on_message.call_args_list == [
        mock.call(b"partial"),
        mock.call(b"OK"),
    ]
    assert protocol.buffer == b"trail"

    protocol.reset_framing()
    assert protocol.buffer == b""


@pytest.mark.asyncio
async def test_serial_connection_protocol_drops_echoed_message():
    # Characterization test: documents that echo suppression requires an exact
    # match against the last sent message. See the follow-up issue on GSM
    # framing for the `\r`-only echo and sticky `last_message` shortcomings.
    handler = mock.MagicMock()
    protocol = SerialConnectionProtocol(handler)
    protocol.connection_made(mock.MagicMock())

    await protocol.send_message(b"AT")
    protocol.data_received(b"AT\r\nOK\r\n")

    handler.on_message.assert_called_once_with(b"OK")


# Test SerialCommunication class
@pytest.mark.asyncio
async def test_serial_communication(connected_serial_communication):
    comm = connected_serial_communication

    write_message = b"write_message"
    write_response_message = b"write_response_message"
    read_message = b"read_message"

    asyncio.get_event_loop().call_soon(comm.on_message, write_response_message)
    result = await comm.write(write_message)
    assert result == write_response_message

    asyncio.get_event_loop().call_soon(comm.on_message, read_message)
    await comm.read()
    assert comm.queue.empty()

    callback = mock.MagicMock()
    comm.set_recv_callback(callback)
    assert comm.recv_callback == callback
    comm.on_message(read_message)
    callback.assert_called_once_with(read_message)


# Test GSMTextInterface class
@pytest.mark.asyncio
async def test_gsm_text_interface(connected_serial_communication):
    alarm = mock.MagicMock()
    event = asyncio.Event()

    async def control_partition(partition, command):
        assert partition == "outside"
        assert command == "arm"
        event.set()

        return True

    interface = GSMTextInterface(alarm)
    interface.port = connected_serial_communication
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
