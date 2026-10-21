"""
Unit tests for PRT3 ASCII command encoder.

Each test verifies:
  - exact output bytes (including trailing \\r)
  - output is valid ASCII
  - echo prefix (first 5 chars of decoded output, excl. \\r) matches what the panel
    would echo back to identify the reply
"""

import pytest

from paradox.hardware.prt3.encoder import (
    ARM_MODE_AWAY,
    ARM_MODE_FORCE,
    ARM_MODE_INSTANT,
    ARM_MODE_STAY,
    encode_area_label_request,
    encode_area_status_request,
    encode_arm,
    encode_disarm,
    encode_panic_emergency,
    encode_panic_fire,
    encode_panic_medical,
    encode_quick_arm,
    encode_utility_key,
    encode_user_label_request,
    encode_zone_label_request,
    encode_zone_status_request,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode(b: bytes) -> str:
    """Assert b is bytes, ASCII-decodable, ends with \\r; return stripped text."""
    assert isinstance(b, bytes), f"expected bytes, got {type(b).__name__}"
    text = b.decode("ascii")           # raises if not valid ASCII
    assert text.endswith("\r"), f"command must end with \\r: {b!r}"
    return text[:-1]                   # strip trailing \r for inspection


def _echo_prefix(b: bytes) -> str:
    """Return the first 5 chars of the command (what the panel echoes)."""
    return _decode(b)[:5]


# ---------------------------------------------------------------------------
# encode_area_status_request  RA{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodeAreaStatusRequest:
    def test_area_1(self):
        assert encode_area_status_request(1) == b"RA001\r"

    def test_area_8(self):
        assert encode_area_status_request(8) == b"RA008\r"

    def test_area_4(self):
        assert encode_area_status_request(4) == b"RA004\r"

    def test_output_is_bytes_ending_cr(self):
        b = encode_area_status_request(1)
        _decode(b)   # asserts bytes + \r + ascii

    def test_echo_prefix(self):
        assert _echo_prefix(encode_area_status_request(3)) == "RA003"

    @pytest.mark.parametrize("bad", [0, 9, -1, 100])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError):
            encode_area_status_request(bad)


# ---------------------------------------------------------------------------
# encode_zone_status_request  RZ{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodeZoneStatusRequest:
    def test_zone_1(self):
        assert encode_zone_status_request(1) == b"RZ001\r"

    def test_zone_192(self):
        assert encode_zone_status_request(192) == b"RZ192\r"

    def test_zone_96(self):
        assert encode_zone_status_request(96) == b"RZ096\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_zone_status_request(5)) == "RZ005"

    @pytest.mark.parametrize("bad", [0, 193, -1, 1000])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError):
            encode_zone_status_request(bad)


# ---------------------------------------------------------------------------
# encode_area_label_request  AL{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodeAreaLabelRequest:
    def test_area_1(self):
        assert encode_area_label_request(1) == b"AL001\r"

    def test_area_8(self):
        assert encode_area_label_request(8) == b"AL008\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_area_label_request(2)) == "AL002"

    @pytest.mark.parametrize("bad", [0, 9, -1])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError):
            encode_area_label_request(bad)


# ---------------------------------------------------------------------------
# encode_zone_label_request  ZL{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodeZoneLabelRequest:
    def test_zone_1(self):
        assert encode_zone_label_request(1) == b"ZL001\r"

    def test_zone_192(self):
        assert encode_zone_label_request(192) == b"ZL192\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_zone_label_request(10)) == "ZL010"

    @pytest.mark.parametrize("bad", [0, 193])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError):
            encode_zone_label_request(bad)


# ---------------------------------------------------------------------------
# encode_user_label_request  UL{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodeUserLabelRequest:
    def test_user_1(self):
        assert encode_user_label_request(1) == b"UL001\r"

    def test_user_999(self):
        assert encode_user_label_request(999) == b"UL999\r"

    def test_user_100(self):
        assert encode_user_label_request(100) == b"UL100\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_user_label_request(42)) == "UL042"

    @pytest.mark.parametrize("bad", [0, 1000, -1])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError):
            encode_user_label_request(bad)


# ---------------------------------------------------------------------------
# encode_arm  AA{nnn}{mode}{code}\r
# ---------------------------------------------------------------------------


class TestEncodeArm:
    # Exact output format
    def test_arm_away_code_1234(self):
        assert encode_arm(1, ARM_MODE_AWAY, "1234") == b"AA001A1234\r"

    def test_arm_force(self):
        assert encode_arm(2, ARM_MODE_FORCE, "1") == b"AA002F1\r"

    def test_arm_stay(self):
        assert encode_arm(3, ARM_MODE_STAY, "123456") == b"AA003S123456\r"

    def test_arm_instant(self):
        assert encode_arm(4, ARM_MODE_INSTANT, "9999") == b"AA004I9999\r"

    # All 4 arm modes produce correct mode char at position 4 (0-indexed)
    @pytest.mark.parametrize("mode,char", [
        (ARM_MODE_AWAY,    "A"),
        (ARM_MODE_FORCE,   "F"),
        (ARM_MODE_STAY,    "S"),
        (ARM_MODE_INSTANT, "I"),
    ])
    def test_all_arm_modes(self, mode, char):
        result = _decode(encode_arm(1, mode, "1234"))
        assert result[5] == char, f"mode char at index 5 should be {char!r}"

    # Echo prefix is always first 5 chars (AA + 3-digit area)
    def test_echo_prefix_area_1(self):
        assert _echo_prefix(encode_arm(1, ARM_MODE_AWAY, "1234")) == "AA001"

    def test_echo_prefix_area_8(self):
        assert _echo_prefix(encode_arm(8, ARM_MODE_INSTANT, "999999")) == "AA008"

    # Code length boundaries: 1-6 digits accepted
    def test_code_length_1(self):
        assert encode_arm(1, ARM_MODE_AWAY, "5") == b"AA001A5\r"

    def test_code_length_6(self):
        assert encode_arm(1, ARM_MODE_AWAY, "123456") == b"AA001A123456\r"

    # Code must be variable-length (not zero-padded to 6)
    def test_code_not_padded(self):
        text = _decode(encode_arm(1, ARM_MODE_AWAY, "5"))
        assert text == "AA001A5"

    # Boundary area numbers
    def test_area_min(self):
        assert encode_arm(1, ARM_MODE_AWAY, "1") == b"AA001A1\r"

    def test_area_max(self):
        assert encode_arm(8, ARM_MODE_AWAY, "1") == b"AA008A1\r"

    # ValueError cases
    @pytest.mark.parametrize("bad_area", [0, 9, -1])
    def test_bad_area_raises(self, bad_area):
        with pytest.raises(ValueError):
            encode_arm(bad_area, ARM_MODE_AWAY, "1234")

    def test_bad_mode_raises(self):
        with pytest.raises(ValueError):
            encode_arm(1, "X", "1234")

    def test_empty_code_raises(self):
        with pytest.raises(ValueError):
            encode_arm(1, ARM_MODE_AWAY, "")

    def test_code_too_long_raises(self):
        with pytest.raises(ValueError):
            encode_arm(1, ARM_MODE_AWAY, "1234567")  # 7 digits

    def test_non_digit_code_raises(self):
        with pytest.raises(ValueError):
            encode_arm(1, ARM_MODE_AWAY, "12ab")

    def test_code_type_error_raises(self):
        with pytest.raises((ValueError, TypeError)):
            encode_arm(1, ARM_MODE_AWAY, 1234)  # type: ignore[arg-type]  # NOSONAR


# ---------------------------------------------------------------------------
# encode_quick_arm  AQ{nnn}{mode}\r
# ---------------------------------------------------------------------------


class TestEncodeQuickArm:
    def test_quick_arm_away(self):
        assert encode_quick_arm(1, ARM_MODE_AWAY) == b"AQ001A\r"

    def test_quick_arm_force(self):
        assert encode_quick_arm(2, ARM_MODE_FORCE) == b"AQ002F\r"

    def test_quick_arm_stay(self):
        assert encode_quick_arm(3, ARM_MODE_STAY) == b"AQ003S\r"

    def test_quick_arm_instant(self):
        assert encode_quick_arm(4, ARM_MODE_INSTANT) == b"AQ004I\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_quick_arm(1, ARM_MODE_AWAY)) == "AQ001"

    def test_area_max(self):
        assert encode_quick_arm(8, ARM_MODE_INSTANT) == b"AQ008I\r"

    @pytest.mark.parametrize("bad_area", [0, 9, -1])
    def test_bad_area_raises(self, bad_area):
        with pytest.raises(ValueError):
            encode_quick_arm(bad_area, ARM_MODE_AWAY)

    def test_bad_mode_raises(self):
        with pytest.raises(ValueError):
            encode_quick_arm(1, "Z")

    # Quick arm has no code — verify no extra chars beyond AQ{nnn}{mode}
    def test_no_extra_chars(self):
        text = _decode(encode_quick_arm(1, ARM_MODE_AWAY))
        assert text == "AQ001A"


# ---------------------------------------------------------------------------
# encode_disarm  AD{nnn}{code}\r
# ---------------------------------------------------------------------------


class TestEncodeDisarm:
    def test_area_1_code_1234(self):
        assert encode_disarm(1, "1234") == b"AD0011234\r"

    def test_area_8_code_999999(self):
        assert encode_disarm(8, "999999") == b"AD008999999\r"

    def test_code_length_1(self):
        assert encode_disarm(1, "5") == b"AD0015\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_disarm(3, "1111")) == "AD003"

    @pytest.mark.parametrize("bad_area", [0, 9])
    def test_bad_area_raises(self, bad_area):
        with pytest.raises(ValueError):
            encode_disarm(bad_area, "1234")

    def test_empty_code_raises(self):
        with pytest.raises(ValueError):
            encode_disarm(1, "")

    def test_code_too_long_raises(self):
        with pytest.raises(ValueError):
            encode_disarm(1, "1234567")

    def test_non_digit_code_raises(self):
        with pytest.raises(ValueError):
            encode_disarm(1, "pass")


# ---------------------------------------------------------------------------
# encode_panic_emergency  PE{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodePanicEmergency:
    def test_area_1(self):
        assert encode_panic_emergency(1) == b"PE001\r"

    def test_area_8(self):
        assert encode_panic_emergency(8) == b"PE008\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_panic_emergency(1)) == "PE001"

    @pytest.mark.parametrize("bad", [0, 9])
    def test_bad_area_raises(self, bad):
        with pytest.raises(ValueError):
            encode_panic_emergency(bad)


# ---------------------------------------------------------------------------
# encode_panic_medical  PM{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodePanicMedical:
    def test_area_1(self):
        assert encode_panic_medical(1) == b"PM001\r"

    def test_area_8(self):
        assert encode_panic_medical(8) == b"PM008\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_panic_medical(2)) == "PM002"

    @pytest.mark.parametrize("bad", [0, 9])
    def test_bad_area_raises(self, bad):
        with pytest.raises(ValueError):
            encode_panic_medical(bad)


# ---------------------------------------------------------------------------
# encode_panic_fire  PF{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodePanicFire:
    def test_area_1(self):
        assert encode_panic_fire(1) == b"PF001\r"

    def test_area_8(self):
        assert encode_panic_fire(8) == b"PF008\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_panic_fire(5)) == "PF005"

    @pytest.mark.parametrize("bad", [0, 9])
    def test_bad_area_raises(self, bad):
        with pytest.raises(ValueError):
            encode_panic_fire(bad)


# ---------------------------------------------------------------------------
# encode_utility_key  UK{nnn}\r
# ---------------------------------------------------------------------------


class TestEncodeUtilityKey:
    def test_key_1(self):
        assert encode_utility_key(1) == b"UK001\r"

    def test_key_251(self):
        assert encode_utility_key(251) == b"UK251\r"

    def test_key_100(self):
        assert encode_utility_key(100) == b"UK100\r"

    def test_echo_prefix(self):
        assert _echo_prefix(encode_utility_key(1)) == "UK001"

    @pytest.mark.parametrize("bad", [0, 252, -1, 1000])
    def test_out_of_range_raises(self, bad):
        with pytest.raises(ValueError):
            encode_utility_key(bad)


# ---------------------------------------------------------------------------
# Cross-cutting: all outputs are bytes, valid ASCII, end with \r
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cmd_bytes", [
    encode_area_status_request(1),
    encode_area_status_request(8),
    encode_zone_status_request(1),
    encode_zone_status_request(192),
    encode_area_label_request(1),
    encode_area_label_request(8),
    encode_zone_label_request(1),
    encode_zone_label_request(192),
    encode_user_label_request(1),
    encode_user_label_request(999),
    encode_arm(1, ARM_MODE_AWAY, "1234"),
    encode_arm(8, ARM_MODE_FORCE, "9"),
    encode_arm(1, ARM_MODE_STAY, "123456"),
    encode_arm(4, ARM_MODE_INSTANT, "0000"),
    encode_quick_arm(1, ARM_MODE_AWAY),
    encode_quick_arm(8, ARM_MODE_INSTANT),
    encode_disarm(1, "1234"),
    encode_disarm(8, "999999"),
    encode_panic_emergency(1),
    encode_panic_medical(1),
    encode_panic_fire(1),
    encode_utility_key(1),
    encode_utility_key(251),
])
def test_all_commands_are_bytes_ascii_cr_terminated(cmd_bytes):
    assert isinstance(cmd_bytes, bytes)
    text = cmd_bytes.decode("ascii")   # raises if not valid ASCII
    assert text.endswith("\r")


# ---------------------------------------------------------------------------
# Echo prefix table: first 5 chars == 2-char verb + 3-digit zero-padded number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cmd_bytes,expected_prefix", [
    (encode_area_status_request(1),         "RA001"),
    (encode_area_status_request(8),         "RA008"),
    (encode_zone_status_request(1),         "RZ001"),
    (encode_zone_status_request(192),       "RZ192"),
    (encode_area_label_request(1),          "AL001"),
    (encode_area_label_request(8),          "AL008"),
    (encode_zone_label_request(1),          "ZL001"),
    (encode_zone_label_request(192),        "ZL192"),
    (encode_user_label_request(1),          "UL001"),
    (encode_user_label_request(999),        "UL999"),
    (encode_arm(1, ARM_MODE_AWAY, "1234"),  "AA001"),
    (encode_arm(8, ARM_MODE_AWAY, "1234"),  "AA008"),
    (encode_quick_arm(1, ARM_MODE_AWAY),    "AQ001"),
    (encode_quick_arm(8, ARM_MODE_STAY),    "AQ008"),
    (encode_disarm(1, "1234"),              "AD001"),
    (encode_disarm(8, "1234"),              "AD008"),
    (encode_panic_emergency(1),             "PE001"),
    (encode_panic_medical(1),              "PM001"),
    (encode_panic_fire(1),                 "PF001"),
    (encode_utility_key(1),               "UK001"),
    (encode_utility_key(251),             "UK251"),
])
def test_echo_prefixes(cmd_bytes, expected_prefix):
    assert _echo_prefix(cmd_bytes) == expected_prefix
