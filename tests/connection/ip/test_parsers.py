import pytest

from paradox.connections.ip.parsers import (
    IPMessageRequest,
    IPMessageResponse,
    IPPayloadConnectResponse,
)
from paradox.hardware.parsers import Encrypted


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
        key=b"\xaa" * 16,
        hardware_version=0x0100,
        ip_firmware_major=0x05,
        ip_firmware_minor=0x02,
        ip_module_serial=b"\x71\x12\x34\x56",
    )
    data = IPPayloadConnectResponse.parse(raw)

    assert data.login_status == "success"
    assert data.key == b"\xaa" * 16
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
        ip_module_serial=b"\x71\xaa\xbb\xcc",
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


# ---------------------------------------------------------------------------
# Encrypted — PARSE tests
# ---------------------------------------------------------------------------
# Real captured frames from EVO192 (firmware 7.50.000+) and SP6000+.
# Format: [E0|status_nibble][FE][length][not_used][request_nr][data...][checksum][end]
# Verifies that Encrypted.parse() extracts the data field correctly.


@pytest.mark.parametrize(
    "payload_hex",
    [
        # from EVO192 7.50.000+ firmware
        # tx
        (
            "E0 FE 2E 00 12 C5 CA 4A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 EE 36 9B E2 17 50 FD 52 CC 91 19"
        ),
        # rx
        (
            "E0 FE 2E 00 12 C5 3F 0A B7 DC 83 97 D4 06 F6 E9 EB 47 56 5C 89 38 BF 35 F0 EA A5 DC C3 2B 95 D2 80 E9 B3 EE 36 9B E2 17 50 FD B4 CC 7C 19"
        ),
        # tx
        (
            "E0 FE 2E 00 12 01 79 71 35 21 C7 F1 C5 3F 0A B7 DC B3 E5 D0 46 E6 E9 F9 E3 72 FA C8 38 3F 06 56 E6 13 DD D3 AB B4 D0 88 BB B3 77 B4 11 19"
        ),
        # rx
        ("E0 FE 0F 00 12 01 3D 77 35 21 F7 03 B4 B8 04"),
        (
            "E0 FE 2E 00 13 80 4F F6 7E FD 6A 3B 91 85 52 E2 45 A5 52 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC E0 69 9B 16"
        ),
        (
            "E0 FE 2E 00 14 61 CB D8 54 3E 81 E5 F1 2B BC E0 EE BB B2 EE 36 9B E2 17 50 FD 2D 15 F3 05 D7 2F B5 59 19 60 FC 6B F3 CC 76 B8 28 D3 4A 18"
        ),
        # tx
        ("E0 FE 11 00 14 F5 78 3D 21 F7 59 83 BF 54 BC 70 07"),
        # rx
        (
            "E0 FE 50 00 14 F5 7A 90 21 F7 59 83 0F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 EE 36 9B E2 17 50 FD 2D 15 F3 05 D7 2F B5 59 19 60 FC 6B F3 CC 76 B8 8E 81 F7 D4 49 FC 06 BE 6E E3 4E 29 99 BC E5 2A"
        ),
        # tx
        ("E0 FE 11 00 14 E3 42 95 95 56 5A DB 25 19 8C A7 06"),
        # rx
        (
            "E0 FE 50 00 14 E3 40 38 95 56 5A DB A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 B3 A3 FE B6 8B E2 17 50 ED 07 15 F3 05 D7 2F B5 F1 8C FD 29"
        ),
        # tx
        ("E0 FE 11 00 14 A8 76 23 8A F9 6A EF 5A E3 24 81 07"),
        # rx
        (
            "E0 FE 50 00 14 A8 74 8E 8A F9 6A EF DA 3D B2 83 09 7E BC 6F 4B 9D 95 56 A0 DF A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 B5 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 16 24 69 2A"
        ),
        # tx
        ("E0 FE 11 00 14 B7 E4 97 24 7F E4 CE FB 4F B8 8C 08"),
        # rx
        (
            "E0 FE 50 00 14 B7 F4 0A 24 7F E4 CE F9 90 CF DA 3D B2 83 09 7E BC 6F 4B 9D 95 56 A0 DF A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 25 B8 72 2A"
        ),
        # tx
        ("E0 FE 11 00 14 F7 BC 57 EC F4 65 C7 A4 1F 84 60 08"),
        # rx
        (
            "E0 FE 50 00 14 F7 BE FA EC F4 65 C7 24 7F 2B 8A F9 90 CF DA 3D B2 83 09 7E BC 6F 4B 9D 95 56 A0 DF A5 46 DB 28 77 5D DC 9C 64 42 DB BA BE 47 79 71 35 21 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD A3 84 C3 2A"
        ),
        # tx
        ("E0 FE 11 00 14 F9 3F 57 79 71 8F C8 26 F8 10 01 07"),
        # rx
        (
            "E0 FE 4C 00 14 F9 2F 4A 79 71 8F C8 F7 A3 83 3F 0A B7 DC B3 C5 92 06 F6 E9 EB 47 76 1E C9 28 BF 27 54 EE 41 DD D3 AB B4 D0 88 BB B3 EE 36 9B E2 17 50 FD 2D 15 F3 05 D7 2F B5 59 19 60 FC 6B F3 CC 76 B8 8E 81 F7 D4 49 5D 10 7E 28"
        ),
        # from SP6000+
        (
            "e0 fe 2e 00 00 78 04 c1 92 06 f6 e9 eb 47 76 1e c9 28 bf 27 54 ee 41 dd d3 ab b4 d0 88 bb b3 ee 36 9b e2 17 50 fd 2d 15 f3 05 20 6b 7f 16"
        ),
    ],
)
def test_encrypted_parse(payload_hex: str):
    payload = bytes.fromhex(payload_hex)
    data = Encrypted.parse(payload)
    assert data.fields.value.data == payload[5:-2]
