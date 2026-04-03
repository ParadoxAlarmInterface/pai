"""Transparent AES-256 E0 FE encryption layer for EVO serial connections."""

import logging

from paradox.lib.crypto import encrypt_serial_message

logger = logging.getLogger("PAI").getChild(__name__)


class EncryptedSerialTransport:
    """Wraps a serial transport to transparently encrypt outgoing messages."""

    def __init__(self, transport, key: bytes):
        self._transport = transport
        self._key = key

    def write(self, data: bytes) -> None:
        encrypted = encrypt_serial_message(data, self._key)
        logger.debug(f"SER ENCRYPT: {len(data)}b → {len(encrypted)}b E0FE frame")
        self._transport.write(encrypted)

    def __getattr__(self, name):
        return getattr(self._transport, name)


def make_serial_key(password) -> bytes:
    """Derive the 32-byte serial encryption key from the panel PC password."""
    if isinstance(password, bytes):
        raw = password
    else:
        raw = str(password).encode("utf-8")
    if len(raw) < 32:
        raw = raw + b"\xee" * (32 - len(raw))
    return raw[:32]
