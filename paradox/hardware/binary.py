import asyncio
import binascii
from binascii import hexlify
import inspect
import logging

from construct import Container, EnumIntegerString

from paradox.config import config as cfg
from paradox.data.model import DetectedPanel
from paradox.exceptions import PanelNotDetected
from paradox.lib.utils import describe_connection

from . import parsers
from .panel import Panel

logger = logging.getLogger("PAI").getChild(__name__)


class BinaryPanel(Panel):
    """Shared legacy binary protocol, including its identification exchange."""

    supports_time_sync = True

    @staticmethod
    async def detect(core, panel_factory, products):
        bootstrap = BinaryPanel(core)
        core.install_panel(bootstrap)
        try:
            initiate_reply = await core.send_wait(
                bootstrap.get_message("InitiateCommunication"),
                None,
                reply_expected=0x7,
            )
        except asyncio.TimeoutError:
            return None

        if not initiate_reply:
            raise ConnectionError("Panel did not replied to InitiateCommunication")

        value = initiate_reply.fields.value
        identity = DetectedPanel(
            product_id=None,
            model=value.label.strip(b"\0 ").decode(cfg.LABEL_ENCODING),
            firmware_version="{}.{} build {}".format(
                value.application.version,
                value.application.revision,
                value.application.build,
            ),
            serial_number=hexlify(value.serial_number).decode(),
        )
        logger.info(
            "Connected via %s to %s version %s",
            describe_connection(),
            identity.model,
            identity.firmware_version,
        )

        await core.connection.on_initiate_communication(
            initiate_reply,
            lambda message, check: core.send_wait(
                message=message, reply_expected=check
            ),
        )

        driver = products.get(value.get("product_id"))
        start_class = driver[0] if driver else BinaryPanel
        reply = await start_class.start_communication(core, initiate_reply)
        if reply.fields.value.product_id is None:
            raise PanelNotDetected("Failed to detect panel")

        panel = panel_factory(core, reply)
        core.install_panel(panel)
        return panel, identity._replace(product_id=reply.fields.value.product_id)

    @classmethod
    async def start_communication(cls, core, initiate_reply: Container) -> Container:
        logger.info("Initiating panel connection")
        reply = await core.send_wait(
            parsers.StartCommunication,
            args={"source_id": core.connection.start_communication_source_id},
            reply_expected=0x0,
        )
        if reply is None:
            raise ConnectionError("Panel did not replied to StartCommunication")
        return reply

    def build_close_connection(self):
        return self.get_message("CloseConnection").build({})

    async def set_time(self, now):
        args = dict(
            century=int(now.year / 100),
            year=int(now.year % 100),
            month=now.month,
            day=now.day,
            hour=now.hour,
            minute=now.minute,
        )
        reply = await self.core.send_wait(
            self.get_message("SetTimeDate"), args, reply_expected=0x3, timeout=10
        )
        return reply is not None

    def parse_message(self, message, direction="topanel"):
        if message is None or len(message) < 2:
            return None
        if message[0] >> 4 == 0xE and message[1] == 0xFE:
            return parsers.Encrypted.parse(message)
        if direction == "topanel":
            if message[0] == 0x72 and message[1] == 0:
                return parsers.InitiateCommunication.parse(message)
            elif message[0] == 0x5F:
                return parsers.StartCommunication.parse(message)
        else:
            if message[0] == 0x72 and message[1] == 0xFF:
                return parsers.InitiateCommunicationResponse.parse(message)
            elif message[0] == 0x00 and message[4] > 0:
                return parsers.StartCommunicationResponse.parse(message)
        return None

    def get_message(self, name):
        clsmembers = dict(inspect.getmembers(parsers))
        if name in clsmembers:
            return clsmembers[name]
        raise ResourceWarning(f"{name} parser not found")

    @staticmethod
    def get_error_message(error_code) -> str:
        error_str = str(error_code)
        if isinstance(error_code, EnumIntegerString):
            error_code = int(error_code)

        if error_code == 0x00:
            message = "Requested command did not work"
        elif error_code == 0x01:
            message = "User Code is invalid"
        elif error_code == 0x02:
            message = "Partition in code lockout (too many bad entries)"
        elif error_code == 0x05:
            message = "Panel will disconnect"
        elif error_code == 0x10:
            message = "Panel Not connected"
        elif error_code == 0x11:
            message = "Panel Already Connected"
        elif error_code == 0x12:
            message = "Invalid PC Password"
        elif error_code == 0x13:
            message = "Winload on phone line"
        elif error_code == 0x14:
            message = "Invalid Module address"
        elif error_code == 0x15:
            message = "Cannot write in RAM"
        elif error_code == 0x16:
            message = "Request to Upgrade Failed"
        elif error_code == 0x17:
            message = "Record number out of range"
        elif error_code == 0x19:
            message = "Invalid record type"
        elif error_code == 0x1A:
            message = "Multi-Bus not supported"
        elif error_code == 0x1B:
            message = "Incorrect number of users"
        elif error_code == 0x1C:
            message = "Invalid label number"
        else:
            if isinstance(error_code, int):
                message = f"{error_str} (0x{error_code:02X})"
            else:
                message = error_str

        return message

    @staticmethod
    def encode_password(password) -> bytes:
        if password is None:
            password = 0

        if isinstance(password, int):
            password = str(password).zfill(4)
        elif isinstance(password, str):
            password = password.encode()

        return binascii.a2b_hex(password.zfill(4))
