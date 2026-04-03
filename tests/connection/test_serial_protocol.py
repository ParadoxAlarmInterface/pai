import binascii
from unittest.mock import MagicMock, call

from paradox.config import config as cfg
from paradox.connections.serial_connection import SerialConnectionProtocol


def test_6byte_message():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = binascii.unhexlify("120600000018")

    cp.data_received(payload)

    handler.on_message.assert_called_with(payload)


def test_37byte_message():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = b"\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc"

    cp.data_received(payload)

    handler.on_message.assert_called_with(payload)


def test_37byte_message_in_chunks():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = b"\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00"
    payload1 = b"\x00\x00\x00\x00\x02Living room     \x00\xcc"

    cp.data_received(payload)
    cp.data_received(payload1)

    handler.on_message.assert_called_with(payload + payload1)


def test_37byte_message_in_many_chunks():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payloads = [
        b"\xe2\xff\xad\x06\x14",
        b"\x13\x01\x04\x0e\x10",
        b"\x00\x01\x05\x00\x00",
        b"\x00\x00\x00\x02Liv",
        b"ing room     \x00\xcc",
    ]

    for p in payloads:
        cp.data_received(p)

    handler.on_message.assert_called_with(b"".join(payloads))


def test_37byte_message_in_many_chunks_with_junk_in_front():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payloads = [
        b"\x01\x02\x03\x04\x05\x06\x07",
        b"\x01\x02\xe2\xff\xad\x06\x14",
        b"\x13\x01\x04\x0e\x10",
        b"\x00\x01\x05\x00\x00",
        b"\x00\x00\x00\x02Liv",
        b"ing room     \x00\xcc",
    ]

    for p in payloads:
        cp.data_received(p)

    handler.on_message.assert_called_with(b"".join(payloads)[9:])


def test_sequential_6byte_and_37byte_with_junk_in_front_and_between():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payloads = [
        b"\x01\x02\x03\x04\x05\x06\x07\x12",
        b"\x06\x00",
        b"\x00\x00\x18\x01",
        b"\x02\x03\x04\x05\x06\x07",
        b"\x01\x02\xe2\xff\xad\x06\x14",
        b"\x13\x01\x04\x0e\x10",
        b"\x00\x01\x05\x00\x00",
        b"\x00\x00\x00\x02Liv",
        b"ing room     \x00\xcc",
    ]

    for p in payloads:
        cp.data_received(p)

    handler.call_count = 2
    handler.on_message.assert_has_calls(
        [
            call(b"\x12\x06\x00\x00\x00\x18"),
            call(
                b"\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc"
            ),
        ],
    )


def test_error_message():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = b"\x70\x04\x10\x84"

    cp.data_received(payload)

    handler.on_message.assert_called_with(payload)


def test_evo_eeprom_reading():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = binascii.unhexlify(
        "524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e"
    )

    cp.data_received(payload)

    handler.on_message.assert_called_with(payload)


def test_evo_eeprom_reading_in_chunks():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = binascii.unhexlify(
        "524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e"
    )

    chunk_length = 9
    payloads = [
        payload[y - chunk_length : y]
        for y in range(chunk_length, len(payload) + chunk_length, chunk_length)
    ]
    for p in payloads:
        # print(binascii.hexlify(p))
        cp.data_received(p)

    handler.on_message.assert_called_with(payload)


def test_evo_ram_reading():
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = binascii.unhexlify(
        "524780000010040200000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002f"
    )

    cp.data_received(payload)

    handler.on_message.assert_called_with(payload)


# ── Encrypted (E0 FE) framing tests ─────────────────────────────────────────


def test_encrypted_message_13bytes_calls_handler():
    """A 13-byte E0 FE message must be framed by length field and delivered."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    # TX from BabyWare capture: E0 FE 0D 00 14 67 76 68 99 28 00 05 04
    payload = bytes.fromhex("E0FE0D001467766899280005" + "04")
    cp.data_received(payload)

    handler.on_message.assert_called_once_with(payload)


def test_encrypted_message_12bytes_calls_handler():
    """A 12-byte E0 FE response message must be framed correctly."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    # RX from BabyWare capture: E0 FE 0C 00 14 67 36 1E A9 00 62 03
    payload = bytes.fromhex("E0FE0C001467361EA9006203")
    cp.data_received(payload)

    handler.on_message.assert_called_once_with(payload)


def test_encrypted_message_in_chunks():
    """E0 FE frame must be reassembled correctly when delivered in chunks."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = bytes.fromhex("E0FE0D001467766899280005" + "04")
    for byte in payload:
        cp.data_received(bytes([byte]))

    handler.on_message.assert_called_once_with(payload)


def test_encrypted_then_normal_message():
    """An E0 FE frame followed immediately by a normal message must both be delivered."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    enc_msg = bytes.fromhex("E0FE0C001467361EA9006203")
    norm_msg = binascii.unhexlify("120600000018")

    cp.data_received(enc_msg + norm_msg)

    assert handler.on_message.call_count == 2
    handler.on_message.assert_any_call(enc_msg)
    handler.on_message.assert_any_call(norm_msg)


def test_encrypted_message_46bytes():
    """A 46-byte E0 FE message from the test captures must be framed correctly."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    # From test_encryption.py - EVO192 7.50.000+ tx capture
    payload = bytes.fromhex(
        "E0FE2E0012C5CA4AB7DCB3C59206F6E9EB47761EC928BF2754EE41DDD3ABB4D088BBB3EE369BE21750FD52CC9119"
    )
    cp.data_received(payload)

    handler.on_message.assert_called_once_with(payload)


def test_encrypted_message_27bytes_calls_handler():
    """A 27-byte BabyWare compact E0 FE frame (from PR #337 TX) must be framed by length byte."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = bytes.fromhex("E0FE1B0000B3FEB64AFF82D038F4157335C5BEB5591970FC00FA0C")
    cp.data_received(payload)

    handler.on_message.assert_called_once_with(payload)


def test_encrypted_message_50bytes_calls_handler():
    """A 50-byte BabyWare compact E0 FE frame (from PR #337 RX) must be framed by length byte."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    payload = bytes.fromhex(
        "E0FE320001A5EFACC53587247F2FAADB054142"
        "7D2003497ABE670B8D1516A4D369136BA83259"
        "DE9424525BFABA4571003A14"
    )
    cp.data_received(payload)

    handler.on_message.assert_called_once_with(payload)


def test_pr337_sequence_babyware_compact_and_unencrypted():
    """Mixed sequence from PR #337: BabyWare compact followed by normal unencrypted frames."""
    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)

    # BabyWare compact TX (13 bytes) + RX (50 bytes) from the PR
    compact_tx = bytes.fromhex("E0FE0D0001A55FA8E417009304")
    compact_rx = bytes.fromhex(
        "E0FE320001A5EFACC53587247F2FAADB054142"
        "7D2003497ABE670B8D1516A4D369136BA83259"
        "DE9424525BFABA4571003A14"
    )
    # InitiateCommunicationResponse (37 bytes, unencrypted, from PR #337)
    init_comm_rsp = bytes.fromhex(
        "72FF04020000A15A01077001050B20D4"
        "001001000F2710201031FF5745564F31"
        "3932000083"
    )

    cp.data_received(compact_tx + compact_rx + init_comm_rsp)

    assert handler.on_message.call_count == 3
    handler.on_message.assert_any_call(compact_tx)
    handler.on_message.assert_any_call(compact_rx)
    handler.on_message.assert_any_call(init_comm_rsp)


# ── Encrypted mode integration tests ────────────────────────────────────────


def test_encrypted_mode_outgoing_wraps_in_e0fe(mocker):
    """When SERIAL_ENCRYPTED=True, send_message must write an E0 FE frame."""
    mocker.patch.object(cfg, "SERIAL_ENCRYPTED", True)
    mocker.patch.object(cfg, "PASSWORD", "1234")
    # Avoid asyncio.get_running_loop() in the base class connection_made
    from paradox.connections.protocols import ConnectionProtocol

    mocker.patch.object(ConnectionProtocol, "connection_made")

    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)
    raw_transport = MagicMock()
    cp.connection_made(raw_transport)

    # Manually populate the fields that the base connection_made would have set,
    # so that check_active() passes.
    from paradox.connections.serial_encryption import (
        EncryptedSerialTransport,
        make_serial_key,
    )

    key = make_serial_key("1234")
    cp.transport = EncryptedSerialTransport(raw_transport, key)
    cp._closed = MagicMock()
    cp._closed.done.return_value = False

    payload = bytes([0x72] + [0x00] * 35 + [0x72])
    cp.send_message(payload)

    written = raw_transport.write.call_args[0][0]
    assert written[0] >> 4 == 0xE
    assert written[1] == 0xFE


def test_encrypted_mode_incoming_e0fe_is_decrypted(mocker):
    """When SERIAL_ENCRYPTED=True, incoming E0 FE AES-256 frames are decrypted."""
    from paradox.lib.crypto import encrypt_serial_message

    mocker.patch.object(cfg, "SERIAL_ENCRYPTED", True)
    mocker.patch.object(cfg, "PASSWORD", "1234")
    from paradox.connections.protocols import ConnectionProtocol

    mocker.patch.object(ConnectionProtocol, "connection_made")

    handler = MagicMock()
    cp = SerialConnectionProtocol(handler)
    transport = MagicMock()
    cp.connection_made(transport)

    payload = bytes([0x72] + [0x00] * 35 + [0x72])
    key = b"1234" + b"\xee" * 28
    frame = encrypt_serial_message(payload, key)

    cp.data_received(frame)

    handler.on_message.assert_called_once_with(payload)
