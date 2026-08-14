import asyncio
from unittest import mock

import pytest

from paradox.connections.gsm.connection import GsmSerialConnection
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
        asyncio.get_event_loop().call_soon(comm.on_connection)
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
