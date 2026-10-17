from unittest.mock import AsyncMock

import pytest

from paradox.config import config as cfg
from paradox.connections.serial.encryption import make_serial_key
from paradox.exceptions import AuthenticationFailed
from paradox.hardware.mg6250.panel import (
    CMD_DATA,
    CMD_IDENTIFY,
    Frame,
    LoginResponse,
    Panel,
    build_frame,
    build_pw_block,
    credential_block,
)

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
