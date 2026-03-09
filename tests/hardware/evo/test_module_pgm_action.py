"""
Tests for PerformModulePGMAction (build) and PerformModulePGMActionResponse (parse).

PerformModulePGMAction layout (build, PAI -> panel):
  Offset  Size  Field
  0       1     po: 0xA4 (command byte)
  1       1     packet_length = 23 (0x17)
  2       1     _not_used0
  3       1     module_address
  4       2     _not_used1
  6       1     pgm1_command (_PGMCommandEnum)
  7       1     pgm2_command
  8       1     pgm3_command
  9       1     module_pgm_command
  10      12    _not_used2
  22      1     checksum
  Total = 23 bytes

PerformModulePGMActionResponse layout (parse, panel -> PAI):
  Offset  Size  Field
  0       1     po: high nibble = 0xA, low nibble = status flags
  1       1     packet_length = 7
  2       1     _not_used0
  3       1     module_address
  4       2     _not_used1
  6       1     checksum
  Total = 7 bytes
"""

from binascii import unhexlify

from paradox.hardware.evo.parsers import PerformModulePGMAction, PerformModulePGMActionResponse


def _checksum(data: bytes) -> int:
    return sum(data) % 256


def _build(module_address, pgm_commands):
    return PerformModulePGMAction.build(
        {"fields": {"value": {"module_address": module_address, "pgm_commands": pgm_commands}}}
    )


# ---------------------------------------------------------------------------
# PerformModulePGMAction — BUILD tests
# ---------------------------------------------------------------------------


def test_build_trigger_pgm1_pulse_on():
    """Trigger PGM 1 (pulse on): A4 17 00 04 00 00 04 00 00 00 ... C3"""
    raw = _build(4, ["on_override", "release", "release", "release"])

    assert raw == unhexlify("a4170004000004000000000000000000000000000000c3")


def test_build_release_pgm1_pulse_off():
    """Release PGM 1 (pulse off): A4 17 00 04 00 00 02 00 00 00 ... C1"""
    raw = _build(4, ["off_override", "release", "release", "release"])

    assert raw == unhexlify("a4170004000002000000000000000000000000000000c1")


def test_build_activate_pgm3_steady_on():
    """Activate PGM 3 steady on: A4 17 00 04 00 00 00 00 03 00 ... C2"""
    raw = _build(4, ["release", "release", "on", "release"])

    assert raw == unhexlify("a4170004000000000300000000000000000000000000c2")


def test_build_trigger_module_pgm_pulse_on():
    """Trigger PGM 4 (pulse on): A4 17 00 04 00 00 00 00 00 04 ... C3"""
    raw = _build(4, ["release", "release", "release", "on_override"])

    assert raw == unhexlify("a4170004000000000004000000000000000000000000c3")


def test_build_deactivate_pgm1_steady_off():
    """Deactivate PGM 1 steady off (off=1): byte 6 = 0x01, checksum = 0xC0"""
    raw = _build(4, ["off", "release", "release", "release"])

    assert raw[0] == 0xA4
    assert raw[6] == 0x01   # off
    assert raw[7] == 0x00
    assert raw[8] == 0x00
    assert raw[9] == 0x00
    assert raw[-1] == _checksum(raw[:-1])


def test_build_activate_pgm2_steady_on():
    """Activate PGM 2 steady on (on=3): byte 7 = 0x03"""
    raw = _build(4, ["release", "on", "release", "release"])

    assert raw[6] == 0x00
    assert raw[7] == 0x03   # on
    assert raw[8] == 0x00
    assert raw[9] == 0x00
    assert raw[-1] == _checksum(raw[:-1])


def test_build_packet_length_always_23():
    """Packet length byte is always 23 (0x17) regardless of command."""
    for pgm_idx in range(4):
        commands = ["release"] * 4
        commands[pgm_idx] = "on"
        raw = _build(4, commands)
        assert len(raw) == 23
        assert raw[1] == 0x17


def test_build_command_byte_is_0xa4():
    """First byte is always 0xA4."""
    raw = _build(4, ["on", "release", "release", "release"])
    assert raw[0] == 0xA4


def test_build_module_address_at_byte3():
    """Module address is encoded at byte 3."""
    raw = _build(4, ["on", "release", "release", "release"])
    assert raw[3] == 0x04

    raw2 = _build(7, ["on", "release", "release", "release"])
    assert raw2[3] == 0x07


def test_build_non_command_bytes_are_zero():
    """Bytes 2, 4, 5 and the 12 trailing padding bytes are always zero."""
    raw = _build(4, ["on", "release", "release", "release"])
    assert raw[2] == 0x00           # _not_used0
    assert raw[4:6] == b"\x00\x00"  # _not_used1
    assert raw[10:22] == b"\x00" * 12  # _not_used2


def test_build_only_target_pgm_byte_nonzero():
    """Only the byte for the targeted PGM output is non-zero."""
    for pgm_idx in range(4):
        commands = ["release"] * 4
        commands[pgm_idx] = "on"
        raw = _build(4, commands)
        for i, cmd_byte in enumerate(raw[6:10]):
            if i == pgm_idx:
                assert cmd_byte == 3  # on
            else:
                assert cmd_byte == 0  # release


def test_build_checksum_correct():
    """Checksum is sum of all preceding bytes mod 256."""
    raw = _build(4, ["on_override", "release", "release", "release"])
    assert raw[-1] == _checksum(raw[:-1])


# ---------------------------------------------------------------------------
# PerformModulePGMActionResponse — PARSE tests
# ---------------------------------------------------------------------------


def test_parse_response_known_ack():
    """Parse the known panel ACK: A2 07 00 04 00 00 AD"""
    raw = unhexlify("a20700040000ad")
    parsed = PerformModulePGMActionResponse.parse(raw)

    assert parsed.fields.value.po.command == 0xA
    assert parsed.fields.value.packet_length == 7
    assert parsed.fields.value.module_address == 4


def test_parse_response_po_command_is_nibble_0xa():
    """po.command (high nibble) is always 0xA regardless of low nibble."""
    # Low nibble 2 = WinLoad connected flag
    raw = unhexlify("a20700040000ad")
    parsed = PerformModulePGMActionResponse.parse(raw)
    assert parsed.fields.value.po.command == 0xA


def test_parse_response_different_module_address():
    """Parse response for a module at address 7."""
    addr = 7
    body = bytes([0xA2, 0x07, 0x00, addr, 0x00, 0x00])
    cs = _checksum(body)
    raw = body + bytes([cs])

    parsed = PerformModulePGMActionResponse.parse(raw)
    assert parsed.fields.value.module_address == addr


def test_parse_response_reply_expected_match():
    """po.command == 0xA satisfies the reply_expected=0xA check used in send_wait."""
    raw = unhexlify("a20700040000ad")
    parsed = PerformModulePGMActionResponse.parse(raw)

    # This is the exact lambda used in send_wait
    reply_expected = 0xA
    assert parsed.fields.value.po.command == reply_expected
