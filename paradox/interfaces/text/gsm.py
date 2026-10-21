import asyncio
import json
import logging

from paradox.config import config as cfg
from paradox.connections.gsm.connection import (
    DEFAULT_COMMAND_TIMEOUT,
    GsmSerialConnection,
)
from paradox.connections.gsm.protocol import PROMPT
from paradox.event import EventLevel, Notification
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface
from paradox.lib import ps

# GSM interface.
# Only exposes critical status changes and accepts commands

logger = logging.getLogger("PAI").getChild(__name__)

#: Ends an SMS body and hands it to the modem for sending.
CTRL_Z = b"\x1a"

#: Abandons SMS entry mode without sending.
ESC = b"\x1b"

#: Delivery to the network can be slow on a weak signal.
SMS_SEND_TIMEOUT = 60

MODEM_POLL_INTERVAL = 5

#: Error result codes. Everything else the modem emits before OK is informational.
ERRORS = (b"ERROR", b"+CME ERROR", b"+CMS ERROR")


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

        # The modem answers one command at a time and the reply queue cannot
        # tell two callers apart, so every exchange is serialised here rather
        # than in the transport -- an SMS spans several transport calls.
        self._command_lock = asyncio.Lock()
        self._send_tasks = set()

    def stop(self):
        """Stops the GSM Interface"""
        super().stop()

        for task in self._send_tasks:
            task.cancel()

        if self.port is not None:
            # stop() is synchronous, so the close can only be scheduled. The
            # port is dropped either way: a half-closed port is still better
            # than one held open for the life of the process.
            port, self.port = self.port, None
            self.modem_connected = False
            self._loop.create_task(port.close())

        logger.debug("GSM Stopped")

    async def _at_command(
        self, command: bytes, timeout=DEFAULT_COMMAND_TIMEOUT
    ) -> bytes:
        """Send one AT command and wait for its final result code."""
        logger.debug("I->M: %s", command)
        self.port.clear()
        self.port.write(command)
        return await self._read_final_result(timeout)

    async def connect(self):
        logger.info(f"Using {cfg.GSM_MODEM_PORT} at {cfg.GSM_MODEM_BAUDRATE} baud")

        await self._close_port()
        self.port = GsmSerialConnection(cfg.GSM_MODEM_PORT, cfg.GSM_MODEM_BAUDRATE, 5)

        self.port.set_recv_callback(None)
        result = await self.port.connect()

        if not result:
            logger.error("Could not connect to GSM modem")
            return False

        try:
            # Held across the whole sequence: a half-initialised modem must not
            # see an SMS interleaved between these commands.
            async with self._command_lock:
                await self._at_command(b"AT")
                await self._at_command(b"ATE0")  # Disable Echo
                await self._at_command(b"AT+CMEE=2")  # Increase verbosity
                await self._at_command(b"AT+CMGF=1")  # SMS Text mode
                await self._at_command(b"AT+CFUN=1")  # Enable modem
                # SMS delivered only while the modem is enabled, body carried
                # in +CMT, no status report.
                await self._at_command(b"AT+CNMI=1,2,0,0,0")
                await self._at_command(b"AT+CUSD=1")  # Result code presentation

        except asyncio.TimeoutError:
            logger.error("No reply from modem")
            return False

        except Exception:
            logger.exception("Modem connect error")
            return False

        self.port.set_recv_callback(self.data_received)

        logger.debug("Modem connected")
        self.modem_connected = True
        return True

    async def _close_port(self) -> None:
        """Drop the previous port, so a retry does not leak the last attempt."""
        if self.port is None:
            return

        port, self.port = self.port, None
        self.modem_connected = False
        try:
            await port.close()
        except Exception:
            logger.exception("Error closing GSM modem port")

    async def run(self):
        await super().run()

        while True:
            if self.modem_connected and not self.port.connected:
                # on_connection_loss only clears the transport's own flag, so
                # the interface has to notice the drop and rebuild the port.
                logger.warning("Modem connection lost")
                self.modem_connected = False

            if not self.modem_connected and not await self.connect():
                logger.warning("Could not connect to modem")

            await asyncio.sleep(MODEM_POLL_INTERVAL)

    def data_received(self, raw: bytes) -> bool:
        """Handle an unsolicited modem line.

        Returns whether the line was consumed. Anything declined here is a
        reply to a command in flight and falls through to the connection's
        queue, which is what lets :meth:`_send_sms` see its own responses.
        """
        logger.debug(f"Data Received: {raw}")

        try:
            data = raw.decode()
        except UnicodeDecodeError:
            logger.warning("Discarding undecodable modem line: %r", raw)
            self.message_cmt = None
            return True

        if data.startswith("+CMT"):
            self.message_cmt = data
            return True

        if self.message_cmt is not None:
            # Clear before parsing: a header left in place after a failure
            # would capture every following line as its SMS body.
            header, self.message_cmt = self.message_cmt, None
            try:
                self.process_cmt(header, data)
            except (ValueError, IndexError):
                logger.warning("Discarding malformed +CMT message: %r", header)
            return True

        if data.startswith("+CUSD:"):
            try:
                self.process_cusd(data)
            except (ValueError, IndexError):
                logger.warning("Discarding malformed +CUSD message: %r", data)
            return True

        return False

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

    def send_message(self, message: str, level: EventLevel) -> None:
        """Queue an SMS to every configured contact.

        Synchronous to match :class:`AbstractTextInterface`, which is called
        straight from the pubsub handlers. Declaring this ``async`` made every
        notification build a coroutine that nobody awaited.
        """
        if self.port is None or not self.modem_connected:
            logger.warning("GSM not available when sending message")
            return

        task = self._loop.create_task(self._send_sms_to_contacts(message))
        # Tracked so stop() can cancel them, and so the loop keeps a strong
        # reference: asyncio only holds a weak one.
        self._send_tasks.add(task)
        task.add_done_callback(self._send_tasks.discard)

    async def _send_sms_to_contacts(self, message: str) -> None:
        for dst in cfg.GSM_CONTACTS:
            try:
                await self._send_sms(dst, message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ERROR sending SMS to %s", dst)

    async def _send_sms(self, destination: str, message: str) -> None:
        """Send one text-mode SMS.

        The exchange is two-stage: ``AT+CMGS`` is answered by a ``"> "`` entry
        prompt, and only then does the modem accept the body, terminated by
        Ctrl-Z. Sending both at once leaves the modem sitting in entry mode and
        the message unsent.
        """
        # Held for the whole exchange, not just the command: between the prompt
        # and the Ctrl-Z the modem treats everything written as message text,
        # so a second sender would end up inside this SMS.
        async with self._command_lock:
            logger.debug("I->M: %s", destination)
            self.port.clear()
            self.port.write(b'AT+CMGS="%b"' % destination.encode())
            prompt = await self.port.read(expect_prompt=True)

            if prompt != PROMPT:
                # The modem may still be in entry mode; ESC leaves it cleanly
                # rather than letting the next command become SMS text.
                self.port.write_raw(ESC)
                raise ValueError(f"Modem did not ask for an SMS body: {prompt!r}")

            try:
                self.port.write_raw(message.encode() + CTRL_Z)
                result = await self._read_final_result(SMS_SEND_TIMEOUT)
            except asyncio.TimeoutError:
                self.port.write_raw(ESC)
                raise

        logger.debug(f"SMS to {destination} result: {result}")

    async def _read_final_result(self, timeout: float) -> bytes:
        """Read modem lines until a final result code.

        Sending can take the best part of a minute on a weak network, and the
        modem interleaves informational lines such as ``+CMGS: 42`` before the
        closing ``OK``.
        """

        async def until_final():
            while True:
                line = await self.port.read(timeout=None)
                if line is None:
                    raise ConnectionError("Modem disconnected")
                if line == b"OK":
                    return line
                if line.startswith(ERRORS):
                    raise ValueError(f"Modem rejected the command: {line!r}")

        return await asyncio.wait_for(until_final(), timeout)

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
