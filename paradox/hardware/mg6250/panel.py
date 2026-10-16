"""Paradox MG6250 panel support (encrypted link)

Login only: the session is opened, but the 0x24 record protocol (status,
labels, control) is not implemented yet.
"""

import logging
import typing

from construct import (
    Bytes,
    Checksum,
    Const,
    ConstructError,
    Container,
    GreedyBytes,
    Int8ub,
    Int16ul,
    RawCopy,
    Rebuild,
    Struct,
    len_,
    this,
)

from paradox.config import config as cfg
from paradox.connections.serial.encryption import make_serial_key
from paradox.connections.serial.mg6250_framing import (
    CHECKSUM_LEN,
    OVERHEAD,
    MG6250SerialFramer,
    crc16_modbus,
)
from paradox.exceptions import AuthenticationFailed
from paradox.lib.crypto import decrypt as paradox_decrypt
from paradox.lib.crypto import encrypt as paradox_encrypt

from ..panel import Panel as PanelBase

logger = logging.getLogger("PAI").getChild(__name__)

# ---------------------------------------------------------------------------
# Commands (frame bytes 1-2, LE16)
# ---------------------------------------------------------------------------
CMD_IDENTIFY = 0x00  # panel info, then a list that may be supported commands
CMD_LOGIN = 0x01  # login with the PW_BLOCK credential (cleartext)
CMD_DATA = 0x24  # AES-encrypted record protocol (post-login)

# Session id at the start of the body.
SESSION_IDENTIFY = (0x01, 0x02)
SESSION_LOGIN = 0x02

LOGIN_STATUS = {
    0x00: "accepted",
    0x05: "busy (previous session still open)",
    0x81: "rejected: unknown session id",
    0x83: "rejected: unknown user",
    0x84: "rejected: bad PW_BLOCK credential",
    0x85: "busy (previous session still open)",
}

# PW_BLOCK = header | client field(8) | len(pw) | credential(32) | trailer
PW_HEADER = bytes.fromhex("5a0101")
PW_TRAILER = bytes.fromhex("02000100")
DEFAULT_CLIENT_FIELD = bytes.fromhex("0800112233444099")

Frame = Struct(
    "fields"
    / RawCopy(
        Struct(
            "sof" / Const(0xDE, Int8ub),
            "command" / Int16ul,
            "length"
            / Rebuild(
                Int16ul,
                lambda ctx: OVERHEAD
                + len(ctx.field_a)
                + len(ctx.field_b)
                + 1
                + len(ctx.payload),
            ),
            "field_a_length" / Rebuild(Int8ub, len_(this.field_a)),
            "field_b_length" / Rebuild(Int8ub, len_(this.field_b)),
            "field_a" / Bytes(this.field_a_length),
            "field_b" / Bytes(this.field_b_length),
            "session_id" / Int8ub,
            "payload"
            / Bytes(
                this.length - OVERHEAD - this.field_a_length - this.field_b_length - 1
            ),
        )
    ),
    "checksum" / Checksum(Bytes(CHECKSUM_LEN), crc16_modbus, this.fields.data),
)

# Decrypted login reply
LoginResponse = Struct(
    "selector" / Int8ub,
    "mode" / Int8ub,
    "session_key" / Bytes(16),
    "_unknown0" / Bytes(5),
    "label" / Bytes(16),
    "_unknown1" / Bytes(2),
    "padding" / GreedyBytes,
)

PAD = 0xEE  # Paradox padding byte


def credential_block(password: str) -> bytes:
    """32-byte credential: make_serial_key(pw) encrypted under itself."""
    key = make_serial_key(password)
    return paradox_encrypt(key, key)


def build_pw_block(password: str, client_field: bytes = DEFAULT_CLIENT_FIELD) -> bytes:
    return (
        PW_HEADER
        + client_field
        + bytes([len(password)])
        + credential_block(password)
        + PW_TRAILER
    )


def build_frame(command: int, session_id: int, payload: bytes = b"") -> bytes:
    return Frame.build(
        dict(
            fields=dict(
                value=dict(
                    command=command,
                    field_a=b"",
                    field_b=b"",
                    session_id=session_id,
                    payload=payload,
                )
            )
        )
    )


class Panel(PanelBase):
    event_map = {}  # TODO
    property_map = {}  # TODO

    def __init__(
        self, core, start_communication_response=None, variable_message_length=False
    ):
        super().__init__(core, variable_message_length)
        # The MG6250 ignores StartCommunication (0x5F), so connect() passes the
        # InitiateCommunication (0x72) reply here instead.
        if start_communication_response is not None:
            self.settings = start_communication_response.fields.value
        self.session = None  # LoginResponse once logged in
        self.session_key = None  # 16-byte AES key for cmd 0x24 traffic

    def build_data_frame(self, payload: bytes) -> bytes:
        """A 0x24 frame tagged with the session id the login reply assigned."""
        if self.session is None:
            raise RuntimeError("no session; log in first")
        return build_frame(
            CMD_DATA, self.session.selector, bytes([self.session.mode]) + payload
        )

    def make_framer(self):
        return MG6250SerialFramer()

    def parse_message(self, message, direction="topanel") -> typing.Optional[Container]:
        # Legacy identify (0x72) is still handled by the base.
        parent = super().parse_message(message, direction)
        if parent is not None:
            return parent
        if message and message[0] == 0xDE:
            return Frame.parse(message)
        return None

    def decrypt_data(self, payload: bytes):
        """Decrypt a cmd 0x24 payload -> (header, subtype, data)."""
        if self.session_key is None:
            raise RuntimeError("no session key; log in first")
        body = payload[1:]  # skip the mode byte (second session id byte)
        header = self._aes_dec(body[:16])
        if not body[16]:
            return header, None, None
        return header, body[17], self._aes_dec(body[18:])

    def _aes_dec(self, data: bytes) -> bytes:
        n = len(data) // 16 * 16
        return paradox_decrypt(data[:n], self.session_key) if n else b""

    async def initialize_communication(self, password) -> bool:
        """Identify, then log in with the PW_BLOCK credential.

        `password` is the PC password (default "admin"). The username is read
        from cfg.MG6250_USERNAME (default "admin").
        """
        username = getattr(cfg, "MG6250_USERNAME", "admin")

        # identify (0x00) twice: model/firmware, then a list (supported commands?)
        for session_id in SESSION_IDENTIFY:
            await self.core.send_wait(
                message=build_frame(CMD_IDENTIFY, session_id),
                reply_expected=lambda m: m.fields.value.command == CMD_IDENTIFY,
            )

        # credential + length use the PC password; the username is appended.
        pw_block = build_pw_block(password)
        u = username.encode()
        login = build_frame(CMD_LOGIN, SESSION_LOGIN, pw_block + bytes([len(u)]) + u)
        reply = await self.core.send_wait(
            message=login, reply_expected=lambda m: m.fields.value.command == CMD_LOGIN
        )
        if reply is None:
            logger.error("MG6250 login: no reply")
            return False

        status = bytes(reply.fields.value.payload)[:1]
        logger.info(
            "MG6250 login status 0x%02x (%s)",
            status[0],
            LOGIN_STATUS.get(status[0], "unknown"),
        )
        if status != b"\x00":
            raise AuthenticationFailed(
                LOGIN_STATUS.get(status[0], f"status 0x{status[0]:02x}")
            )

        # decrypt the reply with make_serial_key(pw)
        self.session = self._decrypt_login_reply(
            bytes(reply.fields.value.payload), make_serial_key(password)
        )
        if self.session is None:
            logger.error("MG6250 login reply did not decrypt")
            return False
        self.session_key = self.session.session_key
        logger.info(
            "MG6250 session: selector 0x%02x mode 0x%02x user %r",
            self.session.selector,
            self.session.mode,
            self.session.label.decode("ascii", "replace").rstrip(),
        )
        return True

    @staticmethod
    def _decrypt_login_reply(payload: bytes, key: bytes):
        data = payload[1:]  # strip status byte
        missing = -len(data) % 16
        try:
            if missing == 1:
                # Some firmware encrypts a padded block but sends one byte short.
                for guess in range(256):
                    plain = paradox_decrypt(data + bytes([guess]), key)
                    if plain.endswith(bytes([PAD]) * 4):
                        return LoginResponse.parse(plain)
            # Otherwise pad with 0xEE: only the last block, past the session key, comes out garbled.
            return LoginResponse.parse(
                paradox_decrypt(data + bytes([PAD]) * missing, key)
            )
        except ConstructError:
            return None

    # -- record protocol (cmd 0x24): not implemented, login only ----------
    async def load_memory(self):
        logger.warning("MG6250: loading labels and definitions is not supported yet")

    async def request_status(self, nr) -> typing.Optional[Container]:
        logger.warning("MG6250: status requests are not supported yet")
        return None

    async def _not_supported(self, what: str) -> bool:
        logger.warning("MG6250: %s is not supported yet", what)
        return False

    async def control_zones(self, zones, command) -> bool:
        return await self._not_supported("zone control")

    async def control_partitions(self, partitions, command) -> bool:
        return await self._not_supported("partition control")

    async def control_outputs(self, outputs, command) -> bool:
        return await self._not_supported("output control")

    async def control_module_pgm_outputs(
        self, module_address, pgm_index, command
    ) -> bool:
        return await self._not_supported("PGM control")

    async def control_doors(self, doors, command) -> bool:
        return await self._not_supported("door control")

    async def dump_memory(self, file, memory_type):
        return await self._not_supported("memory dump")

    async def send_panic(self, partition, panic_type, user_id):
        return await self._not_supported("panic")
