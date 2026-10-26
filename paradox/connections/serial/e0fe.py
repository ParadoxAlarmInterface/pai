"""Codec for the keyless ``E0 FE`` serial wrapping.

Panels that switch the direct serial link to encrypted mode after the identify
exchange wrap every message in this frame::

    E0 FE | LEN (LE16) | SEQ | ENC(prefix + message) | SEED | CK (LE16)

``LEN`` is the whole frame length, ``CK`` the 16-bit sum of every byte before
it. The cipher is a per-byte XOR followed by a bit permutation; both tables are
selected by ``SEQ ^ SEED`` and advance with every byte. There is no key: the
receiver takes ``SEQ`` and ``SEED`` from the frame itself.

The prefix is ``q`` (0x71) for an identify message (``72 FF``) and ``p``
(0x70) for anything else. A transmitted ``q`` message is additionally XORed
with a byte derived from four of its own bytes; a received ``q`` message
arrives without that XOR, so :meth:`E0FECodec.unwrap` does not undo it.

Pure byte handling: no asyncio, no transport.
"""

from typing import Tuple

HEADER = b"\xe0\xfe"

PREFIX_PLAIN = 0x70
PREFIX_IDENTIFY = 0x71

#: ``E0 FE``, LEN, SEQ before the body; SEED and CK after it.
FRAME_OVERHEAD = 8

#: A one-byte message (its own checksum) plus the prefix.
MIN_FRAME_LENGTH = FRAME_OVERHEAD + 2

#: The longest serial message is 71 bytes (``MAX_MESSAGE_LENGTH`` in
#: serial/framing.py), plus the prefix. ``LEN`` is 16-bit, but a framer waits for
#: as many bytes as a header claims, so a tight bound keeps a false ``E0 FE``
#: from holding up real traffic behind it.
MAX_FRAME_LENGTH = FRAME_OVERHEAD + 1 + 71

#: Bit permutation, one row per cipher round: output bit ``i`` of an encrypted
#: byte is bit ``row[i]`` of its input.
PERMUTATION = (
    (2, 7, 4, 5, 0, 3, 1, 6),
    (6, 1, 2, 4, 0, 3, 5, 7),
    (2, 4, 1, 3, 5, 6, 7, 0),
    (3, 2, 6, 1, 0, 4, 7, 5),
    (4, 6, 1, 7, 2, 0, 5, 3),
    (6, 2, 5, 7, 1, 3, 0, 4),
    (1, 5, 6, 0, 3, 7, 4, 2),
)

#: XOR applied to each byte before permuting it.
XOR_TABLE = bytes.fromhex("cdbe722f6966187f5c26bd1277e35d712c90af")


def _permute(value: int, row: Tuple[int, ...]) -> int:
    return sum(1 << i for i, src in enumerate(row) if value & (1 << src))


def _unpermute(value: int, row: Tuple[int, ...]) -> int:
    return sum(1 << src for i, src in enumerate(row) if value & (1 << i))


_ENCRYPT = tuple(bytes(_permute(b, row) for b in range(256)) for row in PERMUTATION)
_DECRYPT = tuple(bytes(_unpermute(b, row) for b in range(256)) for row in PERMUTATION)


def _cipher(data: bytes, seq: int, seed: int, decrypt: bool) -> bytes:
    xor_len = len(XOR_TABLE)
    rounds = len(PERMUTATION)
    t = seq ^ seed
    # Out-of-range start positions fold back by one less than the table size,
    # not modulo it.
    xor_pos = t >> 3
    if xor_pos >= xor_len:
        xor_pos -= xor_len - 1
    round_ = t & 7
    if round_ >= rounds:
        round_ -= rounds - 1

    out = bytearray()
    for b in data:
        if decrypt:
            out.append(_DECRYPT[round_][b] ^ XOR_TABLE[xor_pos])
        else:
            out.append(_ENCRYPT[round_][b ^ XOR_TABLE[xor_pos]])
        xor_pos = (xor_pos + 1) % xor_len
        round_ = (round_ + 1) % rounds
    return bytes(out)


def _checksum_ok(message: bytes) -> bool:
    return bool(message) and sum(message[:-1]) & 0xFF == message[-1]


def is_frame(data: bytes) -> bool:
    """True when ``data`` is one structurally valid ``E0 FE`` frame.

    Checks the header, that ``LEN`` matches the actual length within
    :data:`MIN_FRAME_LENGTH`..:data:`MAX_FRAME_LENGTH`, and the 16-bit checksum.
    The body is not decrypted.
    """
    return (
        MIN_FRAME_LENGTH <= len(data) <= MAX_FRAME_LENGTH
        and data[:2] == HEADER
        and int.from_bytes(data[2:4], "little") == len(data)
        and sum(data[:-2]) & 0xFFFF == int.from_bytes(data[-2:], "little")
    )


class E0FECodec:
    """Wraps and unwraps messages for one serial connection.

    ``seq`` and ``seed`` are shared by both directions: every transmitted frame
    advances ``seq``, and every valid received frame replaces both with its own.
    A link starts at ``seq=0, seed=0``.
    """

    def __init__(self) -> None:
        self.seq = 0
        self.seed = 0

    def wrap(self, message: bytes) -> bytes:
        """Return ``message`` wrapped in a frame, advancing the state.

        The seed is sent unchanged: the receiver reads it from the frame, so
        any value is accepted on the other end.

        Raises ``ValueError`` for a message without a valid 8-bit checksum or
        one too long to frame; the state is then left untouched.
        """
        if not _checksum_ok(message):
            raise ValueError("E0 FE: message checksum mismatch")
        if len(message) + 1 + FRAME_OVERHEAD > MAX_FRAME_LENGTH:
            raise ValueError("E0 FE: message too long (%d bytes)" % len(message))

        if message[:2] == b"\x72\xff":
            if len(message) < 16:
                raise ValueError("E0 FE: identify message too short")
            prefix = PREFIX_IDENTIFY
            key = message[12] ^ message[13] ^ message[14] ^ message[15]
            message = bytes(b ^ key for b in message)
        else:
            prefix = PREFIX_PLAIN

        body = _cipher(bytes([prefix]) + message, self.seq, self.seed, decrypt=False)
        frame = (
            HEADER
            + (len(body) + FRAME_OVERHEAD).to_bytes(2, "little")
            + bytes([self.seq])
            + body
            + bytes([self.seed])
        )
        frame += (sum(frame) & 0xFFFF).to_bytes(2, "little")

        self.seq = (self.seq + 1) & 0xFF
        return frame

    def unwrap(self, frame: bytes) -> bytes:
        """Return the message carried by ``frame`` and adopt its seq/seed.

        Raises ``ValueError`` if the frame structure, either checksum or the
        prefix is invalid; the state is then left untouched.
        """
        if not is_frame(frame):
            raise ValueError("E0 FE: invalid frame")
        seq, seed = frame[4], frame[-3]
        body = _cipher(frame[5:-3], seq, seed, decrypt=True)
        if body[0] not in (PREFIX_PLAIN, PREFIX_IDENTIFY):
            raise ValueError("E0 FE: unknown prefix 0x%02x" % body[0])
        message = body[1:]
        if not _checksum_ok(message):
            raise ValueError("E0 FE: message checksum mismatch")

        self.seq = seq
        self.seed = seed
        return message
