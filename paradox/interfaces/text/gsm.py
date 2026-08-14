import asyncio
import json
import logging

from paradox.config import config as cfg
from paradox.connections.gsm.connection import GsmSerialConnection
from paradox.event import EventLevel, Notification
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface
from paradox.lib import ps

# GSM interface.
# Only exposes critical status changes and accepts commands

logger = logging.getLogger("PAI").getChild(__name__)


class GSMTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using GSM"""

    def __init__(self, alarm):
        super().__init__(
            alarm,
            cfg.GSM_EVENT_FILTERS,
            cfg.GSM_ALLOW_EVENTS,
            cfg.GSM_IGNORE_EVENTS,
            cfg.GSM_MIN_EVENT_LEVEL,
        )

        self.port = None
        self.modem_connected = False
        self.message_cmt = None

    def stop(self):
        """Stops the GSM Interface"""
        super().stop()

        if self.port is not None:
            # stop() is synchronous, so the close can only be scheduled. The
            # port is dropped either way: a half-closed port is still better
            # than one held open for the life of the process.
            port, self.port = self.port, None
            self.modem_connected = False
            self._loop.create_task(port.close())

        logger.debug("GSM Stopped")

    async def write(self, message: str, expected: str = None) -> None:
        r = b""
        while r != expected:
            r = await self.port.send_command(message)
            data = b""

            if r == b"ERROR":
                raise Exception(f"Got error from modem: {r}")

            while r != expected:
                r = await self.port.read()
                data += r + b"\n"

    async def connect(self):
        logger.info(f"Using {cfg.GSM_MODEM_PORT} at {cfg.GSM_MODEM_BAUDRATE} baud")
        self.port = GsmSerialConnection(cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE, 5)

        self.port.set_recv_callback(None)
        result = await self.port.connect()

        if not result:
            logger.error("Could not connect to GSM modem")
            return False

        try:
            await self.write(b"AT", b"OK")  # Init
            await self.write(b"ATE0", b"OK")  # Disable Echo
            await self.write(b"AT+CMEE=2", b"OK")  # Increase verbosity
            await self.write(b"AT+CMGF=1", b"OK")  # SMS Text mode
            await self.write(b"AT+CFUN=1", b"OK")  # Enable modem
            await self.write(
                b"AT+CNMI=1,2,0,0,0", b"OK"
            )  # SMS received only when modem enabled, Use +CMT with SMS, No Status Report,
            await self.write(b"AT+CUSD=1", b"OK")  # Enable result code presentation

        except asyncio.TimeoutError:
            logger.error("No reply from modem")
            return False

        except Exception:
            logger.exception("Modem connect error")
            return False

        self.port.set_recv_callback(
            self.data_received
        )  # Set recv callback to handle future messages

        logger.debug("Modem connected")
        self.modem_connected = True
        return True

    async def run(self):
        await super().run()

        while not self.modem_connected:
            if not await self.connect():
                logger.warning("Could not connect to modem")

            await asyncio.sleep(5)

    def data_received(self, raw: bytes) -> bool:
        logger.debug(f"Data Received: {raw}")

        try:
            data = raw.decode()
        except UnicodeDecodeError:
            logger.warning("Discarding undecodable modem line: %r", raw)
            self.message_cmt = None
            return True

        if data.startswith("+CMT"):
            self.message_cmt = data
        elif self.message_cmt is not None:
            # Clear before parsing: a header left in place after a failure
            # would capture every following line as its SMS body.
            header, self.message_cmt = self.message_cmt, None
            try:
                self.process_cmt(header, data)
            except (ValueError, IndexError):
                logger.warning("Discarding malformed +CMT message: %r", header)
        elif data.startswith("+CUSD:"):
            try:
                self.process_cusd(data)
            except (ValueError, IndexError):
                logger.warning("Discarding malformed +CUSD message: %r", data)

        return True

    async def handle_message(self, timestamp: str, source: str, message: str) -> None:
        """Handle GSM message. It should be a command"""

        logger.debug(f"Received: {timestamp} {source} {message}")

        if source in cfg.GSM_CONTACTS:
            ret = await self.handle_command(message)

            m = f"GSM {source}: {ret}"
            logger.info(m)
        else:
            m = f"GSM {source} (UNK): {message}"
            logger.warning(m)

        self.send_message(m, EventLevel.INFO)
        ps.sendNotification(
            Notification(sender=self.name, message=m, level=EventLevel.INFO)
        )

    async def send_message(self, message: str, level: EventLevel) -> None:
        if self.port is None:
            logger.warning("GSM not available when sending message")
            return

        for dst in cfg.GSM_CONTACTS:
            data = b'AT+CMGS="%b"\x0d%b\x1a' % (dst.encode(), message.encode())

            try:
                result = await self.port.send_command(data)
                logger.debug(f"SMS result: {result}")
            except Exception:
                logger.exception("ERROR sending SMS")

    def process_cmt(self, header: str, text: str) -> None:
        idx = header.find(" ")
        if idx <= 0:
            return

        tokens = json.loads(f"[{header[idx:]}]", strict=False)

        logger.debug(f"On {tokens[2]}, {tokens[0]} sent {text}")
        asyncio.create_task(self.handle_message(tokens[2], tokens[0], text))

    def process_cusd(self, message: str) -> None:
        idx = message.find(" ")
        if idx < 0:
            return

        tokens = json.loads(f"[{message[idx:]}]", strict=False)

        code = tokens[0]
        if code == 1:
            logger.info("Modem registered into network")
            ps.sendNotification(
                Notification(
                    sender=self.name,
                    message="Modem registered into network",
                    level=EventLevel.INFO,
                )
            )
        elif code == 4:
            logger.warning("CUSD code not supported")
            return
        else:
            return
