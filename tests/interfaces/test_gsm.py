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
