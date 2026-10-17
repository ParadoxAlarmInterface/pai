from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BLOCK_SIZE = 16
PADDING = b"\xee"


def _transpose_blocks(data: bytes) -> bytes:
    """Convert each AES state between Paradox row order and AES column order."""
    return b"".join(
        data[offset + row : offset + BLOCK_SIZE : 4]
        for offset in range(0, len(data), BLOCK_SIZE)
        for row in range(4)
    )


def _cipher(key: bytes) -> Cipher:
    if not key:
        # The legacy key schedule rejected empty keys, even for empty messages.
        raise IndexError("index out of range")
    return Cipher(algorithms.AES(bytes(key[:32]).ljust(32, PADDING)), modes.ECB())


def encrypt(ctxt, key):
    """Encrypt with Paradox AES-256-ECB, padding partial blocks with 0xEE."""
    data = bytes(ctxt)
    data += PADDING * (-len(data) % BLOCK_SIZE)
    encryptor = _cipher(key).encryptor()
    encrypted = encryptor.update(_transpose_blocks(data)) + encryptor.finalize()
    return _transpose_blocks(encrypted)


def decrypt(ctxt, key):
    """Decrypt full blocks, retaining 0xEE padding and ignoring a partial tail."""
    decryptor = _cipher(key).decryptor()
    data = bytes(ctxt)
    data = data[: len(data) - len(data) % BLOCK_SIZE]
    decrypted = decryptor.update(_transpose_blocks(data)) + decryptor.finalize()
    return _transpose_blocks(decrypted)


def encrypt_serial_message(payload: bytes, key) -> bytes:
    """Wrap a serial message payload in an encrypted E0 FE frame.

    Uses Paradox custom AES-256-ECB. Output format matches the ESP32 IP150 emulator:
        [0xE0 | (payload[0] & 0x0F)][0xFE][AES-256(padded_payload)][checksum]

    There is no length byte — the frame boundary is determined by timeout on the
    receiving end (matching the panel's own framing behaviour).

    Args:
        payload: raw serial message bytes (e.g. a 37-byte InitiateCommunication)
        key: PC password bytes; padded to 32 bytes with 0xEE if shorter

    Returns:
        Complete E0 FE encrypted serial frame ready to write to the serial port.
    """
    if not payload:
        return b""
    encrypted = encrypt(payload, key)
    frame = bytearray([0xE0 | (payload[0] & 0x0F), 0xFE]) + bytearray(encrypted)
    checksum_byte = sum(frame) % 256
    frame.append(checksum_byte)
    return bytes(frame)


def decrypt_serial_message(frame: bytes, key) -> bytes:
    """Decrypt an E0 FE serial frame and return the original payload.

    Expects the ESP32-compatible format: [E0|x][FE][AES_blocks...][checksum]
    (no length byte at position [2]).

    Args:
        frame: raw E0 FE frame bytes (as received from the serial port)
        key: PC password bytes; padded to 32 bytes with 0xEE if shorter

    Returns:
        Decrypted payload bytes with trailing 0xEE padding stripped.
        Returns b"" if the frame is too short or contains no full AES blocks.
    """
    if len(frame) < 4 or frame[0] >> 4 != 0xE or frame[1] != 0xFE:
        return b""
    # Full-AES frames: total = 2 + n*16 + 1  =>  (len - 3) must be a multiple of 16.
    # BabyWare compact frames do NOT satisfy this — reject them early.
    if (len(frame) - 3) % 16 != 0:
        return b""
    # Verify the E0 FE checksum (sum of all bytes except last) before decrypting.
    if sum(frame[:-1]) % 256 != frame[-1]:
        return b""
    enc_data = frame[2:-1]  # Guaranteed to be a multiple of 16 bytes
    decrypted = decrypt(enc_data, key)
    return decrypted.rstrip(b"\xee")
