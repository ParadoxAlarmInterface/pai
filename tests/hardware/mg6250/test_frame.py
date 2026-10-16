import pytest

from paradox.connections.serial.encryption import make_serial_key

from paradox.hardware.mg6250.panel import (
    CMD_DATA,
    CMD_IDENTIFY,
    Frame,
    LoginResponse,
    Panel,
    build_frame,
)

IDENTIFY = bytes.fromhex("de00000a00000001951a")


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


def test_decrypt_captured_data_frame():
    login = bytes.fromhex(
        "de01003a00000002007fed6b10ac84fdb756fc3afeaa06592f7fd7e322e899caa93a"
        "572696c39099f728fbc7ea9d344dc559588b81f6c3f44c2c"
    )
    data = bytes.fromhex("de24001c00000008264227190a2630a77cfe2d4cb9948713db00e09e")
    panel = Panel.__new__(Panel)
    panel.session = Panel._decrypt_login_reply(
        bytes(Frame.parse(login).fields.value.payload), make_serial_key("admin")
    )
    panel.session_key = panel.session.session_key
    assert (panel.session.selector, panel.session.mode) == (0x08, 0x26)

    header, subtype, body = panel.decrypt_data(
        bytes(Frame.parse(data).fields.value.payload)
    )
    assert header == bytes.fromhex("01000180801700082600000000000000")
    assert (subtype, body) == (None, None)
