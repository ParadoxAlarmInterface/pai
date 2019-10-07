from mock import call, MagicMock
import binascii

from paradox.connections.serial_connection import SerialConnectionProtocol


def test_6byte_message():
    cp = SerialConnectionProtocol(None, None)

    payload = binascii.unhexlify('120600000018')
    cp.read_queue = MagicMock()

    cp.data_received(payload)

    cp.read_queue.put_nowait.assert_called_with(payload)


def test_37byte_message():
    cp = SerialConnectionProtocol(None, None)

    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc'
    cp.read_queue = MagicMock()

    cp.data_received(payload)

    cp.read_queue.put_nowait.assert_called_with(payload)


def test_37byte_message_in_chunks():
    cp = SerialConnectionProtocol(None, None)

    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00'
    payload1 = b'\x00\x00\x00\x00\x02Living room     \x00\xcc'
    cp.read_queue = MagicMock()

    cp.data_received(payload)
    cp.data_received(payload1)

    cp.read_queue.put_nowait.assert_called_with(payload + payload1)


def test_37byte_message_in_many_chunks():
    cp = SerialConnectionProtocol(None, None)

    payloads = [
        b'\xe2\xff\xad\x06\x14',
        b'\x13\x01\x04\x0e\x10',
        b'\x00\x01\x05\x00\x00',
        b'\x00\x00\x00\x02Liv',
        b'ing room     \x00\xcc'
    ]
    cp.read_queue = MagicMock()

    for p in payloads:
        cp.data_received(p)

    cp.read_queue.put_nowait.assert_called_with(b"".join(payloads))


def test_37byte_message_in_many_chunks_with_junk_in_front():
    cp = SerialConnectionProtocol(None, None)

    payloads = [
        b'\x01\x02\x03\x04\x05\x06\x07',
        b'\x01\x02\xe2\xff\xad\x06\x14',
        b'\x13\x01\x04\x0e\x10',
        b'\x00\x01\x05\x00\x00',
        b'\x00\x00\x00\x02Liv',
        b'ing room     \x00\xcc'
    ]
    cp.read_queue = MagicMock()

    for p in payloads:
        cp.data_received(p)

    cp.read_queue.put_nowait.assert_called_with(b"".join(payloads)[9:])


def test_sequential_6byte_and_37byte_with_junk_in_front_and_between():
    cp = SerialConnectionProtocol(None, None)

    payloads = [
        b'\x01\x02\x03\x04\x05\x06\x07\x12',
        b'\x06\x00',
        b'\x00\x00\x18\x01',
        b'\x02\x03\x04\x05\x06\x07',
        b'\x01\x02\xe2\xff\xad\x06\x14',
        b'\x13\x01\x04\x0e\x10',
        b'\x00\x01\x05\x00\x00',
        b'\x00\x00\x00\x02Liv',
        b'ing room     \x00\xcc'
    ]
    cp.read_queue = MagicMock()

    for p in payloads:
        cp.data_received(p)

    cp.read_queue.put_nowait.call_count = 2
    cp.read_queue.put_nowait.assert_has_calls([
        call(
            b'\x12\x06\x00\x00\x00\x18'
        ),
        call(
            b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc'
        )
    ],
    )


def test_error_message():
    cp = SerialConnectionProtocol(None, None)

    payload = b'\x70\x04\x10\x84'
    cp.read_queue = MagicMock()

    cp.data_received(payload)

    cp.read_queue.put_nowait.assert_called_with(payload)


def test_evo_eeprom_reading():
    cp = SerialConnectionProtocol(None, None)

    payload = binascii.unhexlify(
        '524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e')

    cp.read_queue = MagicMock()

    cp.data_received(payload)

    cp.read_queue.put_nowait.assert_called_with(payload)


def test_evo_eeprom_reading_in_chunks(mocker):
    cp = SerialConnectionProtocol(None, None)

    payload = binascii.unhexlify(
        '524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e')

    cp.read_queue = MagicMock()

    chunk_length = 9
    payloads = [payload[y - chunk_length:y] for y in range(chunk_length, len(payload) + chunk_length, chunk_length)]
    for p in payloads:
        # print(binascii.hexlify(p))
        cp.data_received(p)

    cp.read_queue.put_nowait.assert_called_with(payload)


def test_evo_ram_reading(mocker):
    cp = SerialConnectionProtocol(None, None)

    payload = binascii.unhexlify(
        '524780000010040200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002f')

    cp.read_queue = MagicMock()

    cp.data_received(payload)

    cp.read_queue.put_nowait.assert_called_with(payload)
