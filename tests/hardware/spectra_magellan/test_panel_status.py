"""
Tests for Spectra/Magellan PanelStatus (build direction, PAI -> panel).

PanelStatus layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po.command = 0x50
  1       1     _not_used0 (Int8ub, default 0x00)
  2       1     validation (Int8ub, default 0x00)
  3       1     status_request (Int8ub, default 0x00)
  4       29    _not_used1 (Padding)
  33      1     source_id (default 1 = Winload_Direct)
  34      2     user_id (Int16ul, default 0)
  + Padding(31) — additional 31 bytes after RawCopy but before checksum
  Total fields struct = 36 bytes
  Total with extra Padding(31) = 67 bytes
  Checksum = 1 byte
  Total packet = 68 bytes

  Note: PanelStatus has an unusual extra Padding(31) outside the RawCopy struct
  but before the checksum. PacketChecksum covers only the 36 bytes in fields.data
  (the RawCopy content), not the 31 padding bytes.
"""

# pylint: disable=duplicate-code
import pytest

from paradox.hardware.spectra_magellan.parsers import PanelStatus


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def test_build_panel_status_defaults():
    """Build PanelStatus with all defaults."""
    raw = PanelStatus.build({"fields": {"value": {}}})

    # command = 0x50 at byte 0
    assert raw[0] == 0x50
    # _not_used0 = 0x00 at byte 1
    assert raw[1] == 0x00
    # validation = 0x00 at byte 2
    assert raw[2] == 0x00
    # status_request = 0x00 at byte 3
    assert raw[3] == 0x00
    # source_id = 1 (Winload_Direct) at byte 33
    assert raw[33] == 0x01
    # Total packet size = 36 (fields) + 31 (Padding) + 1 (checksum) = 68 bytes
    assert len(raw) == 68
    # checksum covers only the fields.data (first 36 bytes), not the padding
    assert raw[-1] == _checksum(raw[:36])


def test_build_panel_status_status_request_0():
    """Build PanelStatus for status_request=0."""
    raw = PanelStatus.build({"fields": {"value": {"status_request": 0}}})

    assert raw[3] == 0x00
    assert raw[-1] == _checksum(raw[:36])


def test_build_panel_status_status_request_1():
    """Build PanelStatus for status_request=1."""
    raw = PanelStatus.build({"fields": {"value": {"status_request": 1}}})

    assert raw[3] == 0x01
    assert raw[-1] == _checksum(raw[:36])


def test_build_panel_status_status_request_2():
    """Build PanelStatus for status_request=2."""
    raw = PanelStatus.build({"fields": {"value": {"status_request": 2}}})

    assert raw[3] == 0x02
    assert raw[-1] == _checksum(raw[:36])


def test_build_panel_status_total_length():
    """Total packet = 68 bytes (36 fields + 31 padding + 1 checksum)."""
    raw = PanelStatus.build({"fields": {"value": {}}})
    assert len(raw) == 68


def test_build_panel_status_checksum_validity():
    """Checksum = sum of first 36 bytes (fields.data) mod 256."""
    for req in range(5):
        raw = PanelStatus.build({"fields": {"value": {"status_request": req}}})
        assert raw[-1] == _checksum(
            raw[:36]
        ), f"Checksum failed for status_request={req}"


@pytest.mark.parametrize("status_request", [0, 1, 2, 3, 4, 5, 7])
def test_build_panel_status_various_requests(status_request):
    """Various status_request values build with valid checksums."""
    raw = PanelStatus.build({"fields": {"value": {"status_request": status_request}}})
    assert raw[3] == status_request
    assert raw[-1] == _checksum(raw[:36])
