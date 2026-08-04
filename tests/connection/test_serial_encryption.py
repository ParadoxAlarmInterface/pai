from paradox.connections.serial.encryption import make_serial_key
from paradox.lib.crypto import decrypt_serial_message, encrypt_serial_message

# PC password "1234" padded to 32 bytes with 0xEE
PC_PASSWORD = b"1234"


def test_roundtrip_37byte_message():
    """Encrypting and decrypting a 37-byte message recovers the original."""
    payload = bytes([0x72] + [0x00] * 35 + [0x72])  # InitiateCommunication
    frame = encrypt_serial_message(payload, PC_PASSWORD)
    recovered = decrypt_serial_message(frame, PC_PASSWORD)
    assert recovered == payload


def test_roundtrip_8byte_message():
    """Encrypting and decrypting an 8-byte message recovers the original."""
    payload = bytes([0x50, 0x08, 0x00, 0x00, 0x00, 0x00, 0x40, 0x98])
    frame = encrypt_serial_message(payload, PC_PASSWORD)
    recovered = decrypt_serial_message(frame, PC_PASSWORD)
    assert recovered == payload


def test_encrypted_frame_starts_with_e0_fe():
    """E0 FE frames must start with 0xE0|cmd_nibble and 0xFE."""
    payload = bytes([0x72] + [0x00] * 35 + [0x72])
    frame = encrypt_serial_message(payload, PC_PASSWORD)
    assert frame[0] >> 4 == 0xE
    assert frame[1] == 0xFE


def test_encrypted_frame_checksum():
    """Checksum byte must equal sum of all preceding bytes mod 256."""
    payload = bytes([0x72] + [0x00] * 35 + [0x72])
    frame = encrypt_serial_message(payload, PC_PASSWORD)
    expected = sum(frame[:-1]) % 256
    assert frame[-1] == expected


def test_decrypt_empty_returns_empty():
    assert decrypt_serial_message(b"", PC_PASSWORD) == b""


def test_decrypt_short_frame_returns_empty():
    assert decrypt_serial_message(b"\xe0\xfe\x00", PC_PASSWORD) == b""


def test_encrypted_frame_size():
    """Frame length must be 2 (header) + ceil(payload/16)*16 (AES) + 1 (checksum)."""
    payload = bytes([0x72] + [0x00] * 35 + [0x72])  # 37 bytes → 3 blocks = 48 AES bytes
    frame = encrypt_serial_message(payload, PC_PASSWORD)
    expected_aes_bytes = ((len(payload) + 15) // 16) * 16
    assert len(frame) == 2 + expected_aes_bytes + 1


# ── BabyWare compact frames from PR #337 (EVO192 v7.70) ─────────────────────
# decrypt_serial_message must return b"" for all BabyWare compact frames,
# even those large enough that the old code would attempt AES decryption.

_PR337_BABYWARE_FRAMES = [
    # 13-byte TX (already rejected by old code — regression)
    bytes.fromhex("E0FE0D0001A55FA8E417009304"),
    # 27-byte TX (old code returned 16B garbage)
    bytes.fromhex("E0FE1B0000B3FEB64AFF82D038F4157335C5BEB5591970FC00FA0C"),
    # 36-byte RX (old code returned 32B garbage)
    bytes.fromhex(
        "E0FE2400052BFDCC0E388E81F7DC0DFC06BE6EE3" "4E2988DD57DD959BB8470AAF9300CC10"
    ),
    # 47-byte TX (old code returned 32B garbage)
    bytes.fromhex(
        "E0FE2F00002BA0369BE25752FD2D15F305D72FB5"
        "591960FC6BF3CC76B88E81F7D449FC06BE6EE34E"
        "2988DD5700B316"
    ),
    # 50-byte RX (main regression: old code returned 32B garbage)
    bytes.fromhex(
        "E0FE320001A5EFACC53587247F2FAADB054142"
        "7D2003497ABE670B8D1516A4D369136BA83259"
        "DE9424525BFABA4571003A14"
    ),
]


def test_decrypt_returns_empty_for_babyware_compact_frames():
    """BabyWare compact E0 FE frames from PR #337 must return b'' (never garbage)."""
    key = b"0000" + b"\xee" * 28
    for frame in _PR337_BABYWARE_FRAMES:
        result = decrypt_serial_message(frame, key)
        assert (
            result == b""
        ), f"{len(frame)}-byte BabyWare compact frame: expected b'' but got {len(result)}B"


# ── make_serial_key: integer password zero-padding ──────────────────────────


def test_make_serial_key_int_zero_pads_to_4_digits():
    """Integer passwords must be zero-padded to 4 digits before encoding."""
    assert make_serial_key(0)[:4] == b"0000"
    assert make_serial_key(1)[:4] == b"0001"
    assert make_serial_key(100)[:4] == b"0100"
    assert make_serial_key(1234)[:4] == b"1234"


def test_make_serial_key_string_unchanged():
    """String passwords are encoded as-is."""
    assert make_serial_key("1234")[:4] == b"1234"
    assert make_serial_key("abcd")[:4] == b"abcd"


def test_make_serial_key_always_32_bytes():
    """Key is always padded to exactly 32 bytes with 0xEE."""
    for pw in [0, 1, 1234, "1234", b"1234"]:
        key = make_serial_key(pw)
        assert len(key) == 32
        assert key[4:] == b"\xee" * 28
