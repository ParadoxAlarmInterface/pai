import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock

from construct import Container
import pytest

from paradox.config import config as cfg
from paradox.connections.serial.encryption import make_serial_key
from paradox.event import LiveEvent
from paradox.exceptions import AuthenticationFailed, StatusRequestException
from paradox.hardware.mg6250.panel import (
    ACK_GAP,
    AREA_FIELD_LABEL,
    CLOCK_FIELD_DATE,
    CLOCK_FIELD_POWER,
    CMD_DATA,
    CMD_IDENTIFY,
    CMD_LOGIN,
    FIELD_LABEL,
    FIELD_SERIAL,
    KIND_ACK,
    KIND_ACK_REPEAT,
    KIND_DATA,
    LAST_FRAGMENT,
    LOG_OP_RANGE,
    LOG_OP_READ,
    OBJ_AREA,
    OBJ_CLOCK,
    OBJ_PARTITION_STATUS,
    OBJ_SYSTEM,
    OBJ_USER,
    OBJ_ZONE,
    ZONE_DEFINITIONS,
    OBJ_ZONE_STATUS,
    PARTITION_ACTIONS,
    PARTITION_STATUS_FIELD,
    PROGRAMMING_BEGIN,
    PROGRAMMING_END,
    SERVICE_CONTROL,
    SERVICE_EVENT_LOG,
    SERVICE_OBJECTS,
    SERVICE_PROGRAMMING,
    SET_TIME_RETRY,
    SYSTEM_FIELD_STATUS,
    ZONE_ALARM_MEMORY,
    ZONE_IN_ALARM,
    ZONE_STATUS_FIELD,
    Frame,
    LogEvent,
    LoginResponse,
    Panel,
    PanelAckHandler,
    build_frame,
    build_log_request,
    build_pw_block,
    build_read_record,
    build_set_time_record,
    credential_block,
    decode_date,
    parse_log_records,
    parse_records,
)
from paradox.lib import ps
from paradox.lib.crypto import encrypt as paradox_encrypt
from paradox.hardware.spectra_magellan import parsers as sp_parsers
from paradox.hardware.spectra_magellan.panel import Panel as SpectraPanel
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


@pytest.mark.parametrize("status", [0x05, 0x85])
async def test_login_busy_is_retryable(status):
    """A session still open is not fatal: return False so PAI retries."""
    core = AsyncMock()
    reply = Frame.parse(build_frame(CMD_LOGIN, 2, bytes([status])))
    core.send_wait.side_effect = [None, None, reply]
    assert await Panel(core).initialize_communication("admin") is False


BUSY_REPLY = build_frame(CMD_LOGIN, 2, b"\x05")


def login_core():
    core = AsyncMock()
    core.connection = MagicMock()
    core.connection.handler_registry = HandlerRegistry()
    return core


async def test_login_saves_session(monkeypatch, tmp_path):
    path = tmp_path / "session.json"
    monkeypatch.setattr(cfg, "MG6250_SESSION_FILE", str(path))
    core = login_core()
    core.send_wait.side_effect = [None, None, Frame.parse(LOGIN_REPLY)]
    panel = Panel(core)
    assert await panel.initialize_communication("admin") is True

    assert path.stat().st_mode & 0o777 == 0o600
    saved = Panel._load_session()
    assert (saved.selector, saved.mode) == (0x08, 0x26)
    assert saved.session_key == panel.session_key


async def test_busy_login_resumes_saved_session(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MG6250_SESSION_FILE", str(tmp_path / "s.json"))
    core = login_core()
    core.send_wait.side_effect = [None, None, Frame.parse(LOGIN_REPLY)]
    await Panel(core).initialize_communication("admin")  # saves the session

    core = login_core()
    core.send_wait.side_effect = [None, None, Frame.parse(BUSY_REPLY)]
    panel = Panel(core)
    panel.read_records = AsyncMock(return_value={(OBJ_SYSTEM, 1): {1: b"\x05"}})
    assert await panel.initialize_communication("admin") is True
    assert (panel.session.selector, panel.session.mode) == (0x08, 0x26)
    assert len(core.connection.handler_registry) == 1  # panel acks handled


@pytest.mark.parametrize(
    "read", [AsyncMock(return_value={}), AsyncMock(side_effect=asyncio.TimeoutError)]
)
async def test_busy_login_drops_stale_session(monkeypatch, tmp_path, read):
    monkeypatch.setattr(cfg, "MG6250_SESSION_FILE", str(tmp_path / "s.json"))
    core = login_core()
    core.send_wait.side_effect = [None, None, Frame.parse(LOGIN_REPLY)]
    await Panel(core).initialize_communication("admin")

    core = login_core()
    core.send_wait.side_effect = [None, None, Frame.parse(BUSY_REPLY)]
    panel = Panel(core)
    panel.read_records = read
    assert await panel.initialize_communication("admin") is False
    assert panel.session is None and panel.session_key is None
    assert not (tmp_path / "s.json").exists()  # not tried again at the next login


async def test_busy_login_without_saved_session(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MG6250_SESSION_FILE", str(tmp_path / "missing.json"))
    core = login_core()
    core.send_wait.side_effect = [None, None, Frame.parse(BUSY_REPLY)]
    panel = Panel(core)
    panel.read_records = AsyncMock()
    assert await panel.initialize_communication("admin") is False
    panel.read_records.assert_not_awaited()


@pytest.mark.parametrize("status", [0x81, 0x83, 0x84])
async def test_login_refused_is_fatal(status):
    core = AsyncMock()
    reply = Frame.parse(build_frame(CMD_LOGIN, 2, bytes([status])))
    core.send_wait.side_effect = [None, None, reply]
    with pytest.raises(AuthenticationFailed):
        await Panel(core).initialize_communication("admin")


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


def test_panel_ack_handler_takes_the_session_frames():
    handler = PanelAckHandler(session_panel(0xB4, 0x62, SET_TIME_KEY))
    assert handler.can_handle(Frame.parse(SET_TIME_ACK))
    assert handler.can_handle(Frame.parse(SET_TIME_REPLY))
    assert not handler.can_handle(Frame.parse(IDENTIFY))
    assert not PanelAckHandler(Panel(AsyncMock())).can_handle(
        Frame.parse(SET_TIME_ACK)
    )  # no session key yet


async def test_repeated_reply_is_acked_again_and_others_are_left_alone():
    # 2026-11-08: a retried status read, the panel resent its reply about 2 s later
    core = AsyncMock()
    core.connection = MagicMock()
    core.send_wait.return_value = Frame.parse(SET_TIME_REPLY)
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY, core)
    handler = PanelAckHandler(panel)

    # A reply still awaited (not acked yet) must not be answered from here
    await handler(Frame.parse(SET_TIME_REPLY))
    core.connection.write.assert_not_called()

    await panel.transact(SERVICE_OBJECTS, b"")
    core.connection.write.reset_mock()
    await handler(Frame.parse(SET_TIME_REPLY))
    (frame,) = core.connection.write.call_args.args
    header = panel.decrypt_data(payload(frame))[0]
    assert (header.tid, header.fragment, header.kind) == (1, 0x8001, KIND_ACK_REPEAT)
    assert payload(frame)[17:] == b"\x02"

    core.connection.write.reset_mock()
    await handler(Frame.parse(SET_TIME_ACK))  # the panel's own ack: nothing to do
    core.connection.write.assert_not_called()


async def test_transact_without_reply_raises():
    core = AsyncMock()
    core.send_wait.return_value = None
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY, core)
    with pytest.raises(StatusRequestException):
        await panel.transact(SERVICE_OBJECTS, b"")


async def test_control_partition_returns_false_when_panel_is_silent():
    core = Paradox()
    core.send_wait = AsyncMock(side_effect=asyncio.TimeoutError)  # as after retries
    core.panel = session_panel(0xB4, 0x62, SET_TIME_KEY, core)
    core.panel.panel_serial = bytes(4)
    core.storage.get_container("partition").deep_merge(
        {1: {"id": 1, "key": "Partition 1"}}
    )

    assert await core.control_partition("1", "arm") is False


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


@pytest.mark.parametrize(
    "raw, mode",
    [
        # armed-stay-disarmed-sleep-disarm, slepp-armed-disarmed-open,
        # alarm-ir-etage: exit delay then armed for each arm mode
        # the mode bits are already set in the exit delay: not armed yet
        ("010001000000", None),
        ("050000000000", "stay"),
        ("020001000000", None),
        ("060000000000", "sleep"),
        ("030001000000", None),
        ("070000000000", "away"),
        # alarm-ir-etage: in alarm while fully armed
        ("770240000000", "away"),
        ("000000000000", None),
    ],
)
async def test_request_status_reports_arm_mode(raw, mode):
    panel = session_panel(0x1E, 0xE0, ALARM_KEY)
    panel._zones = [15]
    panel.read_records = status_reads([2], partition=bytes.fromhex(raw))

    converted = convert_raw_status(await panel.request_status(OBJ_CLOCK))

    partition = converted["partition"][1]
    modes = {m: partition[f"arm_{m}"] for m in ("stay", "sleep", "away")}
    assert modes == {m: m == mode for m in modes}


@pytest.mark.parametrize(
    "raw, forced",
    [
        # arm-bypass-disarm: full arm with zone 12 open
        ("031001000000", True),
        ("071000000000", True),
        # alarm-ir-etage: full arm with all zones closed
        ("030001000000", False),
        ("070000000000", False),
        # exit-delay-audio: disarmed after an alarm
        ("000200000000", False),
    ],
)
async def test_request_status_reports_forced_arm(raw, forced):
    panel = session_panel(0x1E, 0xE0, ALARM_KEY)
    panel._zones = [15]
    panel.read_records = status_reads([2], partition=bytes.fromhex(raw))

    converted = convert_raw_status(await panel.request_status(OBJ_CLOCK))

    assert converted["partition"][1]["arm_force"] is forced


# set_time.pcapng, decrypted: the same 8 bytes then 00 00 in the session replies
SET_TIME_RECORD = "05100024000100010006141a0a101404"
CLOCK_WRITE_REPLY = bytes.fromhex("050d0024000100000400010000")
BEGIN_REPLY = bytes.fromhex("00000000ffffffff0000")
END_REPLY = bytes.fromhex("01000000ffffffff0000")
SET_TIME_NOW = datetime.datetime(2026, 10, 16, 20, 4)


def test_set_time_record_matches_capture():
    assert build_set_time_record(SET_TIME_NOW).hex() == SET_TIME_RECORD


def set_time_panel(monkeypatch, replies):
    monkeypatch.setattr("paradox.hardware.mg6250.panel.WRITE_SETTLE", 0)
    panel = session_panel(0xB4, 0x62, SET_TIME_KEY)
    panel.transact = AsyncMock(side_effect=replies)
    return panel


async def test_set_time_is_a_write_inside_a_programming_session(monkeypatch):
    panel = set_time_panel(
        monkeypatch, [[BEGIN_REPLY], [CLOCK_WRITE_REPLY], [END_REPLY]]
    )
    assert await panel.set_time(SET_TIME_NOW) is True
    assert [c.args for c in panel.transact.await_args_list] == [
        (SERVICE_PROGRAMMING, bytes.fromhex("00000000ffffffff3c00")),
        (SERVICE_OBJECTS, bytes.fromhex(SET_TIME_RECORD)),
        (SERVICE_PROGRAMMING, bytes.fromhex("01000000ffffffff")),
    ]


async def test_set_time_refused_session_writes_nothing_and_is_not_retried(monkeypatch):
    refused = bytes.fromhex("00000000ffffffff0100")
    panel = set_time_panel(monkeypatch, [[refused]])
    assert await panel.set_time(SET_TIME_NOW) is False
    assert await panel.set_time(SET_TIME_NOW) is None  # not tried again
    panel.transact.assert_awaited_once()  # and no End after a refused Begin


async def test_set_time_refused_write_is_not_retried(monkeypatch):
    refused = bytes.fromhex("050d0024000100010400010000")
    panel = set_time_panel(monkeypatch, [[BEGIN_REPLY], [refused], [END_REPLY]])
    assert await panel.set_time(SET_TIME_NOW) is False
    assert await panel.set_time(SET_TIME_NOW) is None
    assert panel.transact.await_count == 3


@pytest.mark.parametrize(
    "failure", [asyncio.TimeoutError(), StatusRequestException("no reply")]
)
async def test_set_time_lost_begin_reply_still_ends_the_session(monkeypatch, failure):
    # the panel may have opened the programming session all the same
    panel = set_time_panel(monkeypatch, [failure, [END_REPLY]])
    assert await panel.set_time(SET_TIME_NOW) is False
    assert [c.args[1] for c in panel.transact.await_args_list] == [
        PROGRAMMING_BEGIN,
        PROGRAMMING_END,
    ]


async def test_set_time_lost_end_reply_keeps_the_accepted_write(monkeypatch):
    panel = set_time_panel(
        monkeypatch,
        [[BEGIN_REPLY], [CLOCK_WRITE_REPLY], asyncio.TimeoutError()],
    )
    assert await panel.set_time(SET_TIME_NOW) is True


async def test_set_time_lost_reply_is_retried_later(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(
        "paradox.hardware.mg6250.panel.time.monotonic", lambda: clock[0]
    )
    panel = set_time_panel(
        monkeypatch,
        [
            [BEGIN_REPLY],
            asyncio.TimeoutError(),
            [END_REPLY],
            [BEGIN_REPLY],
            [CLOCK_WRITE_REPLY],
            [END_REPLY],
        ],
    )
    assert await panel.set_time(SET_TIME_NOW) is False
    clock[0] += SET_TIME_RETRY - 1
    assert await panel.set_time(SET_TIME_NOW) is None  # too early
    assert panel.transact.await_count == 3
    clock[0] += 1
    assert await panel.set_time(SET_TIME_NOW) is True


async def test_set_time_refused_write_still_ends_the_session(monkeypatch):
    refused = bytes.fromhex("050d0024000100010400010000")
    panel = set_time_panel(monkeypatch, [[BEGIN_REPLY], [refused], [END_REPLY]])
    assert await panel.set_time(SET_TIME_NOW) is False
    assert panel.transact.await_args.args[1] == bytes.fromhex("01000000ffffffff")


@pytest.mark.parametrize(
    "failure", [asyncio.TimeoutError(), StatusRequestException("no reply")]
)
async def test_set_time_lost_write_still_ends_the_session(monkeypatch, failure):
    panel = set_time_panel(monkeypatch, [[BEGIN_REPLY], failure, [END_REPLY]])
    assert await panel.set_time(SET_TIME_NOW) is False
    assert panel.transact.await_count == 3
    assert panel.transact.await_args.args[1] == bytes.fromhex("01000000ffffffff")


async def test_base_panel_set_time_still_sends_set_time_date():
    # SP/MG and EVO keep using the SetTimeDate message
    core = AsyncMock()
    start = Container(fields=Container(value=Container(firmware=Container(version=7))))
    panel = SpectraPanel(core, start)
    assert await panel.set_time(SET_TIME_NOW) is True
    call = core.send_wait.await_args
    assert call.args[0] is panel.get_message("SetTimeDate")
    assert call.args[1] == dict(
        century=20, year=26, month=10, day=16, hour=20, minute=4
    )
    assert call.kwargs["reply_expected"] == 0x3


# pf-salon-open: event log requests and replies, decrypted
LOG_RANGE_REQUEST = "010d00010192720000ffffffff"
LOG_RANGE_REPLY = "0113000001010092720000ae7200001d00000000"
LOG_READ_REQUEST = "001100010192720000ae72000000000000"


def log_event(number, major, minor, label=b"", label_type=1, area=1):
    return (
        number.to_bytes(4, "little")
        + bytes([0x1F, major, minor, area])
        + bytes.fromhex("141a0b071602")  # 2026-11-07 22:02
        + bytes.fromhex("000100fbff")
        + bytes([label_type])
        + label.ljust(16, b" ")
    )


def log_reply(first, last, events):
    body = (
        bytes([0, 19 + len(events) * 36])
        + bytes.fromhex("0000010100")
        + first.to_bytes(4, "little")
        + last.to_bytes(4, "little")
        + len(events).to_bytes(4, "little")
        + b"".join(events)
    )
    return body + bytes([0xEE]) * (-len(body) % 16)


def range_reply(first, last):
    return bytes.fromhex(
        "01130000010100"
        + first.to_bytes(4, "little").hex()
        + last.to_bytes(4, "little").hex()
        + (last - first + 1).to_bytes(4, "little").hex()
    )


def test_log_requests_match_capture():
    assert build_log_request(LOG_OP_RANGE, 0x7292).hex() == LOG_RANGE_REQUEST
    assert build_log_request(LOG_OP_READ, 0x7292, 0x72AE).hex() == LOG_READ_REQUEST


def test_parse_log_range_reply():
    (record,) = parse_log_records(bytes.fromhex(LOG_RANGE_REPLY))
    assert (record.op, record.first, record.last, record.count) == (
        LOG_OP_RANGE,
        0x7292,
        0x72AE,
        29,
    )
    assert record.events == []


def test_parse_log_read_reply():
    data = log_reply(
        0x7292, 0x7293, [log_event(0x7292, 6, 3), log_event(0x7293, 41, 5)]
    )
    (record,) = parse_log_records(data)
    assert [(e.number, e.major, e.minor) for e in record.events] == [
        (0x7292, 6, 3),
        (0x7293, 41, 5),
    ]


def log_panel(replies):
    """A logged-in panel whose log requests get `replies`, one list of fragments each."""
    core = MagicMock()
    core.get_label.return_value = None
    panel = session_panel(0x94, 0x42, STATUS_KEY, core)
    panel._log_enabled = True
    panel.transact = AsyncMock(side_effect=replies)
    return panel, core


async def test_first_poll_only_notes_the_log_position():
    panel, core = log_panel([[range_reply(0x7292, 0x72AE)]])
    await panel._publish_new_events()
    assert panel._log_last == 0x72AE
    panel.transact.assert_awaited_once_with(
        SERVICE_EVENT_LOG, build_log_request(LOG_OP_RANGE, 0)
    )
    core.handle_event_message.assert_not_called()


async def test_no_new_event_reads_nothing():
    panel, core = log_panel([[range_reply(0x7292, 0x72AE)]])
    panel._log_last = 0x72AE
    await panel._publish_new_events()
    panel.transact.assert_awaited_once_with(
        SERVICE_EVENT_LOG, build_log_request(LOG_OP_RANGE, 0x72AE)
    )
    core.handle_event_message.assert_not_called()


async def test_log_going_back_follows_it_without_publishing():
    # log cleared: the old position would never be passed again
    panel, core = log_panel(
        [
            [range_reply(1, 3)],
            [range_reply(1, 4)],
            [log_reply(4, 4, [log_event(4, 47, 15)])],
        ]
    )
    panel._log_last = 0x72AE
    await panel._publish_new_events()
    assert panel._log_last == 3
    core.handle_event_message.assert_not_called()

    await panel._publish_new_events()
    panel.transact.assert_awaited_with(
        SERVICE_EVENT_LOG, build_log_request(LOG_OP_READ, 4, 4)
    )
    core.handle_event_message.assert_called_once()
    assert panel._log_last == 4


async def test_new_events_are_published_once_in_order():
    events = [log_event(0x72AF, 47, 15), log_event(0x72B0, 42, 1)]
    panel, core = log_panel(
        [[range_reply(0x7292, 0x72B0)], [log_reply(0x72AF, 0x72B0, events)]]
    )
    panel._log_last = 0x72AE
    await panel._publish_new_events()
    panel.transact.assert_awaited_with(
        SERVICE_EVENT_LOG, build_log_request(LOG_OP_READ, 0x72AF, 0x72B0)
    )
    messages = [
        c.args[0].fields.value for c in core.handle_event_message.call_args_list
    ]
    assert [(m.event.major, m.event.minor) for m in messages] == [(47, 15), (42, 1)]
    assert messages[0].time == datetime.datetime(2026, 11, 7, 22, 2)
    assert panel._log_last == 0x72B0


@pytest.mark.parametrize(
    "failure", [asyncio.TimeoutError(), StatusRequestException("no reply")]
)
async def test_refused_first_request_stops_reading_the_log(failure):
    panel, core = log_panel([failure])
    await panel._publish_new_events()
    assert panel._log_enabled is False
    await panel._publish_new_events()  # no second request
    panel.transact.assert_awaited_once()


async def test_later_failure_keeps_reading_the_log():
    panel, core = log_panel([asyncio.TimeoutError(), [range_reply(0x7292, 0x72AE)]])
    panel._log_last = 0x72AE
    await panel._publish_new_events()
    assert panel._log_enabled is True
    await panel._publish_new_events()
    assert panel.transact.await_count == 2


def live_event(panel, major, minor, label=b""):
    message = panel._log_event_message(
        LogEvent.parse(log_event(0x7292, major, minor, label))
    )
    labels = {("partition", 1): "Area 1", ("zone", 15): "IR ETAGE"}
    return LiveEvent(message, Panel.event_map, lambda t, i: labels.get((t, i)))


@pytest.mark.parametrize(
    "major, minor, kind, text",
    [
        (6, 3, "partition", "Partition Area 1 armed in stay mode"),
        (6, 4, "partition", "Partition Area 1 armed in sleep mode"),
        (41, 5, "partition", "Partition Area 1 armed via BabyWare"),
        (45, 1, "partition", "Partition Area 1 disarmed via BabyWare"),
        (54, 2, "system", "Software log on"),
        (55, 4, "system", "Console tamper"),
        (56, 4, "system", "Console tamper restore"),
        (55, 12, "system", "Fail to communicate personal reporting"),
        (22, 66, "system", "Battery voltage level"),
    ],
)
def test_log_event_messages(major, minor, kind, text):
    panel, core = log_panel([])
    event = live_event(panel, major, minor)
    assert (event.type, event.message) == (kind, text)


def test_log_event_uses_todays_label_and_changes_no_state():
    panel, core = log_panel([])
    core.get_label.side_effect = lambda t, i: (
        "IR ETAGE" if (t, i) == ("zone", 15) else None
    )
    event = live_event(panel, 47, 15, b"Zone 15")  # the label when it was saved
    assert (event.type, event.id, event.label) == ("zone", 15, "IR ETAGE")
    assert event.message == "Zone IR ETAGE in alarm"
    assert event.change == {}


def test_saved_events_change_no_state():
    # tables 11 and 12: polling stays the source of state
    for major, event in Panel.event_map.items():
        if major > 3:
            assert "change" not in event, major
            for sub in event.get("sub", {}).values():
                assert not isinstance(sub, dict) or "change" not in sub, major


def test_property_map_covers_what_the_panel_publishes():
    # every property request_status publishes, and PAI's derived states
    for name in (
        "arm",
        "arm_stay",
        "arm_sleep",
        "arm_away",
        "arm_force",
        "exit_delay",
        "audible_alarm",
        "ready_status",
        "current_state",
        "target_state",
        "open",
        "presently_in_alarm",
        "generated_alarm",
        "time",
        "battery",
        "ac",
    ):
        assert name in Panel.property_map


@pytest.mark.parametrize(
    "zones, zone_partitions, ready",
    [
        ({8: b"\x00\x00\x00", 12: b"\x00\x00\x00"}, {8: 1, 12: 1}, True),
        # open-closed-open-closed-ready: ST F CUISINE and ST SEJOUR G
        ({8: b"\x01\x00\x00", 12: b"\x01\x00\x00"}, {8: 1, 12: 1}, False),
        ({8: b"\x00\x00\x00", 12: b"\x01\x00\x00"}, {8: 1, 12: 3}, False),
        # open zone of the other partition, or of an unknown one
        ({8: b"\x01\x00\x00", 12: b"\x00\x00\x00"}, {8: 2, 12: 1}, True),
        ({8: b"\x01\x00\x00", 12: b"\x00\x00\x00"}, {}, False),
    ],
)
async def test_request_status_calculates_ready(zones, zone_partitions, ready):
    panel = session_panel(0x1E, 0xE0, ALARM_KEY)
    panel._zones = sorted(zones)
    panel._zone_partitions = zone_partitions
    panel.read_records = status_reads([2], zones=zones)

    converted = convert_raw_status(await panel.request_status(OBJ_CLOCK))

    assert converted["partition"][1]["ready_status"] is ready


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
    assert panel._zone_partitions == {1: 1}
    assert panel._zones == [1]  # status polls enrolled zones only
    assert panel._zone_definitions == {1: 9}
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


async def test_load_labels_ignores_limits_outside_panel_range(monkeypatch):
    monkeypatch.setattr(
        cfg, "LIMITS", {"zone": [1, 65], "user": [2, 17], "partition": [1, 2]}
    )
    panel = session_panel(0x3E, 0x00, ZONES_KEY)
    requested = {}

    async def read_objects(obj, indexes, fields):
        requested[obj] = list(indexes)
        return {i: {FIELD_SERIAL: bytes(6)} for i in indexes} if obj == OBJ_ZONE else {}

    panel.read_objects = read_objects
    await panel.load_labels()
    assert requested[OBJ_ZONE] == [1]
    assert requested[OBJ_USER] == [2]
    assert requested[OBJ_AREA] == [1]


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


async def test_accepted_control_forces_status_reread():
    """A disarm does not move the 0x1c counter: the next poll must re-read."""
    panel, _ = control_panel()
    panel._change_counter = 0x42
    assert await panel.control_partitions([1], "disarm") is True
    assert panel._change_counter is None


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


async def test_control_before_login_is_refused():
    # 2026-11-07: an MQTT arm_sleep arrived while PAI was reconnecting
    panel, core = control_panel()
    panel.session = None
    assert await panel.control_partitions([1], "arm_sleep") is False
    core.send_wait.assert_not_awaited()


# captures/bypass: zone 12, panel serial replaced by 01020304
ZONE_BYPASS_REQUEST = "01ff00000000000102030401" + "0c0001000000"
ZONE_CLEAR_REQUEST = "01ff00000000000102030400" + "0c0001000000"
ZONE_CONTROL_REPLY = "01ff0000000000" + "01020304" + "000000"


@pytest.mark.parametrize(
    "command, request_hex",
    [("bypass", ZONE_BYPASS_REQUEST), ("clear_bypass", ZONE_CLEAR_REQUEST)],
)
async def test_zone_control_matches_capture(command, request_hex):
    panel, core = control_panel()
    panel.transact = AsyncMock(return_value=[bytes.fromhex(ZONE_CONTROL_REPLY)])
    assert await panel.control_zones([12], command) is True
    panel.transact.assert_awaited_once_with(SERVICE_CONTROL, bytes.fromhex(request_hex))
    assert panel._change_counter is None  # the next poll reads the status again


async def test_zone_control_refuses_unknown_command():
    panel, core = control_panel()
    panel.transact = AsyncMock()
    assert await panel.control_zones([12], "toggle") is False
    panel.transact.assert_not_awaited()


async def test_zone_control_reports_refusal():
    panel, core = control_panel()
    panel._change_counter = 7
    refused = bytes.fromhex("01ff0000000000" + "01020304" + "010000")
    panel.transact = AsyncMock(return_value=[refused])
    assert await panel.control_zones([12], "bypass") is False
    assert panel._change_counter == 7


async def test_zone_control_without_reply_or_login_is_not_accepted():
    panel, core = control_panel()
    panel.transact = AsyncMock(side_effect=StatusRequestException("no reply"))
    assert await panel.control_zones([12], "bypass") is False
    panel, core = control_panel()
    panel.session = None
    assert await panel.control_zones([12], "bypass") is False
    core.send_wait.assert_not_awaited()


# captures/send-zone-sleep: BabyWare set zone 14 (IR S/SOL) from Instant (Full
# Arm) to Instant (Sleep / Full Arm)
ZONE_FIELD_BEFORE = bytes.fromhex("bb8b0a018700")
ZONE_DEFINITION_WRITE = "0110" + "0001000e" + "00" + "00" + "0006" + "bb8b09018700"
ZONE_WRITE_REPLY = bytes.fromhex("010b0001000e0000000000")


def definition_panel(monkeypatch, replies, field=ZONE_FIELD_BEFORE):
    monkeypatch.setattr("paradox.hardware.mg6250.panel.WRITE_SETTLE", 0)
    monkeypatch.setattr("paradox.lib.ps.sendMessage", MagicMock())
    panel, core = control_panel()
    panel._zone_definitions = {14: field[2]}
    panel.read_objects = AsyncMock(return_value={14: {FIELD_SERIAL: field}})
    panel.transact = AsyncMock(side_effect=replies)
    return panel


@pytest.mark.parametrize("command", ["definition_9", "definition_instant_sleep_full"])
async def test_zone_definition_write_matches_capture(monkeypatch, command):
    panel = definition_panel(
        monkeypatch, [[BEGIN_REPLY], [ZONE_WRITE_REPLY], [END_REPLY]]
    )
    assert await panel.control_zones([14], command) is True
    panel.read_objects.assert_awaited_once_with(OBJ_ZONE, [14], (FIELD_SERIAL,))
    assert [c.args for c in panel.transact.await_args_list] == [
        (SERVICE_PROGRAMMING, bytes.fromhex("00000000ffffffff3c00")),
        (SERVICE_OBJECTS, bytes.fromhex(ZONE_DEFINITION_WRITE)),
        (SERVICE_PROGRAMMING, bytes.fromhex("01000000ffffffff")),
    ]
    assert panel._zone_definitions == {14: 9}
    # published again, under paradox/definitions
    ps.sendMessage.assert_called_once_with(
        "definitions_loaded",
        data={"zone": {14: {"definition": "instant_sleep_full", "partition": None}}},
    )


async def test_zone_definition_already_set_writes_nothing(monkeypatch):
    panel = definition_panel(monkeypatch, [])
    assert await panel.control_zones([14], "definition_instant_full") is True
    panel.transact.assert_not_awaited()
    ps.sendMessage.assert_not_called()


@pytest.mark.parametrize(
    "command",
    [
        "definition_0",
        "definition_disabled",
        "definition_30",
        "definition_",
        "definition_x",
    ],
)
async def test_zone_definition_refuses_unknown_definitions(monkeypatch, command):
    panel = definition_panel(monkeypatch, [])
    assert await panel.control_zones([14], command) is False
    panel.read_objects.assert_not_awaited()
    panel.transact.assert_not_awaited()


async def test_zone_definition_refuses_a_zone_not_enrolled(monkeypatch):
    panel = definition_panel(monkeypatch, [], field=bytes.fromhex("000000018700"))
    assert await panel.control_zones([14], "definition_9") is False
    panel.transact.assert_not_awaited()


async def test_zone_definition_refused_write_ends_the_session(monkeypatch):
    refused = bytes.fromhex("010b0001000e0001000000")
    panel = definition_panel(monkeypatch, [[BEGIN_REPLY], [refused], [END_REPLY]])
    assert await panel.control_zones([14], "definition_9") is False
    assert panel.transact.await_count == 3
    assert panel._zone_definitions == {14: 10}


async def test_zone_definition_lost_write_ends_the_session(monkeypatch):
    panel = definition_panel(
        monkeypatch, [[BEGIN_REPLY], StatusRequestException("no reply"), [END_REPLY]]
    )
    assert await panel.control_zones([14], "definition_9") is False
    assert panel.transact.await_args_list[-1].args == (
        SERVICE_PROGRAMMING,
        bytes.fromhex("01000000ffffffff"),
    )
    assert panel._zone_definitions == {14: 10}


async def test_definitions_are_named_as_for_the_sp_mg_panels():
    panel, core = control_panel()
    panel._zone_definitions = {14: 9, 15: 10, 16: 99}
    panel._zone_partitions = {14: 1, 15: 1, 16: 3}
    assert await panel.load_definitions() == {
        "zone": {
            14: {"definition": "instant_sleep_full", "partition": 1},
            15: {"definition": "instant_full", "partition": 1},
            16: {"definition": 99, "partition": 3},  # not in the guide
        }
    }
    sp_names = sp_parsers.DefinitionsParserMap["zone"].definition
    for number, name in ZONE_DEFINITIONS.items():
        if number <= 26:
            assert sp_names.encmapping[name] == number


async def test_load_memory_sends_definitions_then_labels(mocker):
    panel, core = control_panel()
    panel.load_labels = AsyncMock(return_value={"zone": {}})
    panel._zone_definitions = {14: 9}
    panel._zone_partitions = {14: 1}
    send = mocker.patch("paradox.lib.ps.sendMessage")
    await panel.load_memory()
    assert [c.args[0] for c in send.call_args_list] == [
        "definitions_loaded",
        "labels_loaded",
    ]
    assert send.call_args_list[0].kwargs["data"]["zone"][14]["definition"] == (
        "instant_sleep_full"
    )


# captures/refresh-disconnect: BabyWare disconnecting from session 91 69
LOGOUT_REQUEST = bytes.fromhex("de01000c0000000191692 8b5".replace(" ", ""))


async def test_close_connection_logs_out(monkeypatch, tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{}")
    monkeypatch.setattr(cfg, "MG6250_SESSION_FILE", str(path))
    core = MagicMock()
    panel = session_panel(0x91, 0x69, STATUS_KEY, core)
    panel._log_enabled = True
    panel.close_connection()
    core.connection.write.assert_called_once_with(LOGOUT_REQUEST)
    assert panel.session is None and panel.session_key is None
    assert panel._log_enabled is False
    assert not path.exists()  # it cannot be resumed any more


def test_close_connection_without_a_session_sends_the_generic_close():
    core = MagicMock()
    panel = Panel(core)
    panel.close_connection()
    core.connection.write.assert_called_once_with(
        panel.get_message("CloseConnection").build(dict())
    )


def test_base_panel_close_connection_is_unchanged():
    core = MagicMock()
    start = Container(fields=Container(value=Container(firmware=Container(version=7))))
    panel = SpectraPanel(core, start)
    panel.close_connection()
    core.connection.write.assert_called_once_with(
        panel.get_message("CloseConnection").build(dict())
    )


async def test_time_sync_does_not_overlap():
    # The core starts it at every status update; set_time takes over a second
    alarm = Paradox()
    alarm.panel = MagicMock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def set_time(now):
        started.set()
        await release.wait()
        return True

    alarm.panel.set_time = AsyncMock(side_effect=set_time)
    alarm._is_time_sync_required = lambda now: True
    first = asyncio.create_task(alarm.sync_time())
    await started.wait()
    await alarm.sync_time()
    release.set()
    await first
    alarm.panel.set_time.assert_awaited_once()
    await alarm.sync_time()  # and it can run again afterwards
    assert alarm.panel.set_time.await_count == 2
