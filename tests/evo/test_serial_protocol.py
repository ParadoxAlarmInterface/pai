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

def test_37byte_message_in_many_chunks(mocker):
    cp = SerialConnectionProtocol(None, None)

    payloads = [
        b'\xe2\xff\xad\x06\x14',
        b'\x13\x01\x04\x0e\x10',
        b'\x00\x01\x05\x00\x00',
        b'\x00\x00\x00\x02Liv',
        b'ing room     \x00\xcc'
    ]
    mocker.patch.object(cp, 'read_queue')

    for p in payloads:
        cp.data_received(p)

    cp.read_queue.put_nowait.assert_called_with(b"".join(payloads))

def test_37byte_message_in_many_chunks_with_junk_in_front(mocker):
    cp = SerialConnectionProtocol(None, None)

    payloads = [
        b'\x01\x02\x03\x04\x05\x06\x07',
        b'\x01\x02\xe2\xff\xad\x06\x14',
        b'\x13\x01\x04\x0e\x10',
        b'\x00\x01\x05\x00\x00',
        b'\x00\x00\x00\x02Liv',
        b'ing room     \x00\xcc'
    ]
    mocker.patch.object(cp, 'read_queue')

    for p in payloads:
        cp.data_received(p)

    cp.read_queue.put_nowait.assert_called_with(b"".join(payloads)[9:])