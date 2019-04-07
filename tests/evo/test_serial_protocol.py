import mock
import binascii
from pytest_mock import mocker

from paradox.connections.serial_connection import SerialConnectionProtocol

def test_6byte_message(mocker):
    cp = SerialConnectionProtocol(None, None)

    payload = binascii.unhexlify('120600000018')
    mocker.patch.object(cp, 'read_queue')

    cp.data_received(payload)

    cp.read_queue.put_nowait.assert_called_with(payload)

def test_37byte_message(mocker):
    cp = SerialConnectionProtocol(None, None)

    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc'
    mocker.patch.object(cp, 'read_queue')

    cp.data_received(payload)

    cp.read_queue.put_nowait.assert_called_with(payload)

def test_37byte_message_in_chunks(mocker):
    cp = SerialConnectionProtocol(None, None)

    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00'
    payload1 = b'\x00\x00\x00\x00\x02Living room     \x00\xcc'
    mocker.patch.object(cp, 'read_queue')

    cp.data_received(payload)
    cp.data_received(payload1)

    cp.read_queue.put_nowait.assert_called_with(payload + payload1)