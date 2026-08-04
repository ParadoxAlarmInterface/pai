"""Tests for the serial framer.

These cover length derivation and the resynchronisation rules directly, with
plain bytes and no transport, which the previous protocol-coupled design could
not do.
"""

import pytest

from paradox.config import config as cfg
from paradox.connections.framing import NEED_MORE, RESYNC
from paradox.connections.serial.framing import MAX_AES_BLOCKS, SerialFramer


def frames(framer, data):
    """Feed bytes and return the frames produced, draining the generator."""
    return list(framer.feed(data))


def make_frame(payload):
    """Append a valid 8-bit checksum."""
    return payload + bytes([sum(payload) % 256])


@pytest.fixture
def plain(mocker):
    mocker.patch.object(cfg, "SERIAL_ENCRYPTED", False)
    return SerialFramer()


@pytest.fixture
def encrypted(mocker):
    mocker.patch.object(cfg, "SERIAL_ENCRYPTED", True)
    return SerialFramer()


class TestFixedLength:
    def test_fixed_mode_requires_37_bytes(self, plain):
        plain.use_variable_message_length = False
        assert frames(plain, b"\x00" * 36) == []
        out = frames(plain, b"\x00")
        assert len(out) == 1
        assert len(out[0].data) == 37

    def test_fixed_mode_ignores_header_nibble(self, plain):
        plain.use_variable_message_length = False
        payload = bytes([0xC0]) + b"\x00" * 35
        out = frames(plain, make_frame(payload))
        assert len(out) == 1
        assert len(out[0].data) == 37


class TestLengthDerivation:
    def test_nibble_zero_is_fixed_37(self, plain):
        assert plain.derive_length(b"\x00\x05").length == 37

    @pytest.mark.parametrize("nibble", [1, 3, 4, 5, 6, 7, 8, 9])
    def test_short_nibbles_take_length_from_byte_one(self, plain, nibble):
        assert plain.derive_length(bytes([nibble << 4, 40])).length == 40

    @pytest.mark.parametrize("nibble", [1, 3, 4, 5, 6, 7, 8, 9])
    def test_short_nibbles_fall_back_to_37_when_out_of_range(self, plain, nibble):
        assert plain.derive_length(bytes([nibble << 4, 0])).length == 37
        assert plain.derive_length(bytes([nibble << 4, 72])).length == 37

    def test_nibble_two_is_not_a_length_carrying_nibble(self, plain):
        # Deliberately preserved from the original implementation: 0x2 is
        # absent from the length-carrying set and falls through to 37.
        assert plain.derive_length(b"\x20\x28").length == 37

    @pytest.mark.parametrize("nibble", [0xA, 0xB, 0xD])
    def test_ab_d_nibbles_take_length_from_byte_one(self, plain, nibble):
        assert plain.derive_length(bytes([nibble << 4, 40])).length == 40

    def test_c_nibble_is_big_endian_16_bit(self, plain):
        assert plain.derive_length(b"\xc0\x00\x25").length == 37

    def test_c_nibble_needs_three_bytes(self, plain):
        assert plain.derive_length(b"\xc0\x00") is NEED_MORE

    def test_e_nibble_small_byte_one_is_fixed_37(self, plain):
        assert plain.derive_length(b"\xe0\x13").length == 37
        assert plain.derive_length(b"\xe0\x00").length == 37
        assert plain.derive_length(b"\xe0\xff").length == 37

    def test_e_nibble_large_byte_one_is_the_length(self, plain):
        assert plain.derive_length(b"\xe0\x28").length == 40

    def test_unknown_nibble_is_fixed_37(self, plain):
        assert plain.derive_length(b"\xf0\x05").length == 37


class TestImplausibleLengths:
    def test_implausible_length_resyncs_rather_than_stalling(self, plain):
        # A battery voltage byte 0xC0-0xCF at the head reads as ~39000 bytes.
        assert plain.derive_length(b"\xc9\x88\x77") is RESYNC

    def test_zero_length_resyncs(self, plain):
        assert plain.derive_length(b"\xa0\x00") is RESYNC

    def test_misaligned_stream_recovers_and_frames_the_real_message(self, plain):
        real = make_frame(bytes([0x50, 37]) + b"\x00" * 34)
        out = frames(plain, b"\xc9\x88" + real)
        assert len(out) == 1
        assert out[0].data == real


class TestChecksum:
    def test_bad_checksum_costs_exactly_one_byte(self, plain):
        bad = bytes([0x50, 37]) + b"\x00" * 34 + b"\xff"
        assert frames(plain, bad) == []
        assert len(plain.buffer) == 36

    def test_frame_after_a_bad_one_is_still_found(self, plain):
        good = make_frame(bytes([0x50, 37]) + b"\x00" * 34)
        bad = bytes([0x50, 37]) + b"\x00" * 34 + b"\xff"
        out = frames(plain, bad + good)
        assert [f.data for f in out] == [good]


class TestPipelining:
    def test_two_frames_in_one_callback_both_emit(self, plain):
        a = make_frame(bytes([0x50, 37]) + b"\x11" * 34)
        b = make_frame(bytes([0x50, 37]) + b"\x22" * 34)
        assert [f.data for f in frames(plain, a + b)] == [a, b]

    def test_frame_split_across_callbacks_reassembles(self, plain):
        a = make_frame(bytes([0x50, 37]) + b"\x11" * 34)
        assert frames(plain, a[:10]) == []
        assert [f.data for f in frames(plain, a[10:])] == [a]

    def test_byte_at_a_time_delivery_still_frames(self, plain):
        a = make_frame(bytes([0x50, 37]) + b"\x11" * 34)
        out = []
        for i in range(len(a)):
            out += frames(plain, a[i : i + 1])
        assert [f.data for f in out] == [a]

    def test_generator_abandoned_midway_keeps_remaining_bytes(self, plain):
        a = make_frame(bytes([0x50, 37]) + b"\x11" * 34)
        b = make_frame(bytes([0x50, 37]) + b"\x22" * 34)
        gen = plain.feed(a + b)
        assert next(gen).data == a
        gen.close()
        # The second frame was never consumed, so it must still be parseable.
        assert [f.data for f in frames(plain, b"")] == [b]


class TestBabyWareCompactE0FE:
    def test_length_comes_from_byte_two(self, plain):
        result = plain.derive_length(b"\xe0\xfe\x0c")
        assert result.length == 12
        assert result.encrypted is True

    def test_needs_three_bytes(self, plain):
        assert plain.derive_length(b"\xe0\xfe") is NEED_MORE

    def test_implausible_length_resyncs_instead_of_spinning(self, plain):
        # A zero-length frame would consume nothing and loop forever.
        assert plain.derive_length(b"\xe0\xfe\x00") is RESYNC
        assert plain.derive_length(b"\xe0\xfe\x03") is RESYNC

    def test_compact_frame_is_exempt_from_the_71_byte_maximum(self, plain):
        assert plain.derive_length(b"\xe0\xfe\xc8").length == 200

    def test_compact_frame_emits_without_checksum_validation(self, plain):
        raw = b"\xe0\xfe\x0c" + b"\xaa" * 9
        out = frames(plain, raw)
        assert len(out) == 1
        assert out[0].data == raw
        assert out[0].encrypted is True


class TestFullAesE0FE:
    def test_single_block_frame_is_found_by_checksum(self, encrypted):
        raw = make_frame(b"\xe0\xfe" + b"\x5a" * 16)
        out = frames(encrypted, raw)
        assert len(out) == 1
        assert out[0].data == raw
        assert out[0].encrypted is True

    def test_multi_block_frame_is_found_by_checksum(self, encrypted):
        raw = make_frame(b"\xe0\xfe" + b"\x5a" * 48)
        out = frames(encrypted, raw)
        assert [f.data for f in out] == [raw]

    def test_partial_frame_waits_for_more_data(self, encrypted):
        raw = make_frame(b"\xe0\xfe" + b"\x5a" * 16)
        assert frames(encrypted, raw[:-1]) == []

    def test_junk_does_not_stall_the_link_forever(self, encrypted):
        """Regression: the AES scan used to break and never resync.

        E0 FE followed by data that never checksums left the buffer growing
        without bound and the handler never called again.
        """
        junk = b"\xe0\xfe" + bytes((i * 7 + 3) % 256 for i in range(4000))
        frames(encrypted, junk)
        assert len(encrypted.buffer) < 4000

    def test_buffer_stays_bounded_across_repeated_junk(self, encrypted):
        junk = b"\xe0\xfe" + bytes((i * 7 + 3) % 256 for i in range(4000))
        for _ in range(4):
            frames(encrypted, junk)
        max_scan = 2 + MAX_AES_BLOCKS * 16 + 1
        assert len(encrypted.buffer) <= max_scan + len(junk)

    def test_recovers_and_frames_a_real_message_after_junk(self, encrypted):
        real = make_frame(bytes([0x50, 37]) + b"\x00" * 34)
        junk = b"\xe0\xfe" + b"\x00" * 200
        out = frames(encrypted, junk + real)
        assert real in [f.data for f in out]

    def test_scan_is_bounded_to_max_aes_blocks(self, encrypted):
        # A frame longer than the scan window cannot be found; the framer must
        # resync rather than buffer indefinitely.
        oversized = make_frame(b"\xe0\xfe" + b"\x5a" * (16 * (MAX_AES_BLOCKS + 1)))
        frames(encrypted, oversized)
        assert len(encrypted.buffer) < len(oversized)


class TestReset:
    def test_reset_drops_buffered_bytes(self, plain):
        frames(plain, b"\x50\x25\x00")
        assert len(plain.buffer) == 3
        plain.reset()
        assert len(plain.buffer) == 0
