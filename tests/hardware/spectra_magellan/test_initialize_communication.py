"""
Tests for Spectra/Magellan InitializeCommunication (build) and
InitializeCommunicationResponse (parse).

InitializeCommunication layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po.command = 0x00
  1       3     _not_used0 (Padding)
  4       1     product_id
  5       1     firmware.version
  6       1     firmware.revision
  7       1     firmware.build
  8       2     panel_id (Int16ub)
  10      2     pc_password (default b"0000")
  12      1     _not_used1 (Bytes(1))
  13      1     source_method (default 0x00 = Winload_Connection)
  14      4     user_code (Int32ub, default 0x00000000)
  18      15    _not_used2 (Padding)
  33      1     source_id (default 1 = Winload_Direct)
  34      2     user_id (Int16ul, default 0)
  Total fields = 36 bytes + 1 checksum = 37 bytes

InitializeCommunicationResponse layout (parse, panel -> PAI):
  Offset  Size  Field
  0       1     po.command = 0x10
  1       2     neware_connection (Int16ub)
  3       1     user_id_low (Int8ub)
  4       1     partition_rights (BitStruct: _not_used[6], partition_2, partition_1)
  5       31    _not_used0 (Padding)
  Total fields = 36 bytes + 1 checksum = 37 bytes
"""

# pylint: disable=duplicate-code
import pytest

from paradox.hardware.spectra_magellan.parsers import (
    InitializeCommunication,
    InitializeCommunicationResponse,
)


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def _build_init_comm(**kwargs):
    """Helper to build InitializeCommunication with all required fields."""
    # product_id, firmware, panel_id, _not_used1 have no Default and must be provided
    value = {
        "product_id": "SPECTRA_SP7000",
        "firmware": {"version": 6, "revision": 1, "build": 0},
        "panel_id": 0x0000,
        "pc_password": b"\x00\x00",
        "_not_used1": b"\x00",
    }
    value.update(kwargs)
    return InitializeCommunication.build({"fields": {"value": value}})


# ---------------------------------------------------------------------------
# InitializeCommunication — BUILD tests
# ---------------------------------------------------------------------------


def test_build_initialize_communication_defaults():
    """Build InitializeCommunication with required fields returns a valid packet."""
    raw = _build_init_comm()

    # command = 0x00 at byte 0
    assert raw[0] == 0x00
    # Total length = 37 bytes
    assert len(raw) == 37
    # Checksum valid
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_product_id_mg5050():
    """Build sets product_id for MG5050."""
    raw = _build_init_comm(
        product_id="MAGELLAN_MG5050",  # = 65
        firmware={"version": 6, "revision": 1, "build": 0},
    )

    assert raw[0] == 0x00  # command
    # product_id at offset 4
    assert raw[4] == 65  # MAGELLAN_MG5050
    # firmware version at offset 5
    assert raw[5] == 6
    assert raw[6] == 1
    assert raw[7] == 0
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_spectra_sp6000():
    """Build sets product_id for SP6000."""
    raw = _build_init_comm(product_id="SPECTRA_SP6000")  # = 22

    assert raw[4] == 22  # SPECTRA_SP6000
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_pc_password():
    """Build with a custom pc_password."""
    raw = _build_init_comm(pc_password=b"\x12\x34")

    # pc_password at offset 10-11
    assert raw[10] == 0x12
    assert raw[11] == 0x34
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_source_method_neware():
    """Build with source_method = NEware_Connection."""
    raw = _build_init_comm(source_method="NEware_Connection")

    # source_method at offset 13
    assert raw[13] == 0x55
    assert raw[-1] == _checksum(raw[:-1])


def test_build_initialize_communication_total_length():
    """Total packet length is 37 bytes."""
    raw = _build_init_comm()
    assert len(raw) == 37


@pytest.mark.parametrize(
    "product_id,expected_byte",
    [
        ("MAGELLAN_MG5000", 64),
        ("MAGELLAN_MG5050", 65),
        ("SPECTRA_SP5500", 21),
        ("SPECTRA_SP6000", 22),
        ("SPECTRA_SP7000", 23),
    ],
)
def test_build_initialize_communication_product_ids(product_id, expected_byte):
    """Build correctly encodes various product IDs."""
    raw = _build_init_comm(product_id=product_id)
    assert raw[4] == expected_byte
    assert raw[-1] == _checksum(raw[:-1])


# ---------------------------------------------------------------------------
# InitializeCommunicationResponse — PARSE tests
# ---------------------------------------------------------------------------


def _build_init_comm_response(
    neware_connection=0x0000,
    user_id_low=0x00,
    partition_2=False,
    partition_1=False,
):
    """
    Construct InitializeCommunicationResponse bytes manually.

    Byte 0: command = 0x10
    Bytes 1-2: neware_connection (Int16ub)
    Byte 3: user_id_low
    Byte 4: partition_rights BitStruct: [7:2]=0, [1]=partition_2, [0]=partition_1
    Bytes 5-35: _not_used0 (Padding, 31 bytes)
    Byte 36: checksum
    """
    b0 = 0x10
    b1 = (neware_connection >> 8) & 0xFF
    b2 = neware_connection & 0xFF
    b3 = user_id_low
    b4 = (int(partition_2) << 1) | int(partition_1)
    data = bytes([b0, b1, b2, b3, b4]) + b"\x00" * 31
    cs = _checksum(data)
    return data + bytes([cs])


def test_parse_init_communication_response_basic():
    """Parse basic InitializeCommunicationResponse with no flags."""
    raw = _build_init_comm_response()
    data = InitializeCommunicationResponse.parse(raw)

    assert data.fields.value.po.command == 0x10
    assert data.fields.value.neware_connection == 0
    assert data.fields.value.user_id_low == 0
    assert data.fields.value.partition_rights.partition_1 is False
    assert data.fields.value.partition_rights.partition_2 is False


def test_parse_init_communication_response_partition_1():
    """Parse InitializeCommunicationResponse with partition_1 access."""
    raw = _build_init_comm_response(partition_1=True)
    data = InitializeCommunicationResponse.parse(raw)

    assert data.fields.value.partition_rights.partition_1 is True
    assert data.fields.value.partition_rights.partition_2 is False


def test_parse_init_communication_response_both_partitions():
    """Parse InitializeCommunicationResponse with both partitions."""
    raw = _build_init_comm_response(partition_1=True, partition_2=True)
    data = InitializeCommunicationResponse.parse(raw)

    assert data.fields.value.partition_rights.partition_1 is True
    assert data.fields.value.partition_rights.partition_2 is True


def test_parse_init_communication_response_neware_connection():
    """Parse InitializeCommunicationResponse with neware_connection value."""
    raw = _build_init_comm_response(neware_connection=0x0001)
    data = InitializeCommunicationResponse.parse(raw)

    assert data.fields.value.neware_connection == 1


def test_parse_init_communication_response_user_id_low():
    """Parse InitializeCommunicationResponse with user_id_low set."""
    raw = _build_init_comm_response(user_id_low=0x05)
    data = InitializeCommunicationResponse.parse(raw)

    assert data.fields.value.user_id_low == 5
