"""
PRT3Panel — Panel adapter for the Paradox PRT3 Printer Module.

Implements all Panel abstract methods using the PRT3 ASCII protocol instead
of binary EEPROM reads.  Delegates wire-format parsing to parser.py and
state normalization to adapter.py.

Protocol overview
-----------------
- Startup: await ``COMM&ok\\r`` from the serial port (no password exchange).
- Labels:  poll AL/ZL/UL one-by-one; collect PRT3LabelReply messages.
- Status:  poll RA/RZ one-by-one; collect PRT3AreaStatus / PRT3ZoneStatus.
- Control: send AA/AQ/AD for arm/disarm; PE/PM/PF for panic.
- Events:  async PRT3SystemEvent messages arrive unsolicited; a persistent
           handler in the runtime (follow-up work) dispatches them.

Design constraints
------------------
- Zone bypass has no PRT3 command; control_zones() raises NotImplementedError.
- PGM / output control has no PRT3 command; control_outputs() raises.
- EEPROM reads are not available; load_definitions() returns {}.
- Arm with user code requires PRT3_USER_CODE in config; if absent, quick-arm
  is used (requires One-Touch Arming enabled on the panel).
- Disarm always requires a user code; if PRT3_USER_CODE is not configured,
  disarm commands are rejected with a logged error.

Handler compatibility note
--------------------------
The PAI runtime registers EventMessageHandler and ErrorMessageHandler on the
connection's handler_registry.  Both assert isinstance(data, Container) which
would raise AssertionError when PRT3Message dataclasses are dispatched.
This is fixed by the guarded versions in async_message_manager.py.
Async system events (PRT3SystemEvent) additionally require a persistent
PRT3EventHandler to be registered — this is Phase 3 / runtime wiring work.
"""

import asyncio
import logging
from typing import Optional

from paradox.config import config as cfg
from paradox.hardware.panel import Panel
from paradox.hardware.prt3 import adapter, encoder
from paradox.hardware.prt3.event import EVENT_MAP, PRT3Event
from paradox.hardware.prt3.parser import (
    PRT3AreaStatus,
    PRT3CommandEcho,
    PRT3CommStatus,
    PRT3LabelReply,
    PRT3ZoneStatus,
    parse_line,
)
from paradox.hardware.prt3.property import property_map

logger = logging.getLogger("PAI").getChild(__name__)

# ---------------------------------------------------------------------------
# Partition command → arm encoder mapping
# ---------------------------------------------------------------------------

# Maps PAI command string → (encoder_fn, arm_mode_char)
# All arm variants that don't require a user code use quick-arm.
_QUICK_ARM_MODES = {
    "arm":         "A",   # default arm → away
    "arm_away":    "A",
    "arm_stay":    "S",
    "arm_force":   "F",
    "arm_instant": "I",
}

# Panic type → encoder function
_PANIC_ENCODERS = {
    "emergency": encoder.encode_panic_emergency,
    "medical":   encoder.encode_panic_medical,
    "fire":      encoder.encode_panic_fire,
}


class PRT3Panel(Panel):
    """
    Panel implementation for the PRT3 ASCII serial interface.

    Uses ASCII RA/RZ/AL/ZL/UL commands for status and labels, and
    AA/AQ/AD/PE/PM/PF commands for control.  All EEPROM-based operations
    from the base Panel class are replaced with ASCII equivalents.
    """

    property_map = property_map

    # Single virtual status address: PRT3 has no multi-block EEPROM, so
    # the poll loop calls request_status(0) once per cycle and it polls
    # all configured areas and zones internally.
    status_request_addresses = [0]

    def __init__(self, core):
        # variable_message_length=False: PRT3Protocol.variable_message_length()
        # is a no-op; the Panel base class must not try to manage lengths.
        super().__init__(core, variable_message_length=False)

    # ------------------------------------------------------------------
    # Message parsing
    # ------------------------------------------------------------------

    def parse_message(self, message: bytes, direction="topanel"):
        """
        Decode a raw PRT3 ASCII line (bytes, \\r-included) into a typed
        PRT3Message dataclass.

        Returns None for empty or unparseable input.  parse_line() logs a
        WARNING for unrecognised lines; this method does not raise.
        """
        if not message:
            return None
        try:
            line = message.decode("ascii").rstrip("\r")
        except (UnicodeDecodeError, AttributeError):
            logger.warning("PRT3: non-ASCII message: %r", message)
            return None
        return parse_line(line)

    # ------------------------------------------------------------------
    # Internal request/reply helper
    # ------------------------------------------------------------------

    async def _prt3_send_wait(
        self,
        command_bytes: bytes,
        predicate,
        timeout: Optional[float] = None,
    ):
        """
        Write a PRT3 command and await a matching reply.

        :param command_bytes: Encoded command bytes (\\r-terminated).
        :param predicate:     callable(PRT3Message) → bool.  The first
                              message for which this returns True is returned.
        :param timeout:       Override the default IO_TIMEOUT.
        :returns:             Matching PRT3Message, or None on timeout.
        """
        self.core.connection.write(command_bytes)
        try:
            return await self.core.connection.wait_for_message(
                predicate,
                timeout=timeout if timeout is not None else cfg.IO_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return None

    # ------------------------------------------------------------------
    # Startup handshake
    # ------------------------------------------------------------------

    async def initialize_communication(self, password) -> bool:
        """
        Wait for COMM&ok from the panel.

        The PRT3 module emits 'COMM&ok\\r' shortly after power-on or
        reconnect.  There is no password exchange; the ``password`` argument
        is accepted for interface compatibility but ignored.

        Returns True if COMM&ok is received before the timeout.
        Returns False if COMM&fail arrives first, or on timeout.
        """
        logger.info("PRT3: awaiting COMM&ok from panel")
        try:
            msg = await self.core.connection.wait_for_message(
                lambda m: isinstance(m, PRT3CommStatus),
                timeout=cfg.PRT3_COMM_TIMEOUT,
            )
            if msg.ok:
                logger.info("PRT3: panel ready (COMM&ok)")
                return True
            logger.error("PRT3: panel communication failure (COMM&fail)")
            return False
        except asyncio.TimeoutError:
            logger.error(
                "PRT3: timeout waiting for COMM&ok (%.0fs)", cfg.PRT3_COMM_TIMEOUT
            )
            return False

    # ------------------------------------------------------------------
    # Definitions (EEPROM not available via PRT3)
    # ------------------------------------------------------------------

    async def load_definitions(self) -> dict:
        """PRT3 provides no EEPROM access; return empty definitions."""
        return {}

    # ------------------------------------------------------------------
    # Label loading
    # ------------------------------------------------------------------

    async def load_labels(self) -> dict:
        """
        Request area, zone, and user labels via AL/ZL/UL ASCII commands.

        Sends commands one-by-one and collects PRT3LabelReply messages.
        A command that returns PRT3CommandEcho(&fail) means the element
        doesn't exist and is silently skipped.

        Returns a labels dict compatible with Paradox._on_labels_load().
        """
        logger.info("PRT3: loading labels")
        replies = []

        # Area labels — AL001..AL{max}
        for area in range(1, cfg.PRT3_MAX_AREAS + 1):
            cmd = encoder.encode_area_label_request(area)
            expected_cmd = f"AL{area:03d}"
            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_cmd, a=area: (
                    (isinstance(m, PRT3LabelReply) and m.element_type == "area" and m.index == a)
                    or (isinstance(m, PRT3CommandEcho) and m.cmd == ec)
                ),
            )
            if isinstance(msg, PRT3LabelReply):
                replies.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: area %d label not found (panel returned &fail)", area)
            elif msg is None:
                logger.warning("PRT3: timeout loading area %d label", area)

        # Zone labels — ZL001..ZL{max}
        for zone in range(1, cfg.PRT3_MAX_ZONES + 1):
            cmd = encoder.encode_zone_label_request(zone)
            expected_cmd = f"ZL{zone:03d}"
            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_cmd, z=zone: (
                    (isinstance(m, PRT3LabelReply) and m.element_type == "zone" and m.index == z)
                    or (isinstance(m, PRT3CommandEcho) and m.cmd == ec)
                ),
            )
            if isinstance(msg, PRT3LabelReply):
                replies.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: zone %d label not found", zone)
            elif msg is None:
                logger.warning("PRT3: timeout loading zone %d label", zone)

        # User labels — UL001..UL{max}
        for user in range(1, cfg.PRT3_MAX_USERS + 1):
            cmd = encoder.encode_user_label_request(user)
            expected_cmd = f"UL{user:03d}"
            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_cmd, u=user: (
                    (isinstance(m, PRT3LabelReply) and m.element_type == "user" and m.index == u)
                    or (isinstance(m, PRT3CommandEcho) and m.cmd == ec)
                ),
            )
            if isinstance(msg, PRT3LabelReply):
                replies.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: user %d label not found", user)
            elif msg is None:
                logger.warning("PRT3: timeout loading user %d label", user)

        labels = adapter.labels_dict_from_replies(replies)
        logger.info(
            "PRT3: labels loaded — %d zones, %d partitions, %d users",
            len(labels.get("zone", {})),
            len(labels.get("partition", {})),
            len(labels.get("user", {})),
        )
        return labels

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------

    async def request_status(self, nr: int) -> dict:
        """
        Poll all configured areas and zones.  The ``nr`` argument is ignored
        (PRT3 has no EEPROM address blocks); it is always called with 0
        from the poll loop via status_request_addresses = [0].

        Returns the flat status dict that convert_raw_status() accepts::

            {
              "partition_arm":          {1: True, 2: False},
              "partition_ready_status": {1: True, 2: True},
              ...
              "zone_open":              {1: False, 2: True},
              ...
            }

        Areas or zones that return &fail (don't exist) are silently excluded.
        Timeouts per-element are logged as warnings; the poll loop tolerates
        missing replies via the deep_merge / StatusRequestException path.
        """
        area_msgs = []
        zone_msgs = []

        for area in range(1, cfg.PRT3_MAX_AREAS + 1):
            cmd = encoder.encode_area_status_request(area)
            expected_cmd = f"RA{area:03d}"
            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_cmd, a=area: (
                    (isinstance(m, PRT3AreaStatus) and m.area == a)
                    or (isinstance(m, PRT3CommandEcho) and m.cmd == ec)
                ),
            )
            if isinstance(msg, PRT3AreaStatus):
                area_msgs.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: area %d status not found", area)
            elif msg is None:
                logger.warning("PRT3: timeout polling area %d status", area)

        for zone in range(1, cfg.PRT3_MAX_ZONES + 1):
            cmd = encoder.encode_zone_status_request(zone)
            expected_cmd = f"RZ{zone:03d}"
            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_cmd, z=zone: (
                    (isinstance(m, PRT3ZoneStatus) and m.zone == z)
                    or (isinstance(m, PRT3CommandEcho) and m.cmd == ec)
                ),
            )
            if isinstance(msg, PRT3ZoneStatus):
                zone_msgs.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: zone %d status not found", zone)
            elif msg is None:
                logger.warning("PRT3: timeout polling zone %d status", zone)

        return adapter.build_flat_status(area_msgs, zone_msgs)

    # ------------------------------------------------------------------
    # Control — partitions
    # ------------------------------------------------------------------

    async def control_partitions(self, partitions: list, command: str) -> bool:
        """
        Arm or disarm partitions using AA/AQ/AD commands.

        Arm commands: uses quick-arm (AQ) if PRT3_USER_CODE is not set, or
        arm with code (AA) if PRT3_USER_CODE is configured.  Quick-arm
        requires One-Touch Arming to be enabled in panel programming.

        Disarm: always requires PRT3_USER_CODE; returns False if not set.
        """
        user_code = cfg.PRT3_USER_CODE
        accepted = False

        for partition in partitions:
            if command == "disarm":
                if not user_code:
                    logger.error(
                        "PRT3: disarm requires PRT3_USER_CODE to be configured"
                    )
                    continue
                cmd = encoder.encode_disarm(partition, user_code)
                expected_echo = f"AD{partition:03d}"

            elif command in _QUICK_ARM_MODES:
                mode = _QUICK_ARM_MODES[command]
                if user_code:
                    cmd = encoder.encode_arm(partition, mode, user_code)
                    expected_echo = f"AA{partition:03d}"
                else:
                    cmd = encoder.encode_quick_arm(partition, mode)
                    expected_echo = f"AQ{partition:03d}"

            else:
                logger.error("PRT3: unknown partition command %r", command)
                continue

            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_echo: (
                    isinstance(m, PRT3CommandEcho) and m.cmd == ec
                ),
            )
            if msg is None:
                logger.warning("PRT3: timeout on %s partition %d", command, partition)
            elif msg.ok:
                logger.info("PRT3: %s partition %d accepted", command, partition)
                accepted = True
            else:
                logger.warning(
                    "PRT3: %s partition %d rejected by panel (&fail)", command, partition
                )

        return accepted

    # ------------------------------------------------------------------
    # Control — zones (not supported by PRT3)
    # ------------------------------------------------------------------

    async def control_zones(self, zones: list, command: str) -> bool:
        raise NotImplementedError(
            "PRT3 has no zone bypass command — control_zones() is not supported"
        )

    # ------------------------------------------------------------------
    # Control — outputs (not supported by PRT3)
    # ------------------------------------------------------------------

    async def control_outputs(self, outputs, command) -> bool:
        raise NotImplementedError(
            "PRT3 has no PGM output command — control_outputs() is not supported"
        )

    # ------------------------------------------------------------------
    # Panic
    # ------------------------------------------------------------------

    async def send_panic(self, partition: int, panic_type: str, _code) -> bool:
        """
        Send a PE/PM/PF panic command.

        :param partition:  1-based area number (1-8).
        :param panic_type: 'emergency', 'medical', or 'fire'.
        :param _code:      Not used by PRT3 (panic commands carry no code).
        """
        encode_fn = _PANIC_ENCODERS.get(panic_type)
        if encode_fn is None:
            logger.error("PRT3: unknown panic type %r", panic_type)
            return False

        cmd = encode_fn(partition)
        expected_echo = f"{cmd[:2].decode('ascii')}{partition:03d}"

        msg = await self._prt3_send_wait(
            cmd,
            lambda m, ec=expected_echo: (
                isinstance(m, PRT3CommandEcho) and m.cmd == ec
            ),
        )
        if msg is None:
            logger.warning("PRT3: timeout on %s panic area %d", panic_type, partition)
            return False
        if not msg.ok:
            logger.warning(
                "PRT3: %s panic area %d rejected (&fail)", panic_type, partition
            )
            return False
        logger.info("PRT3: %s panic area %d accepted", panic_type, partition)
        return True
