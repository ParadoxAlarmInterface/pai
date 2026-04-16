"""
Unit tests for paradox.hardware.prt3.parser.

Coverage:
  - COMM status (ok / fail)
  - Buffer-full sentinel
  - Command echoes (&OK / &fail) — including failed info requests
  - Area status replies — every flag field, every arm state, boundary indices
  - Zone status replies — every flag field, every open state, boundary indices
  - Label replies — zone/area/user, space preservation, boundary indices
  - System events — field extraction, group 0, area 0 (global), area 255
  - Virtual PGM events — on/off, boundary pgm numbers
  - Malformed / unknown / truncated lines → None (never raised)
  - Replay of every fixture line (smoke test)
"""

import pytest

from paradox.hardware.prt3.parser import (
    ARM_AWAY,
    ARM_DISARMED,
    ARM_FORCE,
    ARM_INSTANT,
    ARM_STAY,
    PRT3AreaStatus,
    PRT3BufferFull,
    PRT3CommandEcho,
    PRT3CommStatus,
    PRT3LabelReply,
    PRT3PgmEvent,
    PRT3SystemEvent,
    PRT3ZoneStatus,
    ZONE_CLOSED,
    ZONE_FIRE_LOOP_TROUBLE,
    ZONE_OPEN,
    ZONE_TAMPERED,
    parse_line,
)
from tests.hardware.prt3 import fixtures as fx


# ===========================================================================
# COMM status
# ===========================================================================


def test_comm_ok():
    result = parse_line("COMM&ok")
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is True


def test_comm_fail():
    result = parse_line("COMM&fail")
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is False


def test_comm_ok_from_fixture():
    result = parse_line(fx.COMM_OK)
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is True


def test_comm_fail_from_fixture():
    result = parse_line(fx.COMM_FAIL)
    assert isinstance(result, PRT3CommStatus)
    assert result.ok is False


# ===========================================================================
# Buffer full
# ===========================================================================


def test_buffer_full():
    result = parse_line("!")
    assert isinstance(result, PRT3BufferFull)


def test_buffer_full_from_fixture():
    assert isinstance(parse_line(fx.BUFFER_FULL), PRT3BufferFull)


# ===========================================================================
# Command echoes
# ===========================================================================


@pytest.mark.parametrize(
    "line, expected_cmd",
    [
        ("AA001&OK", "AA001"),   # arm
        ("AQ001&OK", "AQ001"),   # quick arm
        ("AD001&OK", "AD001"),   # disarm
        ("PE001&OK", "PE001"),   # emergency panic
        ("PM001&OK", "PM001"),   # medical panic
        ("PF001&OK", "PF001"),   # fire panic
        ("UK001&OK", "UK001"),   # utility key 1
        ("UK251&OK", "UK251"),   # utility key max
        ("AA008&OK", "AA008"),   # arm area 8
    ],
)
def test_echo_ok(line, expected_cmd):
    result = parse_line(line)
    assert isinstance(result, PRT3CommandEcho)
    assert result.ok is True
    assert result.cmd == expected_cmd


@pytest.mark.parametrize(
    "line, expected_cmd",
    [
        ("AA001&fail", "AA001"),  # arm failed (invalid code)
        ("AD001&fail", "AD001"),  # disarm failed
        ("RA001&fail", "RA001"),  # area status request failed
        ("ZL001&fail", "ZL001"),  # zone label request failed
        ("AL008&fail", "AL008"),  # area label request failed
        ("UL999&fail", "UL999"),  # user label request failed
    ],
)
def test_echo_fail(line, expected_cmd):
    result = parse_line(line)
    assert isinstance(result, PRT3CommandEcho)
    assert result.ok is False
    assert result.cmd == expected_cmd


@pytest.mark.parametrize(
    "line, expected_cmd",
    [
        ("AA001&ok", "AA001"),   # arm — lowercase firmware variant
        ("UK001&ok", "UK001"),   # utility key — observed on live Paradox panel
        ("AD001&ok", "AD001"),   # disarm
    ],
)
def test_echo_ok_lowercase(line, expected_cmd):
    """Some panel firmware sends lowercase '&ok'; parser must accept both cases."""
    result = parse_line(line)
    assert isinstance(result, PRT3CommandEcho)
    assert result.ok is True
    assert result.cmd == expected_cmd


def test_echo_cmd_is_exactly_5_chars():
    result = parse_line("AA001&OK")
    assert len(result.cmd) == 5


@pytest.mark.parametrize("line", [
    fx.ECHO_ARM_OK, fx.ECHO_QUICK_ARM_OK, fx.ECHO_DISARM_OK,
    fx.ECHO_PANIC_EMERG_OK, fx.ECHO_PANIC_MED_OK, fx.ECHO_PANIC_FIRE_OK,
    fx.ECHO_UTILITY_KEY_OK,
    fx.ECHO_ARM_OK_LOWER, fx.ECHO_UTILITY_KEY_OK_LOWER,
])
def test_echo_ok_from_fixtures(line):
    result = parse_line(line)
    assert isinstance(result, PRT3CommandEcho)
    assert result.ok is True


@pytest.mark.parametrize("line", [
    fx.ECHO_ARM_FAIL, fx.ECHO_DISARM_FAIL, fx.ECHO_STATUS_FAIL, fx.ECHO_LABEL_FAIL,
])
def test_echo_fail_from_fixtures(line):
    result = parse_line(line)
    assert isinstance(result, PRT3CommandEcho)
    assert result.ok is False


# ===========================================================================
# Area status
# ===========================================================================


class TestAreaStatus:
    """RA{nnn}{7 flags} replies — 12 chars total."""

    def test_disarmed_all_clear(self):
        # "RA001DOOOOOO": D=disarmed, all secondary flags = O (inactive)
        r = parse_line(fx.AREA_DISARMED)
        assert isinstance(r, PRT3AreaStatus)
        assert r.area == 1
        assert r.arm_state == ARM_DISARMED
        assert r.in_programming is False
        assert r.trouble is False
        assert r.not_ready is False
        assert r.alarm is False
        assert r.strobe is False
        assert r.zone_in_memory is False

    @pytest.mark.parametrize(
        "line, expected_arm_state",
        [
            ("RA001DOOOOOO", ARM_DISARMED),
            ("RA001AOOOOOO", ARM_AWAY),
            ("RA001FOOOOOO", ARM_FORCE),
            ("RA001SOOOOOO", ARM_STAY),
            ("RA001IOOOOOO", ARM_INSTANT),
        ],
    )
    def test_arm_states(self, line, expected_arm_state):
        r = parse_line(line)
        assert isinstance(r, PRT3AreaStatus)
        assert r.arm_state == expected_arm_state

    def test_in_programming_flag_true(self):
        # "RA001DPOOOOO" — P at position 6
        r = parse_line("RA001DPOOOOO")
        assert isinstance(r, PRT3AreaStatus)
        assert r.in_programming is True
        assert r.arm_state == ARM_DISARMED

    def test_in_programming_flag_false(self):
        r = parse_line("RA001DOOOOOO")
        assert r.in_programming is False

    def test_trouble_flag_true(self):
        # "RA001DOTOOOO" — T at position 7
        r = parse_line("RA001DOTOOOO")
        assert isinstance(r, PRT3AreaStatus)
        assert r.trouble is True

    def test_trouble_flag_false(self):
        r = parse_line("RA001DOOOOOO")
        assert r.trouble is False

    def test_not_ready_flag_true(self):
        # "RA001DOONOOO" — N at position 8
        r = parse_line("RA001DOONOOO")
        assert isinstance(r, PRT3AreaStatus)
        assert r.not_ready is True

    def test_not_ready_flag_false(self):
        # O at position 8 means "area IS ready"
        r = parse_line("RA001DOOOOOO")
        assert r.not_ready is False

    def test_alarm_flag_true(self):
        # "RA001AOOOAOO" — A at position 9
        r = parse_line("RA001AOOOAOO")
        assert isinstance(r, PRT3AreaStatus)
        assert r.alarm is True
        assert r.strobe is False

    def test_alarm_flag_false(self):
        r = parse_line("RA001DOOOOOO")
        assert r.alarm is False

    def test_strobe_flag_true(self):
        # "RA001AOOOASO" — A(alarm) at 9, S(strobe) at 10
        r = parse_line("RA001AOOOASO")
        assert isinstance(r, PRT3AreaStatus)
        assert r.alarm is True
        assert r.strobe is True

    def test_zone_in_memory_flag_true(self):
        # "RA001IOOOOOM" — M at position 11
        r = parse_line("RA001IOOOOOM")
        assert isinstance(r, PRT3AreaStatus)
        assert r.arm_state == ARM_INSTANT
        assert r.zone_in_memory is True

    def test_zone_in_memory_flag_false(self):
        r = parse_line("RA001DOOOOOO")
        assert r.zone_in_memory is False

    def test_all_flags_active(self):
        # "RA001APTNASM": away, prog, trouble, not-ready, alarm, strobe, memory
        r = parse_line(fx.AREA_ALL_FLAGS)
        assert isinstance(r, PRT3AreaStatus)
        assert r.area == 1
        assert r.arm_state == ARM_AWAY
        assert r.in_programming is True
        assert r.trouble is True
        assert r.not_ready is True
        assert r.alarm is True
        assert r.strobe is True
        assert r.zone_in_memory is True

    def test_stay_trouble_not_ready(self):
        # "RA003SOTNOOO": stay, no prog, trouble, not-ready
        r = parse_line(fx.AREA_STAY_TROUBLE)
        assert r.area == 3
        assert r.arm_state == ARM_STAY
        assert r.trouble is True
        assert r.not_ready is True
        assert r.alarm is False

    def test_alarm_and_strobe_from_fixture(self):
        # "RA001AOOOASO": away, alarm, strobe
        r = parse_line(fx.AREA_ARMED_ALARM_STROBE)
        assert r.arm_state == ARM_AWAY
        assert r.alarm is True
        assert r.strobe is True

    def test_zone_in_memory_from_fixture(self):
        # "RA008IOOOOOM": instant, zone-in-memory
        r = parse_line(fx.AREA_ARMED_MEMORY)
        assert r.arm_state == ARM_INSTANT
        assert r.zone_in_memory is True
        assert r.area == 8

    def test_area_number_max(self):
        r = parse_line(fx.AREA_MAX_NUMBER)   # "RA008DOOOOOO"
        assert r.area == 8

    @pytest.mark.parametrize("area_num", [1, 4, 8])
    def test_area_number_parsing(self, area_num):
        line = f"RA{area_num:03d}DOOOOOO"
        r = parse_line(line)
        assert isinstance(r, PRT3AreaStatus)
        assert r.area == area_num

    def test_unknown_arm_char_returns_none(self):
        # 'X' is not D/A/F/S/I
        assert parse_line("RA001XOOOOOO") is None

    def test_wrong_length_short_returns_none(self):
        assert parse_line("RA001DOOOOO") is None    # 11 chars

    def test_wrong_length_long_returns_none(self):
        assert parse_line("RA001DOOOOOOO") is None  # 13 chars


# ===========================================================================
# Zone status
# ===========================================================================


class TestZoneStatus:
    """RZ{nnn}{5 flags} replies — 10 chars total."""

    def test_closed_all_clear(self):
        r = parse_line(fx.ZONE_CLOSED_OK)   # "RZ001COOOO"
        assert isinstance(r, PRT3ZoneStatus)
        assert r.zone == 1
        assert r.open_state == ZONE_CLOSED
        assert r.alarm is False
        assert r.fire_alarm is False
        assert r.supervision_trouble is False
        assert r.low_battery is False

    @pytest.mark.parametrize(
        "line, expected_state",
        [
            ("RZ001COOOO", ZONE_CLOSED),
            ("RZ001OOOOO", ZONE_OPEN),
            ("RZ001TOOOO", ZONE_TAMPERED),
            ("RZ001FOOOO", ZONE_FIRE_LOOP_TROUBLE),
        ],
    )
    def test_open_states(self, line, expected_state):
        r = parse_line(line)
        assert isinstance(r, PRT3ZoneStatus)
        assert r.open_state == expected_state

    def test_alarm_flag(self):
        r = parse_line(fx.ZONE_ALARM)   # "RZ005OAOOO"
        assert r.alarm is True
        assert r.fire_alarm is False

    def test_fire_alarm_flag(self):
        r = parse_line(fx.ZONE_FIRE_ALARM)  # "RZ006OOFOO"
        assert r.alarm is False
        assert r.fire_alarm is True

    def test_supervision_flag(self):
        r = parse_line(fx.ZONE_SUPERVISION)  # "RZ007OOOSO"
        assert r.supervision_trouble is True
        assert r.low_battery is False

    def test_low_battery_flag(self):
        r = parse_line(fx.ZONE_LOW_BATTERY)  # "RZ008OOOOL"
        assert r.low_battery is True
        assert r.supervision_trouble is False

    def test_all_flags_active(self):
        r = parse_line(fx.ZONE_ALL_FLAGS)   # "RZ009OAFSL"
        assert r.zone == 9
        assert r.open_state == ZONE_OPEN
        assert r.alarm is True
        assert r.fire_alarm is True
        assert r.supervision_trouble is True
        assert r.low_battery is True

    def test_zone_number_max(self):
        r = parse_line(fx.ZONE_MAX_NUMBER)  # "RZ192COOOO"
        assert r.zone == 192

    @pytest.mark.parametrize("zone_num", [1, 96, 192])
    def test_zone_number_parsing(self, zone_num):
        line = f"RZ{zone_num:03d}COOOO"
        r = parse_line(line)
        assert isinstance(r, PRT3ZoneStatus)
        assert r.zone == zone_num

    def test_unknown_open_state_returns_none(self):
        assert parse_line("RZ001XOOOO") is None

    def test_wrong_length_short_returns_none(self):
        assert parse_line("RZ001COOO") is None   # 9 chars

    def test_wrong_length_long_returns_none(self):
        assert parse_line("RZ001COOOOO") is None  # 11 chars


# ===========================================================================
# Label replies
# ===========================================================================


class TestLabelReply:
    """ZL/AL/UL{nnn}{16-char label} replies — 21 chars total."""

    def test_zone_label(self):
        r = parse_line(fx.ZONE_LABEL_FRONT_DOOR)
        assert isinstance(r, PRT3LabelReply)
        assert r.element_type == "zone"
        assert r.index == 1
        assert r.label == "Front Door      "
        assert len(r.label) == 16

    def test_area_label(self):
        r = parse_line(fx.AREA_LABEL_HOME)
        assert isinstance(r, PRT3LabelReply)
        assert r.element_type == "area"
        assert r.index == 1
        assert r.label == "Home            "

    def test_user_label(self):
        r = parse_line(fx.USER_LABEL_MASTER)
        assert isinstance(r, PRT3LabelReply)
        assert r.element_type == "user"
        assert r.index == 1
        assert r.label == "Master          "

    def test_label_trailing_spaces_preserved(self):
        # The full 16-char label including trailing spaces must not be stripped
        r = parse_line(fx.AREA_LABEL_HOME)
        assert r.label == "Home            "   # 4 chars + 12 spaces

    def test_zone_label_max_index(self):
        r = parse_line(fx.ZONE_LABEL_MAX_ZONE)
        assert r.index == 192

    def test_area_label_max_index(self):
        r = parse_line(fx.AREA_LABEL_MAX_AREA)
        assert r.index == 8

    def test_user_label_max_index(self):
        r = parse_line(fx.USER_LABEL_MAX_USER)
        assert r.index == 999

    def test_label_is_always_16_chars(self):
        for line in [
            fx.ZONE_LABEL_FRONT_DOOR, fx.ZONE_LABEL_BACK_DOOR,
            fx.AREA_LABEL_HOME, fx.USER_LABEL_MASTER,
        ]:
            r = parse_line(line)
            assert len(r.label) == 16, f"label length for {line!r}: {len(r.label)}"

    def test_wrong_length_short_returns_none(self):
        # 20 chars (one too short)
        assert parse_line("ZL001Front Door     ") is None

    def test_wrong_length_long_returns_none(self):
        # 22 chars (one too long)
        assert parse_line("ZL001Front Door       ") is None


# ===========================================================================
# System events
# ===========================================================================


class TestSystemEvent:
    """G{ggg}N{nnn}A{aaa} events — 12 chars."""

    def test_zone_open_event(self):
        r = parse_line(fx.EVENT_ZONE_OPEN)   # G001N005A006
        assert isinstance(r, PRT3SystemEvent)
        assert r.group == 1
        assert r.number == 5
        assert r.area == 6

    def test_zone_ok_event(self):
        r = parse_line(fx.EVENT_ZONE_OK)     # G000N005A006
        assert r.group == 0
        assert r.number == 5
        assert r.area == 6

    def test_global_area_zero(self):
        # area == 0 means all enabled areas (global event)
        r = parse_line(fx.EVENT_TROUBLE_AC)  # G036N001A000
        assert r.area == 0

    def test_area_255_any_area(self):
        # area == 255 means "at least one enabled area" per spec Note 1
        r = parse_line(fx.EVENT_STATUS3_TAMPER)  # G066N004A255
        assert r.area == 255

    def test_all_zero_event(self):
        r = parse_line(fx.EVENT_ALL_ZERO)    # G000N000A000
        assert isinstance(r, PRT3SystemEvent)
        assert r.group == 0
        assert r.number == 0
        assert r.area == 0

    def test_max_values(self):
        r = parse_line(fx.EVENT_MAX_VALUES)  # G066N999A255
        assert r.group == 66
        assert r.number == 999
        assert r.area == 255

    @pytest.mark.parametrize("line, group, number, area", [
        ("G001N005A006",   1,   5,   6),
        ("G010N001A001",  10,   1,   1),
        ("G014N002A002",  14,   2,   2),
        ("G024N003A001",  24,   3,   1),
        ("G048N001A000",  48,   1,   0),
        ("G064N000A001",  64,   0,   1),
        ("G002N012A002",   2,  12,   2),
        ("G025N007A001",  25,   7,   1),
    ])
    def test_event_fields_parametrized(self, line, group, number, area):
        r = parse_line(line)
        assert isinstance(r, PRT3SystemEvent)
        assert r.group == group
        assert r.number == number
        assert r.area == area

    def test_wrong_format_too_short_group(self):
        assert parse_line("G01N005A006") is None    # group only 2 digits

    def test_wrong_format_too_short_number(self):
        assert parse_line("G001N5A006") is None     # number only 1 digit

    def test_wrong_format_too_short_area(self):
        assert parse_line("G001N005A06") is None    # area only 2 digits

    def test_wrong_format_too_long_area(self):
        assert parse_line("G001N005A0060") is None  # area 4 digits


# ===========================================================================
# Virtual PGM events
# ===========================================================================


class TestPgmEvent:
    """PGM{nn}ON/OFF events — v1 scope: parsed but not acted on."""

    def test_pgm_on(self):
        r = parse_line(fx.PGM_01_ON)   # "PGM01ON"
        assert isinstance(r, PRT3PgmEvent)
        assert r.pgm == 1
        assert r.on is True

    def test_pgm_off(self):
        r = parse_line(fx.PGM_01_OFF)  # "PGM01OFF"
        assert isinstance(r, PRT3PgmEvent)
        assert r.pgm == 1
        assert r.on is False

    def test_pgm_max_on(self):
        r = parse_line(fx.PGM_30_ON)   # "PGM30ON"
        assert r.pgm == 30
        assert r.on is True

    def test_pgm_max_off(self):
        r = parse_line(fx.PGM_30_OFF)  # "PGM30OFF"
        assert r.pgm == 30
        assert r.on is False

    @pytest.mark.parametrize("pgm_num", [1, 15, 30])
    def test_pgm_number_range(self, pgm_num):
        on_line  = f"PGM{pgm_num:02d}ON"
        off_line = f"PGM{pgm_num:02d}OFF"
        r_on  = parse_line(on_line)
        r_off = parse_line(off_line)
        assert isinstance(r_on,  PRT3PgmEvent) and r_on.pgm  == pgm_num
        assert isinstance(r_off, PRT3PgmEvent) and r_off.pgm == pgm_num

    def test_pgm_single_digit_returns_none(self):
        # Spec shows 2-digit PGM numbers (01-30); single digit is non-standard
        assert parse_line("PGM1ON") is None

    def test_pgm_three_digit_returns_none(self):
        assert parse_line("PGM001ON") is None


# ===========================================================================
# Malformed / unknown inputs → None (not raised)
# ===========================================================================


class TestMalformedInputs:

    def test_empty_string(self):
        assert parse_line("") is None

    def test_completely_unknown(self):
        assert parse_line("GARBAGE") is None
        assert parse_line("XYZ123") is None

    def test_comm_uppercase_ok_is_unknown(self):
        # 'COMM&OK' (uppercase OK) is not the COMM status message —
        # COMM status uses lowercase 'ok'.  The string is 7 chars and
        # does not match the 8-char echo pattern either.
        assert parse_line("COMM&OK") is None

    def test_area_status_too_short(self):
        assert parse_line("RA001DOOOOO") is None    # 11 chars

    def test_area_status_too_long(self):
        assert parse_line("RA001DOOOOOOO") is None  # 13 chars

    def test_zone_status_too_short(self):
        assert parse_line("RZ001COOO") is None      # 9 chars

    def test_zone_status_too_long(self):
        assert parse_line("RZ001COOOOO") is None    # 11 chars

    def test_label_too_short(self):
        # 20 chars — one below the required 21
        assert parse_line("ZL001Front Door     ") is None

    def test_label_too_long(self):
        # 22 chars — one above 21
        assert parse_line("ZL001Front Door       ") is None

    def test_area_unknown_arm_char(self):
        # 'Z' is not a valid arm-state character
        assert parse_line("RA001ZOOOOOO") is None

    def test_zone_unknown_open_char(self):
        # 'X' is not C/O/T/F
        assert parse_line("RZ001XOOOO") is None

    def test_echo_ok_wrong_length_short(self):
        assert parse_line("AA01&OK") is None    # 7 chars (4-char prefix)

    def test_echo_ok_wrong_length_long(self):
        assert parse_line("AA001 &OK") is None  # 9 chars (extra space)

    def test_echo_fail_truncated(self):
        assert parse_line("AA001&fai") is None  # "&fai" not "&fail"

    def test_echo_fail_extended(self):
        assert parse_line("AA001&fails") is None  # 11 chars


# ===========================================================================
# Fixture replay — every fixture line must parse without exception
# ===========================================================================


@pytest.mark.parametrize("line", fx.ALL_FIXTURES, ids=fx.ALL_FIXTURES)
def test_all_fixtures_parse_without_exception(line):
    """Each fixture line must parse without raising; none should return None."""
    result = parse_line(line)
    assert result is not None, f"parse_line({line!r}) unexpectedly returned None"


# ===========================================================================
# Public API / type hierarchy
# ===========================================================================


def test_all_message_types_importable():
    from paradox.hardware.prt3.parser import (  # noqa: F401
        PRT3AreaStatus,
        PRT3BufferFull,
        PRT3CommandEcho,
        PRT3CommStatus,
        PRT3LabelReply,
        PRT3Message,
        PRT3PgmEvent,
        PRT3SystemEvent,
        PRT3ZoneStatus,
    )


def test_arm_state_constants_are_distinct():
    states = [ARM_DISARMED, ARM_AWAY, ARM_FORCE, ARM_STAY, ARM_INSTANT]
    assert len(set(states)) == 5


def test_zone_open_state_constants_are_distinct():
    states = [ZONE_CLOSED, ZONE_OPEN, ZONE_TAMPERED, ZONE_FIRE_LOOP_TROUBLE]
    assert len(set(states)) == 4
