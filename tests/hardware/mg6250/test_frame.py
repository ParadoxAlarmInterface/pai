import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock

from construct import Container
import pytest

from paradox.config import config as cfg
from paradox.connections.serial.encryption import make_serial_key
from paradox.exceptions import AuthenticationFailed, StatusRequestException
from paradox.hardware.mg6250.panel import (
    ACK_GAP,
    AREA_FIELD_LABEL,
    CLOCK_FIELD_DATE,
    CLOCK_FIELD_POWER,
    CMD_DATA,
    CMD_IDENTIFY,
    FIELD_LABEL,
    FIELD_SERIAL,
    KIND_ACK,
    KIND_DATA,
    LAST_FRAGMENT,
    OBJ_AREA,
    OBJ_CLOCK,
    OBJ_PARTITION_STATUS,
    OBJ_SYSTEM,
    OBJ_USER,
    OBJ_ZONE,
    OBJ_ZONE_STATUS,
    PARTITION_ACTIONS,
    PARTITION_STATUS_FIELD,
    SERVICE_CONTROL,
    SERVICE_OBJECTS,
    SYSTEM_FIELD_STATUS,
    ZONE_ALARM_MEMORY,
    ZONE_IN_ALARM,
    ZONE_STATUS_FIELD,
    Frame,
    LoginResponse,
    Panel,
    PanelAckHandler,
    build_frame,
    build_pw_block,
    build_read_record,
    credential_block,
    decode_date,
    parse_records,
)
from paradox.lib.crypto import encrypt as paradox_encrypt
from paradox.lib.handlers import HandlerRegistry
from paradox.paradox import Paradox
from paradox.parsers.status import convert_raw_status

IDENTIFY = bytes.fromhex("de00000a00000001951a")


@pytest.mark.parametrize(
    "password, raw",
    [
        ("admin", b"admin"),
        (b"admin", b"admin"),
        (123, b"0123"),
        (0, b"0000"),
        ("\u00e9", b"\xc3\xa9"),
    ],
)
def test_password_block_uses_normalized_bytes(password, raw):
    block = build_pw_block(password)
    assert block[11] == len(raw)
    assert block[12:44] == credential_block(raw)


@pytest.mark.parametrize("password", [None, "", b"", "a" * 256])
async def test_invalid_password_fails_before_identify(password):
    core = AsyncMock()
    panel = Panel(core)
    with pytest.raises(AuthenticationFailed, match="PASSWORD"):
        await panel.initialize_communication(password)
    core.send_wait.assert_not_awaited()


async def test_login_uses_configured_username(monkeypatch):
    monkeypatch.setattr(cfg, "MG6250_USERNAME", "installer")
    core = AsyncMock()
    core.send_wait.side_effect = [None, None, None]
    panel = Panel(core)
    assert await panel.initialize_communication("admin") is False
    login = Frame.parse(core.send_wait.call_args.kwargs["message"]).fields.value
    assert login.payload == build_pw_block("admin") + b"\x09installer"


def test_build_matches_capture():
    assert build_frame(CMD_IDENTIFY, 1) == IDENTIFY


def test_parse_capture():
    fields = Frame.parse(IDENTIFY).fields.value
    assert fields.command == CMD_IDENTIFY
    assert fields.length == len(IDENTIFY)
    assert fields.session_id == 1
    assert fields.payload == b""


def test_round_trip_over_255_bytes():
    payload = bytes(range(256)) * 2
    raw = build_frame(CMD_DATA, 7, payload)
    assert int.from_bytes(raw[3:5], "little") == len(raw) > 0xFF
    fields = Frame.parse(raw).fields.value
    assert (fields.command, fields.session_id, fields.payload) == (CMD_DATA, 7, payload)


def test_data_frame_carries_login_selector():
    panel = Panel.__new__(Panel)
    panel.session = LoginResponse.parse(bytes([0x08, 0x26]) + bytes(39))
    raw = panel.build_data_frame(b"\xaa")
    fields = Frame.parse(raw).fields.value
    assert (fields.command, fields.session_id, fields.payload) == (
        CMD_DATA,
        0x08,
        b"\x26\xaa",
    )
    assert raw[7:9] == bytes.fromhex("0826")  # as in every captured 0x24 frame


def test_data_frame_needs_login():
    panel = Panel.__new__(Panel)
    panel.session = None
    with pytest.raises(RuntimeError):
        panel.build_data_frame(b"")


# success.pcapng: accepted login of admin/admin
LOGIN_REPLY = bytes.fromhex(
    "de01003a00000002007fed6b10ac84fdb756fc3afeaa06592f7fd7e322e899caa93a"
    "572696c39099f728fbc7ea9d344dc559588b81f6c3f44c2c"
)


async def test_login_registers_panel_ack_handler_once():
    core = AsyncMock()
    core.connection = MagicMock()
    core.connection.handler_registry = HandlerRegistry()
    panel = Panel(core)
    for _ in range(2):
        core.send_wait.side_effect = [None, None, Frame.parse(LOGIN_REPLY)]
        assert await panel.initialize_communication("admin") is True
    assert len(core.connection.handler_registry) == 1


def test_decrypt_captured_data_frame():
    data = bytes.fromhex("de24001c00000008264227190a2630a77cfe2d4cb9948713db00e09e")
    panel = Panel.__new__(Panel)
    panel.session = Panel._decrypt_login_reply(
        bytes(Frame.parse(LOGIN_REPLY).fields.value.payload), make_serial_key("admin")
    )
    panel.session_key = panel.session.session_key
    assert (panel.session.selector, panel.session.mode) == (0x08, 0x26)

    header, body = panel.decrypt_data(bytes(Frame.parse(data).fields.value.payload))
    assert (header.tid, header.fragment, header.kind, header.service) == (
        0x01,
        0x8001,
        KIND_ACK,
        SERVICE_OBJECTS,
    )
    assert (header.selector, header.mode) == (0x08, 0x26)
    assert body is None


# set_time.pcapng: session selector b4, mode 62
SET_TIME_KEY = bytes.fromhex("31b9ea2896e0916c596112208ee87914")
# read 0x1c/1 field 0 and 0x24/1 fields 0-3
SET_TIME_REQUEST = bytes.fromhex(
    "de24003d000000b46208f54df8bdde00fcbe995193fae6e5c101089309a9cb8fab483e7a"
    "abc1a02cb3daaabf8ac64a6568253ca1a1706f62a8cd4a6b6b"
)
SET_TIME_REPLY = bytes.fromhex(
    "de24007d000000b462b253dc7716921796740bed95a81100a9010ca51de56b5ca5f9aa76"
    "06d9f4753f066291ab68e298a8e007892e7964e97b1fd4456fcd66111758aa8b4be67c85"
    "9aaa0d2794a89120ed862344bd4a064430841ba2dfccc8febe8d83a87f71e842d0114b8c"
    "fd320847262138d373be8d4c4fc9d0cc97"
)
SET_TIME_ACK = bytes.fromhex("de24001c000000b46262c168379cd3e03adb2962e7dbc0fffe00ec77")

# zones_users.pcapng: session selector 3e, mode 00; reply to a zone read.
# Labels and RF serials replaced (re-encrypted with the session key).
ZONES_KEY = bytes.fromhex("b8fa7d69d529e4f190d29550be402140")
ZONES_REPLY = bytes.fromhex(
    "de2400ed0000003e0056d02a88f4341cfbe0701c6965f0138801017aacd8aac992f5f7f7"
    "a4320bca29b709f6424f98dbd4c6346c1228d365a4bd9c19331301996badca410aebb81f"
    "69f320f683768c3f5292caf38b183dfa8972d68b955e531bbdc89c90f42644a650a3182c"
    "9f3fca2b4e762e4c1c234a69707597bb36203e49775274316f490b81c775ac33bcd39140"
    "cb7470c5987a18b74c28f5c2f18a021a4f0589fbd93cfc6c80fab009ad82a99e57042129"
    "d3dce3235cc7c16e191a90f7ac633671adf618bfc12b830a7d79ad8a6c7c51e8106b3a21"
    "425e81f780395a19fcf732c9146a416626887bce0d"
)


def session_panel(selector, mode, key, core=None):
    panel = Panel(core or AsyncMock())
    panel.session = Container(selector=selector, mode=mode)
    panel.session_key = key
    return panel


def payload(frame):
    return bytes(Frame.parse(frame).fields.value.payload)


def test_build_request_matches_capture():
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY)
    data = build_read_record(0x1C, 1, [0]) + build_read_record(
        OBJ_CLOCK, 1, [0, 1, 2, 3]
    )
    assert panel.build_request(1, SERVICE_OBJECTS, data) == SET_TIME_REQUEST


def test_build_ack_matches_capture():
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY)
    assert panel.build_ack(1, LAST_FRAGMENT | 1, SERVICE_OBJECTS) == SET_TIME_ACK


def test_parse_captured_clock_reply():
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY)
    header, data = panel.decrypt_data(payload(SET_TIME_REPLY))
    assert (header.tid, header.fragment, header.kind) == (1, 0x8001, KIND_DATA)
    clock = [r for r in parse_records(data) if r.obj == OBJ_CLOCK]
    assert len(clock) == 1
    assert clock[0].index == 1
    assert sorted(clock[0].fields) == [0, 1, 2, 3]
    date = decode_date(clock[0].fields[CLOCK_FIELD_DATE])
    assert date == datetime.datetime(2026, 10, 9, 20, 37)


def test_parse_captured_zone_labels():
    panel = session_panel(0x3E, 0x00, ZONES_KEY)
    _, data = panel.decrypt_data(payload(ZONES_REPLY))
    zones = {r.index: r.fields for r in parse_records(data) if r.obj == OBJ_ZONE}
    assert Panel.decode_label(zones[1][FIELD_LABEL]) == "Zone 1"
    assert Panel.decode_label(zones[2][FIELD_LABEL]) == "Zone 2"
    assert zones[1][FIELD_SERIAL] == bytes.fromhex("102030018700")


def test_parse_records_stops_at_padding():
    record = bytes.fromhex("000e0001000200000100000241420000")
    (parsed,) = parse_records(record[:14] + b"\xee" * 6)
    assert (parsed.obj, parsed.index, parsed.fields) == (1, 2, {1: b"AB"})


@pytest.mark.parametrize(
    "raw",
    [
        "000e0001000200000100000241",  # truncated record
        "000d0001000200000100000241",  # truncated field within complete record
        "000e000100020001010000024142",  # record error status
        "000e000100020000010100024142",  # field error status
        "000e00010002000001000002414201",  # junk after valid record
        "000e0001000200000100000241420000",  # more than one terminator
    ],
)
def test_parse_records_rejects_malformed_or_failed_reads(raw):
    with pytest.raises(StatusRequestException, match="record reply"):
        parse_records(bytes.fromhex(raw))


@pytest.mark.parametrize("padding", [b"", b"\xee" * 6, b"\x00", b"\x00" + b"\xee" * 5])
def test_parse_records_preserves_field_ending_in_padding_byte(padding):
    (record,) = parse_records(bytes.fromhex("000e0001000200000100000241ee") + padding)
    assert record.fields == {1: b"A\xee"}


async def test_read_records_merges_fields_across_fragments():
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY)
    panel.transact = AsyncMock(
        return_value=[
            bytes.fromhex("000e000100020000010000024142") + b"\xee" * 2,
            bytes.fromhex("000d0001000200000000000100") + b"\xee" * 3,
        ]
    )
    assert await panel.read_records([(OBJ_ZONE, 2, [0, 1])]) == {
        (OBJ_ZONE, 2): {0: b"\x00", 1: b"AB"}
    }


async def test_transact_acks_last_fragment():
    core = AsyncMock()
    core.connection = MagicMock()
    core.send_wait.return_value = Frame.parse(SET_TIME_REPLY)
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY, core)

    (fragment,) = await panel.transact(SERVICE_OBJECTS, b"")

    assert {r.obj for r in parse_records(fragment)} == {0x1C, OBJ_CLOCK}
    check = core.send_wait.call_args.kwargs["reply_expected"]
    assert check(Frame.parse(SET_TIME_REPLY))
    assert not check(Frame.parse(SET_TIME_ACK))  # the panel's ack is skipped
    core.connection.write.assert_called_once_with(SET_TIME_ACK)


async def test_transact_pauses_after_last_ack():
    core = AsyncMock()
    core.connection = MagicMock()
    core.send_wait.return_value = Frame.parse(SET_TIME_REPLY)
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY, core)

    loop = asyncio.get_running_loop()
    start = loop.time()
    await panel.transact(SERVICE_OBJECTS, b"")
    assert loop.time() - start >= ACK_GAP


@pytest.mark.parametrize("fragment_count", [1, 2])
async def test_transact_serializes_fragments_and_ack_gap(fragment_count):
    core = Paradox()
    core._connection = MagicMock(connected=True)
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY, core)
    writes = []
    loop = asyncio.get_running_loop()
    core.connection.write.side_effect = lambda raw: writes.append((loop.time(), raw))

    async def wait_for_message(check, timeout):
        header, _ = panel.decrypt_data(payload(writes[-1][1]))
        await asyncio.sleep(0)  # let the other transaction queue behind send_wait
        fragment = 1 if header.kind == KIND_DATA else header.fragment + 1
        if header.tid != 1 or fragment == fragment_count:
            fragment |= LAST_FRAGMENT
        reply = Frame.parse(
            panel.build_data_frame(
                panel._encrypted_header(header.tid, fragment, KIND_DATA, header.service)
                + b"\x01\x00"
                + paradox_encrypt(bytes(16), panel.session_key)
            )
        )
        assert check(reply)
        return reply

    core.connection.wait_for_message = AsyncMock(side_effect=wait_for_message)
    await asyncio.wait_for(
        asyncio.gather(
            panel.transact(SERVICE_OBJECTS, b""),
            panel.transact(SERVICE_CONTROL, b""),
        ),
        timeout=2,
    )

    headers = [panel.decrypt_data(payload(raw))[0] for _, raw in writes]
    assert [header.tid for header in headers] == [1] * (fragment_count + 1) + [2, 2]
    assert writes[-2][0] - writes[-3][0] >= ACK_GAP


def test_panel_ack_handler_takes_only_acks():
    handler = PanelAckHandler(session_panel(0xB4, 0x62, SET_TIME_KEY))
    assert handler.can_handle(Frame.parse(SET_TIME_ACK))
    assert not handler.can_handle(Frame.parse(SET_TIME_REPLY))
    assert not handler.can_handle(Frame.parse(IDENTIFY))
    assert not PanelAckHandler(Panel(AsyncMock())).can_handle(
        Frame.parse(SET_TIME_ACK)
    )  # no session key yet


async def test_transact_without_reply_raises():
    core = AsyncMock()
    core.send_wait.return_value = None
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY, core)
    with pytest.raises(StatusRequestException):
        await panel.transact(SERVICE_OBJECTS, b"")


# zone status capture: session selector 94, mode 42; zone 6 open
STATUS_KEY = bytes.fromhex("7abcbf6fdb5b1ea322646767d363868b")
SYSTEM_REPLY = bytes.fromhex(
    "de24005d0000009442d35f3479deed8a57db700cc502130bc7010b0fd01424ba70890235"
    "306f3dfd04b140935d56d40028a270bdd97539270918cf83c60e4702a6d27c9e02db3d29"
    "ff5fbe16c4d99f46a3de133c3ee68e4e9aa80623f2"
)
ZONE_STATUS_REPLY = bytes.fromhex(
    "de2400fd00000094421682cfa0a97e8eb845283cabf5e18e0a010e87fd5df1305d44c919"
    "d578d67e8a344e926aeabfd43add019c884b4b1e341ca267d6aee4cb4d95385761d61317"
    "5b99a6dd89474f667a762ddc5c503879936356961ab2b1753624cc0d75c5122a652ee4c9"
    "881969f19c0aba14d03197e46a42ab99ed9fef1bdd3a2778d0394b4005ce5d22b355abe1"
    "ad39ee3fbee016153740ee97cbc837437ee5b7823d3789b24c88b070db81cd1e6862997a"
    "557770b8b385076cba054ee005c2d1dc5da71fd016434614f882b42118760284b25daf6c"
    "4b3c1516ced51ee0afd7539aee64118bc6e16a8e295e6ff4e0063167fd50af971969fb82c0"
)


def test_parse_captured_change_counter():
    panel = session_panel(0x94, 0x42, STATUS_KEY)
    _, data = panel.decrypt_data(payload(SYSTEM_REPLY))
    (record,) = parse_records(data)
    assert (record.obj, record.index) == (OBJ_SYSTEM, 1)
    assert record.fields[SYSTEM_FIELD_STATUS][0] == 0x0F


def test_parse_captured_zone_status():
    panel = session_panel(0x94, 0x42, STATUS_KEY)
    _, data = panel.decrypt_data(payload(ZONE_STATUS_REPLY))
    status = {
        r.index: r.fields[ZONE_STATUS_FIELD]
        for r in parse_records(data)
        if r.obj == OBJ_ZONE_STATUS
    }
    assert sorted(status) == list(range(1, 15))
    assert {i for i, v in status.items() if v[0]} == {6}


# alarm-ir-etage capture: session selector 1e, mode e0; armed, then zone 15
# (IR ETAGE) triggered the alarm
ALARM_KEY = bytes.fromhex("b8fa7da91569a431d01295d03e80e100")
ALARM_ZONE_STATUS_REPLY = bytes.fromhex(  # zone status #15-23
    "de2400ad0000001ee00237d5d81f749c4f58dc7259462a1b4e01098d850d62e91d872605"
    "5f7b8d664cf275324c5e9c5fd8b06af212eb48e5e370c4023ff4562c838f6c4c1134c22b"
    "d8f4d9507edf9b427790cb893dfe3c90099efaff213af4a5ea6723892eec811def8cf1b7"
    "5fc06cc5d09bd0d89366a824cf24ae65b7505f87e6ac9d8b19fb3525d1ef566797739aad"
    "41a537b0120f13133f96bdaefbd6d70a986d65c09098fb802b7a5e8fb3"
)
ALARM_PARTITION_STATUS_REPLY = bytes.fromhex(  # zone status #61-64, partition #1-2
    "de24007d0000001ee09d742575fa68a75a22063628718a3b8301002fec7cb892fda88021"
    "2a8ebca0a3140a0a4bbf1939f7ef89b1f9520637175060b8f3895e048c9749f59227d5e3"
    "4e257789de2e48719f1b9b90a158edac66938e63893791c55357645fbba393f5fd659017"
    "4da1398068a2fd0f32806be21772d817de"
)


def test_parse_captured_alarm():
    panel = session_panel(0x1E, 0xE0, ALARM_KEY)
    records = []
    for frame in (ALARM_ZONE_STATUS_REPLY, ALARM_PARTITION_STATUS_REPLY):
        _, data = panel.decrypt_data(payload(frame))
        records += parse_records(data)
    status = {(r.obj, r.index): r.fields for r in records}

    zones = {
        i: f[ZONE_STATUS_FIELD] for (o, i), f in status.items() if o == OBJ_ZONE_STATUS
    }
    assert {i for i, v in zones.items() if v[1] & ZONE_IN_ALARM} == {15}
    # byte 0 is 04 here, not the 01 of an open zone while disarmed
    assert zones[15][:2] == bytes([4, ZONE_IN_ALARM | ZONE_ALARM_MEMORY])
    assert status[(OBJ_PARTITION_STATUS, 1)][PARTITION_STATUS_FIELD] == bytes.fromhex(
        "770240000000"
    )
    assert status[(OBJ_PARTITION_STATUS, 2)][PARTITION_STATUS_FIELD] == bytes(6)


def status_reads(counters, zones=None, partition=bytes(6)):
    """read_records side effect: object 0x1c with each counter in turn.

    Zone status defaults to zone 6 open, all zones in exit delay (0x04).
    """
    replies = iter(counters)
    zones = zones or {}

    async def read_records(requests):
        requests = list(requests)
        if requests[0][0] != OBJ_SYSTEM:
            return {
                (obj, i): (
                    {ZONE_STATUS_FIELD: zones.get(i, bytes([i == 6, 4, 0]))}
                    if obj == OBJ_ZONE_STATUS
                    else {PARTITION_STATUS_FIELD: partition}
                )
                for obj, i, _ in requests
            }
        return {
            (OBJ_SYSTEM, 1): {SYSTEM_FIELD_STATUS: bytes([next(replies)]) + bytes(7)},
            (OBJ_CLOCK, 1): {
                CLOCK_FIELD_DATE: bytes([20, 26, 10, 25, 14, 5]),
                CLOCK_FIELD_POWER: bytes.fromhex("42000c"),  # BabyWare: 5.3 V, AC 0.0
            },
        }

    return AsyncMock(side_effect=read_records)


async def test_request_status_reports_clock_and_zones():
    panel = session_panel(0x94, 0x42, STATUS_KEY)
    panel._zones = [1, 6]
    panel.read_records = status_reads([15])

    status = await panel.request_status(OBJ_CLOCK)

    assert status.system.date.time == datetime.datetime(2026, 10, 25, 14, 5)
    assert status.zone_open == {1: False, 6: True}
    assert (status.system.power.battery, status.system.power.ac) == (5.3, 0.0)
    converted = convert_raw_status(status)
    assert converted["zone"][6] == {
        "open": True,
        "presently_in_alarm": False,
        "generated_alarm": False,
    }
    assert converted["system"]["power"] == {"battery": 5.3, "ac": 0.0}


@pytest.mark.parametrize(
    "raw, expected",
    [
        # partition #1 at each poll of alarm-ir-etage
        ("000000000000", (False, False, False)),
        ("030001000000", (False, True, False)),
        ("070000000000", (True, False, False)),
        ("770240000000", (True, False, True)),
    ],
)
async def test_request_status_reports_partition(raw, expected):
    panel = session_panel(0x1E, 0xE0, ALARM_KEY)
    panel._zones = [15]
    panel.read_records = status_reads([2], partition=bytes.fromhex(raw))

    converted = convert_raw_status(await panel.request_status(OBJ_CLOCK))

    partition = converted["partition"][1]
    assert (
        partition["arm"],
        partition["exit_delay"],
        partition["audible_alarm"],
    ) == expected


async def test_request_status_reports_zone_alarm():
    panel = session_panel(0x1E, 0xE0, ALARM_KEY)
    panel._zones = [14, 15]
    panel.read_records = status_reads(
        [4],
        # 15 in alarm (alarm-ir-etage); 14 closed with alarm memory (set-sms)
        zones={14: bytes.fromhex("002000"), 15: bytes.fromhex("043000")},
    )

    converted = convert_raw_status(await panel.request_status(OBJ_CLOCK))

    assert converted["zone"][15] == {
        "open": True,
        "presently_in_alarm": True,
        "generated_alarm": True,
    }
    assert converted["zone"][14] == {
        "open": False,
        "presently_in_alarm": False,
        "generated_alarm": True,
    }


async def test_request_status_reads_zones_only_when_counter_changes():
    panel = session_panel(0x94, 0x42, STATUS_KEY)
    panel._zones = [6]
    panel.read_records = status_reads([15, 15, 16])

    for _ in range(3):
        status = await panel.request_status(OBJ_CLOCK)
        assert status.zone_open == {6: True}

    zone_reads = [
        c
        for c in panel.read_records.await_args_list
        if list(c.args[0])[0][0] == OBJ_ZONE_STATUS
    ]
    assert len(zone_reads) == 2  # first poll, then counter 15 -> 16


async def test_request_status_without_counter_raises():
    panel = session_panel(0x94, 0x42, STATUS_KEY)
    panel.read_records = AsyncMock(return_value={})
    with pytest.raises(StatusRequestException):
        await panel.request_status(OBJ_CLOCK)


@pytest.mark.parametrize(
    "obj, index, fields",
    [
        (OBJ_ZONE_STATUS, 6, None),
        (OBJ_ZONE_STATUS, 6, {}),
        (OBJ_ZONE_STATUS, 6, {ZONE_STATUS_FIELD: b""}),
        (OBJ_ZONE_STATUS, 6, {ZONE_STATUS_FIELD: b"\x04"}),
        (OBJ_PARTITION_STATUS, 1, None),
        (OBJ_PARTITION_STATUS, 1, {}),
        (OBJ_PARTITION_STATUS, 1, {PARTITION_STATUS_FIELD: b""}),
        (OBJ_PARTITION_STATUS, 1, {PARTITION_STATUS_FIELD: b"\x77"}),
        (OBJ_PARTITION_STATUS, 1, {PARTITION_STATUS_FIELD: b"\x77\x02"}),
    ],
)
async def test_incomplete_status_preserves_snapshot_and_retries(obj, index, fields):
    panel = session_panel(0x94, 0x42, STATUS_KEY)
    panel._zones = [1, 6]
    read_records = status_reads(
        [1, 2, 2],
        zones={6: b"\x04\x30\x00"},
        partition=bytes.fromhex("770240000000"),
    )
    panel.read_records = read_records
    expected = await panel.request_status(0)
    old_zones = panel._zone_status
    old_partitions = panel._partition_status

    async def incomplete_read(requests):
        records = await read_records(requests)
        if (obj, index) in records:
            if fields is None:
                del records[obj, index]
            else:
                records[obj, index] = fields
        return records

    panel.read_records = AsyncMock(side_effect=incomplete_read)
    with pytest.raises(StatusRequestException, match="status reply"):
        await panel.request_status(0)
    assert panel._zone_status is old_zones
    assert panel._partition_status is old_partitions
    assert panel._change_counter == 1

    panel.read_records = read_records
    assert await panel.request_status(0) == expected
    assert panel._change_counter == 2
    assert read_records.await_count == 6


async def test_request_status_without_enrolled_zones():
    panel = session_panel(0x94, 0x42, STATUS_KEY)
    panel.read_records = status_reads([1])
    status = await panel.request_status(0)
    assert status.zone_open == {}
    assert status.partition_arm == {1: False}


async def test_load_labels_skips_empty_slots(monkeypatch):
    monkeypatch.setattr(cfg, "LIMITS", {"zone": [1, 2]})
    panel = session_panel(0x3E, 0x00, ZONES_KEY)

    async def read_objects(obj, indexes, fields):
        if obj == OBJ_USER:
            assert list(fields) == [FIELD_LABEL]
            return {1: {FIELD_LABEL: b"System Master".ljust(16)}}
        if obj == OBJ_AREA:
            assert (list(indexes), list(fields)) == ([1], [AREA_FIELD_LABEL])
            return {1: {AREA_FIELD_LABEL: b"Maison".ljust(16)}}
        assert list(fields) == [FIELD_SERIAL, FIELD_LABEL]
        if obj != OBJ_ZONE:
            return {1: {FIELD_SERIAL: bytes(6), FIELD_LABEL: b"Keypad 1".ljust(16)}}
        return {
            1: {  # device 1020 (made up), Instant (Sleep / Full Arm), partition 1
                FIELD_SERIAL: bytes.fromhex("102009018700"),
                FIELD_LABEL: b"Zone 1".ljust(16),
            },
            # empty zone as read in change-zone: only partition and options set
            2: {
                FIELD_SERIAL: bytes.fromhex("000000018700"),
                FIELD_LABEL: b"Zone 2".ljust(16),
            },
        }

    panel.read_objects = read_objects
    labels = await panel.load_labels()
    assert labels["zone"] == {
        1: {
            "id": 1,
            "key": "Zone_1",
            "label": "Zone 1",
        }
    }
    assert labels["keypad"] == {}
    assert panel._zones == [1]  # status polls enrolled zones only
    assert labels["user"] == {
        1: {"id": 1, "key": "System_Master", "label": "System Master"}
    }
    assert labels["partition"] == {1: {"id": 1, "key": "Maison", "label": "Maison"}}


async def test_load_labels_names_partition_without_area_label(monkeypatch):
    monkeypatch.setattr(cfg, "LIMITS", {})
    panel = session_panel(0x3E, 0x00, ZONES_KEY)

    async def read_objects(obj, indexes, fields):
        if obj == OBJ_ZONE:
            return {index: {FIELD_SERIAL: bytes(6)} for index in indexes}
        return {}

    panel.read_objects = read_objects
    labels = await panel.load_labels()
    assert labels["zone"] == {}
    assert panel._zones == []
    assert labels["user"] == {}
    assert labels["partition"] == {
        1: {"id": 1, "key": "Partition_1", "label": "Partition 1"}
    }


@pytest.mark.parametrize(
    "fields",
    [None, {}, {FIELD_SERIAL: b""}, {FIELD_SERIAL: b"\x10\x20"}],
)
async def test_load_labels_rejects_incomplete_enrollment(monkeypatch, fields):
    monkeypatch.setattr(cfg, "LIMITS", {"zone": [1, 6]})
    panel = session_panel(0x3E, 0x00, ZONES_KEY)
    panel._zones = [1, 6]
    objects = {
        1: {FIELD_SERIAL: bytes.fromhex("102009018700")},
        6: {FIELD_SERIAL: bytes.fromhex("102009018700")},
    }

    async def read_objects(obj, indexes, requested_fields):
        return objects if obj == OBJ_ZONE else {}

    panel.read_objects = read_objects
    valid_zone = objects.pop(6)
    if fields is not None:
        objects[6] = fields
    with pytest.raises(StatusRequestException, match="enrollment reply for zone 6"):
        await panel.load_labels()
    assert panel._zones == [1, 6]

    objects[6] = valid_zone
    labels = await panel.load_labels()
    assert sorted(labels["zone"]) == panel._zones == [1, 6]


# arm-full-09.pcapng (same session as the zone status capture): arm request and its reply,
# panel serial replaced by 01020304 (re-encrypted with the session key)
ARM_REQUEST = bytes.fromhex(
    "de24003d0000009442083bcd133cd3653f651dcecb7ef3179d010ec93f5362cb287036ac"
    "d10a1b7c3c10b53c477296496ce173927633ebdc4f71715012"
)
ARM_REPLY = bytes.fromhex(
    "de24002d000000944206d6e50f3e571243ff731b49f2421d4d01039872639bf518de5394"
    "39f60b6ad7e228c38b"
)
# first identify reply (arm-sleep-09.pcapng): first 8 bytes and model kept,
# serial replaced by 01020304, other bytes zeroed
IDENTIFY_REPLY = bytes.fromhex(
    "de00004000000001b1006400000000000102030400000000000000000000000000000000"
    "00000000000000004d47363235300000000000000000000000003728"
)
PANEL_SERIAL = bytes.fromhex("01020304")


def control_panel():
    core = AsyncMock()
    core.connection = MagicMock()
    core.send_wait.return_value = Frame.parse(ARM_REPLY)
    panel = session_panel(0x94, 0x42, STATUS_KEY, core)
    panel.panel_serial = PANEL_SERIAL
    panel._tid = 50  # the capture's request is tid 51
    return panel, core


async def test_identify_reply_gives_panel_serial():
    core = AsyncMock()
    core.send_wait.side_effect = [Frame.parse(IDENTIFY_REPLY), None, None]
    panel = Panel(core)
    assert await panel.initialize_communication("admin") is False  # no login reply
    assert panel.panel_serial == PANEL_SERIAL


async def test_arm_matches_capture():
    panel, core = control_panel()

    assert await panel.control_partitions([1], "arm") is True

    assert core.send_wait.call_args.kwargs["message"] == ARM_REQUEST
    core.connection.write.assert_called_once()  # ack of the panel's reply


@pytest.mark.parametrize(
    "command, action",
    [("arm", 0x13), ("arm_sleep", 0x12), ("arm_stay", 0x11), ("disarm", 0x10)],
)
def test_control_request_layout(command, action):
    panel, _ = control_panel()
    assert panel.build_control(PARTITION_ACTIONS[command]) == (
        bytes.fromhex("00ff0000000000")
        + PANEL_SERIAL
        + bytes([action])
        + bytes.fromhex("010001000000")
    )


@pytest.mark.parametrize(
    "partitions, command", [([1], "arm_force"), ([2], "arm"), ([1], "bogus")]
)
async def test_control_refuses_what_is_not_known(partitions, command):
    panel, core = control_panel()
    assert await panel.control_partitions(partitions, command) is False
    core.send_wait.assert_not_awaited()


async def test_control_needs_panel_serial():
    panel, core = control_panel()
    panel.panel_serial = None
    assert await panel.control_partitions([1], "disarm") is False
    core.send_wait.assert_not_awaited()


async def test_control_reports_refusal():
    panel, core = control_panel()

    panel.transact = AsyncMock(
        return_value=[bytes.fromhex("00ff0000000000") + PANEL_SERIAL + b"\x01\x00\x00"]
    )
    assert await panel.control_partitions([1], "arm") is False


async def test_control_without_reply_is_not_accepted():
    panel, core = control_panel()
    panel.transact = AsyncMock(side_effect=StatusRequestException("no reply"))
    assert await panel.control_partitions([1], "arm") is False
