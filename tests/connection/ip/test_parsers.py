from paradox.connections.ip.parsers import (
    IPMessageRequest,
    IPMessageResponse,
    IPPayloadConnectResponse,
)


def test_IPMessageRequest_defaults():
    key = b"12345abcde"
    test_payload = b"abcdefg"

    a = IPMessageRequest.build(dict(payload=test_payload), password=key)
    print(a)
    data = IPMessageRequest.parse(a, password=key)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_request"
    assert data.header.length == len(test_payload)
    assert data.header.flags.encrypt is True
    assert data.header.flags.installer_mode is False
    assert data.header.cryptor_code == "none"
    assert data.header.sequence_id == 0xEE
    assert data.header.command == "passthrough"
    assert data.header.wt == 0
    assert data.header.sb == 0
    assert data.payload == test_payload


def test_IPMessageRequest_cryptor_sequence():
    key = b"12345abcde"
    test_payload = b"abcdefg"

    a = IPMessageRequest.build(
        dict(payload=test_payload, header=dict(sequence_id=1, cryptor_code="none")),
        password=key,
    )
    print(a)
    assert a[9] == 0
    assert a[11] == 1

    data = IPMessageRequest.parse(a, password=key)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_request"
    assert data.header.length == len(test_payload)
    assert data.header.flags.encrypt is True
    assert data.header.flags.installer_mode is False
    assert data.header.command == "passthrough"
    assert data.header.wt == 0
    assert data.header.sb == 0
    assert data.payload == test_payload


def test_IPMessageResponse_defaults():
    key = b"12345abcde"
    test_payload = b"abcdefg"

    a = IPMessageResponse.build(dict(payload=test_payload), password=key)
    print(a)
    data = IPMessageResponse.parse(a, password=key)

    assert data.header.sof == 0xAA
    assert data.header.message_type == "ip_response"
    assert data.header.length == len(test_payload)
    assert data.header.flags.encrypt is True
    assert data.header.flags.installer_mode is False
    assert data.header.command == "passthrough"
    assert data.header.wt == 0
    assert data.header.sb == 3
    assert data.payload == test_payload


# ---------------------------------------------------------------------------
# IPPayloadConnectResponse — PARSE tests
# ---------------------------------------------------------------------------
# Layout (25 bytes total):
#   Byte 0:     login_status (Enum)
#   Bytes 1-16: key (16 bytes)
#   Bytes 17-18: hardware_version (Int16ub)
#   Byte 19:    ip_firmware_major (HexInt = ExprAdapter on Int8ub)
#   Byte 20:    ip_firmware_minor (HexInt)
#   Bytes 21-24: ip_module_serial (4 bytes)
#   ip_type: Pointer(21, ...) — reads byte at position 21 (= serial[0]) non-destructively
#
# HexInt decode: int(hex(raw_byte)[2:], 10)
#   e.g. raw=0x05 → hex="0x5" → "5" → int("5",10) = 5
#   e.g. raw=0x50 → hex="0x50" → "50" → int("50",10) = 50


def _build_ip_payload_connect_response(
    login_status=0x00,  # success
    key=b"\x00" * 16,
    hardware_version=0x0000,
    ip_firmware_major=0x05,
    ip_firmware_minor=0x02,
    ip_module_serial=b"\x71\x00\x00\x00",  # IP150 serial (first byte 0x71)
):
    """Construct raw IPPayloadConnectResponse bytes."""
    assert len(key) == 16
    assert len(ip_module_serial) == 4
    hw_high = (hardware_version >> 8) & 0xFF
    hw_low = hardware_version & 0xFF
    return bytes(
        [login_status]
        + list(key)
        + [hw_high, hw_low, ip_firmware_major, ip_firmware_minor]
        + list(ip_module_serial)
    )


def test_parse_ip_payload_connect_response_success():
    """Parse a successful IP connect response."""
    raw = _build_ip_payload_connect_response(
        login_status=0x00,
        key=b"\xAA" * 16,
        hardware_version=0x0100,
        ip_firmware_major=0x05,
        ip_firmware_minor=0x02,
        ip_module_serial=b"\x71\x12\x34\x56",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.login_status == "success"
    assert data.key == b"\xAA" * 16
    assert data.hardware_version == 0x0100
    assert data.ip_module_serial == b"\x71\x12\x34\x56"


def test_parse_ip_payload_connect_response_invalid_password():
    """Parse an invalid_password connect response."""
    raw = _build_ip_payload_connect_response(
        login_status=0x01,
        key=b"\x00" * 16,
        ip_module_serial=b"\x71\x00\x00\x00",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.login_status == "invalid_password"


def test_parse_ip_payload_connect_response_user_already_connected():
    """Parse user_already_connected connect response."""
    raw = _build_ip_payload_connect_response(
        login_status=0x02,
        key=b"\x00" * 16,
        ip_module_serial=b"\x71\x00\x00\x00",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.login_status == "user_already_connected"


def test_parse_ip_payload_connect_response_user_already_connected1():
    """Parse user_already_connected1 (0x04) connect response."""
    raw = _build_ip_payload_connect_response(
        login_status=0x04,
        key=b"\x00" * 16,
        ip_module_serial=b"\x71\x00\x00\x00",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.login_status == "user_already_connected1"


def test_parse_ip_payload_connect_response_key_contents():
    """Parse verifies the key field is preserved exactly."""
    test_key = bytes(range(16))
    raw = _build_ip_payload_connect_response(
        key=test_key,
        ip_module_serial=b"\x71\x00\x00\x00",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.key == test_key


def test_parse_ip_payload_connect_response_hardware_version():
    """Parse verifies hardware_version is decoded as big-endian."""
    raw = _build_ip_payload_connect_response(
        hardware_version=0x0203,
        ip_module_serial=b"\x71\x00\x00\x00",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.hardware_version == 0x0203


def test_parse_ip_payload_connect_response_ip150_type():
    """Parse ip_type as IP150 when first serial byte is 0x71."""
    raw = _build_ip_payload_connect_response(
        ip_module_serial=b"\x71\xAA\xBB\xCC",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.ip_type == "IP150"


def test_parse_ip_payload_connect_response_ip100_type():
    """Parse ip_type as IP100 when first serial byte is 0x70."""
    raw = _build_ip_payload_connect_response(
        ip_module_serial=b"\x70\x00\x00\x00",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.ip_type == "IP100"


def test_parse_ip_payload_connect_response_firmware_versions():
    """Parse ip_firmware_major and ip_firmware_minor using HexInt adapter."""
    # HexInt: raw 0x05 → int(hex(5)[2:], 10) = int("5", 10) = 5
    # HexInt: raw 0x02 → int(hex(2)[2:], 10) = int("2", 10) = 2
    raw = _build_ip_payload_connect_response(
        ip_firmware_major=0x05,
        ip_firmware_minor=0x02,
        ip_module_serial=b"\x71\x00\x00\x00",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.ip_firmware_major == 5
    assert data.ip_firmware_minor == 2


def test_parse_ip_payload_connect_response_serial_preserved():
    """Parse verifies ip_module_serial bytes are preserved."""
    serial = b"\x71\x01\x02\x03"
    raw = _build_ip_payload_connect_response(ip_module_serial=serial)
    data = IPPayloadConnectResponse.parse(raw)

    assert data.ip_module_serial == serial
