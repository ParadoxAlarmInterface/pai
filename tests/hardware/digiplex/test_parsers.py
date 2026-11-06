"""Golden-frame tests for the Digiplex protocol parsers.

Every frame here was either captured live from a DGP-848 (firmware build
A095, 2026-10) or published in ParadoxAlarmInterface/pai#257 (avilleret,
firmware build A096).
"""

from construct import Bytes
import pytest

from paradox.hardware.digiplex import parsers
from paradox.hardware.digiplex.adapters import (
    StatusAdapter,
    publishes_tamper,
    zone_device_class,
)
from paradox.hardware.digiplex.property import RAMDataParserMap

# --- golden frames -------------------------------------------------------

# INIT / StartCommunication (protokolas.md §7)
GOLDEN_INIT = bytes.fromhex("5F 20 " + "00 " * 34 + "7F")

# StartCommunication response of our DGP-848 (live capture)
GOLDEN_INIT_RESPONSE = bytes.fromhex(
    "00 00 08 10 00 04 13 00 00 00 00 00 06 12 02 A0 95 " + "00 " * 19 + "7E"
)

# The same response from issue #257 (avilleret's DGP-848, fw A096)
GOLDEN_INIT_RESPONSE_257 = bytes.fromhex(
    "00 00 08 10 00 04 14 00 48 17 00 00 06 12 02 A0 96 " + "00 " * 19 + "DF"
)

# LOGIN response (live capture)
GOLDEN_LOGIN_RESPONSE = bytes.fromhex("10 " + "00 " * 35 + "10")

# READ request for RAM 0x8153, 12 bytes (protokolas.md §7)
GOLDEN_READ_REQUEST = bytes.fromhex("56 00 81 53 " + "00 " * 32 + "2A")

# ERROR / busy response (live capture: "session busy")
GOLDEN_ERROR_RESPONSE = bytes.fromhex("70 " + "00 " * 35 + "70")


def _frame(payload: bytes) -> bytes:
    return payload + bytes([sum(payload) % 256])


def test_checksums_of_golden_frames_are_valid():
    for name, frame in {
        "init": GOLDEN_INIT,
        "init_response": GOLDEN_INIT_RESPONSE,
        "init_response_257": GOLDEN_INIT_RESPONSE_257,
        "login_response": GOLDEN_LOGIN_RESPONSE,
        "read_request": GOLDEN_READ_REQUEST,
        "error": GOLDEN_ERROR_RESPONSE,
    }.items():
        assert len(frame) == 37, name
        assert frame[36] == sum(frame[:36]) % 256, name


def test_build_start_communication_matches_golden_init():
    """PAI's StartCommunication with source_id=0 must equal the golden INIT.
    (DGP-848 silently ignores every other source_id - live tested.)"""
    message = parsers.StartCommunication.build(
        dict(fields=dict(value=dict(source_id=0)))
    )
    assert message == GOLDEN_INIT


def test_parse_init_response():
    parsed = parsers.StartCommunicationResponse.parse(GOLDEN_INIT_RESPONSE)
    v = parsed.fields.value
    assert v.po.command == 0
    assert v.product_id == "DIGIPLEX_v13"  # product_id byte is 0x00
    assert v.firmware.version == 4
    assert v.firmware.revision == 13
    assert v.password_hint == b"\x00\x00"
    assert v.firmware_build == 0xA095
    assert parsed.checksum == GOLDEN_INIT_RESPONSE[36:37]


def test_parse_init_response_issue257():
    """Cross-check with the frames published in issue #257."""
    parsed = parsers.StartCommunicationResponse.parse(GOLDEN_INIT_RESPONSE_257)
    v = parsed.fields.value
    assert v.product_id == "DIGIPLEX_v13"
    assert v.password_hint == b"\x48\x17"
    assert v.firmware_build == 0xA096


def test_build_read_ram_matches_golden():
    message = parsers.build_read_ram(0x8153, 12)
    assert message == GOLDEN_READ_REQUEST


def test_build_read_ram_count_encoding():
    # count 32 is encoded as 0; count splits over count_hi/count_lo
    frame = parsers.build_read_ram(0x8000, 32)
    assert frame[0] == 0x50
    assert frame[1] == 0x00
    frame = parsers.build_read_ram(0x8000, 1)
    assert frame[0] == 0x50
    assert frame[1] == 0x80
    with pytest.raises(ValueError):
        parsers.build_read_ram(0x8000, 33)


def test_parse_read_response():
    payload = bytes.fromhex("00 00 01 00 00 00 00 00 00 00 00 00")
    response = _frame(b"\x50\x00\x81\x53" + payload + bytes(20))
    parsed = parsers.ReadRAMResponse.parse(response)
    v = parsed.fields.value
    assert v.po.command == 5
    assert v.address == 0x8153
    assert v.data[:12] == payload


def test_build_login_echoes_init_response():
    """LOGIN = init response echo with the PC password (BCD) at [8..9].
    With password 0000 the frame equals the init response itself."""
    login = parsers.build_login(GOLDEN_INIT_RESPONSE[:36], b"\x00\x00")
    assert login == GOLDEN_INIT_RESPONSE


def test_build_login_other_password():
    login = parsers.build_login(GOLDEN_INIT_RESPONSE[:36], b"\x48\x17")
    assert login[8:10] == b"\x48\x17"
    assert login[:8] == GOLDEN_INIT_RESPONSE[:8]
    assert login[36] == sum(login[:36]) % 256
    assert login != GOLDEN_INIT_RESPONSE


def test_parse_login_response():
    parsed = parsers.InitializeCommunicationResponse.parse(GOLDEN_LOGIN_RESPONSE)
    assert parsed.fields.value.po.command == 1


def test_parse_error_response():
    parsed = parsers.ErrorMessage.parse(GOLDEN_ERROR_RESPONSE)
    assert parsed.fields.value.po.command == 7
    assert parsed.fields.value.message == 0


def test_zone_status_adapter_bits():
    """bit0 (LSB) of the first byte is zone 1 (live capture: zone 17 open)."""
    r = StatusAdapter(Bytes(6))._decode(bytes.fromhex("00 00 01 00 00 00"), None, None)
    assert r[17] is True
    assert all(r[i] is False for i in range(1, 49) if i != 17)


def test_zone_block_parser():
    """Live capture: zones all closed, no tamper."""
    data = bytes(12) + bytes(20)
    parsed = RAMDataParserMap[0x8153].parse(data)
    assert not any(parsed.zone_open.values())
    assert not any(parsed.zone_tamper.values())
    assert len(parsed.zone_open) == 48

    data = bytes.fromhex("00 00 01 00 00 00") + bytes(6) + bytes(20)
    parsed = RAMDataParserMap[0x8153].parse(data)
    assert parsed.zone_open[17] is True


def test_status_block_parser():
    """Live capture: AC=0x53 PSU=0xF2 BATT=0x53.

    Calibrated against a multimeter (2026-10-25): battery 13.68 V (raw 0x53),
    PSU 13.66 V (raw 0xF2); AC shares the battery scale."""
    data = bytes.fromhex("86 F2 53") + bytes(29)
    parsed = RAMDataParserMap[0x800B].parse(data)
    assert parsed.system.power.psu == 13.66
    assert parsed.system.power.battery == 13.68
    # 0x000B (AC sample) is intentionally not published: it is an unfiltered
    # per-sample reading, not the AC input voltage.
    assert "ac" not in parsed.system.power


def _partition_block(
    house_arm: int = 0x00,
    house_status: int = 0x00,
    garage_arm: int = 0x00,
    garage_status: int = 0x00,
) -> bytes:
    """32 byte RAM block read at 0x8185 (0x0185..0x01A4).

    5-byte partition blocks: partition 1 at 0x0195, partition 2 at 0x019A.
    """
    blokas = bytearray(32)
    blokas[0x0195 - 0x0185] = house_arm
    blokas[0x0196 - 0x0185] = house_status
    blokas[0x019A - 0x0185] = garage_arm
    blokas[0x019B - 0x0185] = garage_status
    return bytes(blokas)


@pytest.mark.parametrize(
    ("house_arm", "arm", "perimetras"),
    [
        (0x00, False, False),  # disarmed
        (0x01, True, False),  # armed (full)          -> armed_away
        (0x05, True, True),  # armed + stay          -> armed_home
        (0x03, True, False),  # armed + force arm     -> armed_away
    ],
)
def test_house_arm(house_arm, arm, perimetras):
    parsed = RAMDataParserMap[0x8185].parse(_partition_block(house_arm=house_arm))
    part = parsed.partition_status[1]
    assert part["arm"] is arm
    assert part["arm_stay"] is perimetras


def test_garage_is_partition_two():
    parsed = RAMDataParserMap[0x8185].parse(_partition_block(garage_arm=0x01))
    assert parsed.partition_status[1]["arm"] is False
    assert parsed.partition_status[2]["arm"] is True


def test_partitions_are_independent():
    parsed = RAMDataParserMap[0x8185].parse(
        _partition_block(house_arm=0x05, garage_arm=0x01)
    )
    assert parsed.partition_status[1]["arm"] is True
    assert parsed.partition_status[2]["arm"] is True

    parsed = RAMDataParserMap[0x8185].parse(
        _partition_block(house_arm=0x00, garage_arm=0x01)
    )
    assert parsed.partition_status[1]["arm"] is False
    assert parsed.partition_status[2]["arm"] is True


@pytest.mark.parametrize(
    ("arm_byte", "audible", "silent"),
    [
        (0x01, False, False),
        (0x41, True, False),  # bit6 audible alarm
        (0x21, False, True),  # bit5 silent alarm
    ],
)
def test_alarm_flags(arm_byte, audible, silent):
    parsed = RAMDataParserMap[0x8185].parse(_partition_block(house_arm=arm_byte))
    part = parsed.partition_status[1]
    assert part["audible_alarm"] is audible
    assert part["silent_alarm"] is silent


def test_exit_delay_flag():
    parsed = RAMDataParserMap[0x8185].parse(
        _partition_block(house_arm=0x01, house_status=0x02)
    )
    assert parsed.partition_status[1]["exit_delay"] is True

    parsed = RAMDataParserMap[0x8185].parse(
        _partition_block(house_arm=0x01, house_status=0x00)
    )
    assert parsed.partition_status[1]["exit_delay"] is False


def test_build_partition_action_frame():
    """MONITOR frame: 40 00 | P1:P2 | P3:P4 | P5:P6 | P7:P8, padded to 36."""
    frame = parsers.build_partition_action({1: 0x06})  # disarm partition 1
    assert len(frame) == 37
    assert frame[0] == 0x40
    assert frame[1] == 0x00
    assert frame[2] == 0x60  # partition 1 is the high nibble, P2 (NOP) the low one
    assert frame[3:6] == b"\x00\x00\x00"
    assert sum(frame[:36]) % 256 == frame[36]


def test_build_partition_action_second_partition():
    frame = parsers.build_partition_action({2: 0x03})  # stay arm partition 2
    assert frame[2] == 0x03  # P1 = 0, P2 = 3


def test_build_partition_action_both_partitions():
    frame = parsers.build_partition_action({1: 0x02, 2: 0x06})
    assert frame[2] == 0x26  # P1 = 2 (arm), P2 = 6 (disarm)


def test_partition_action_parser_accepts_the_echo():
    """The panel answers a MONITOR command with an echo of the same frame."""
    frame = parsers.build_partition_action({1: 0x02})
    parsed = parsers.PerformPartitionAction.parse(frame)
    assert parsed.fields.value.po.command == 0x4
    assert parsed.fields.value.partitions == bytes((0x20, 0x00, 0x00, 0x00))


def test_partition_action_command_map():
    assert parsers.PARTITION_ACTION_COMMANDS["arm"] == 0x02
    assert parsers.PARTITION_ACTION_COMMANDS["arm_stay"] == 0x03
    # HA night maps to stay arm: INSTANT_ARM (0x4) is reported by the panel
    # as a full arm, which would show as armed_away instead of armed_home.
    assert parsers.PARTITION_ACTION_COMMANDS["arm_sleep"] == 0x03
    assert parsers.PARTITION_ACTION_COMMANDS["force"] == 0x05
    assert parsers.PARTITION_ACTION_COMMANDS["disarm"] == 0x06
    assert parsers.PARTITION_ACTION_COMMANDS["beep"] == 0x08


def test_entry_delay_flag():
    """Bit2 of the status byte is the entry delay (keypad beeps, code needed)."""
    parsed = RAMDataParserMap[0x8185].parse(
        _partition_block(house_arm=0x05, house_status=0x04)
    )
    assert parsed.partition_status[1]["entry_delay"] is True

    parsed = RAMDataParserMap[0x8185].parse(
        _partition_block(house_arm=0x05, house_status=0x00)
    )
    assert parsed.partition_status[1]["entry_delay"] is False


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("vaiku rytu lang.", "window"),
        ("miegamojo langas", "window"),
        ("vaiku pietu duz.", "vibration"),
        ("svetaines duzis", "vibration"),
        ("garazo vartai", "garage_door"),
        ("fasado durys", "door"),
        ("sirena, deze, tamp", "tamper"),
        ("gaisras", "smoke"),
        ("virtuve", "motion"),
        ("miegamasis", "motion"),
    ],
)
def test_zone_device_class(label, expected):
    assert zone_device_class(label) == expected


@pytest.mark.parametrize(
    ("device_class", "expected"),
    [
        ("motion", True),
        ("vibration", True),
        ("tamper", True),
        ("window", False),
        ("door", False),
        ("garage_door", False),
        ("smoke", False),
    ],
)
def test_publishes_tamper(device_class, expected):
    assert publishes_tamper(device_class) is expected
