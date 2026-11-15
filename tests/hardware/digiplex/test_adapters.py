"""Bit order of the Digiplex RAM decoders (cases cross-checked against the
hand-written decoders they replaced)."""

from paradox.hardware.digiplex.property import RAMDataParserMap
from paradox.parsers.status import convert_raw_status


def test_zone_flags_bit_order():
    """bit0 (LSB) of the first byte is zone 1, bit7 of the sixth is zone 48."""
    data = bytes.fromhex("01 00 01 00 00 80") + bytes.fromhex("00 00 00 00 00 02")
    parsed = RAMDataParserMap[0x8153].parse(data + bytes(20))

    assert {i for i, v in parsed.zone_open.items() if v} == {1, 17, 48}
    assert {i for i, v in parsed.zone_tamper.items() if v} == {42}
    assert len(parsed.zone_open) == len(parsed.zone_tamper) == 48


def test_partition_blocks():
    """5-byte blocks at 0x0195 / 0x019A; unused bits and bytes are ignored."""
    block = bytearray(b"\xff" * 32)
    block[16:18] = b"\x65\x06"  # P1: armed + stay + silent + audible, exit + entry
    block[21:23] = b"\x8a\xf9"  # P2: only unknown/unused bits set

    status = convert_raw_status(RAMDataParserMap[0x8185].parse(bytes(block)))

    assert dict(status["partition"][1]) == dict(
        arm=True,
        arm_stay=True,
        audible_alarm=True,
        silent_alarm=True,
        exit_delay=True,
        entry_delay=True,
    )
    assert not any(status["partition"][2].values())
    assert set(status["partition"]) == {1, 2}
