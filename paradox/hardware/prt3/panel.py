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
    "arm_sleep":   "I",   # instant arm (no entry delay) — PRT3 closest to HA arm_night
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
        # Warn if the configured zone count means each poll cycle could exceed
        # half of KEEP_ALIVE_INTERVAL (in the worst-case all-timeout scenario).
        if cfg.PRT3_MAX_ZONES * cfg.IO_TIMEOUT > cfg.KEEP_ALIVE_INTERVAL / 2:
            logger.warning(
                "PRT3: polling %d zones at %.1f s timeout may take up to %.0f s per "
                "cycle (KEEP_ALIVE_INTERVAL=%d s) — consider reducing PRT3_MAX_ZONES",
                cfg.PRT3_MAX_ZONES,
                cfg.IO_TIMEOUT,
                cfg.PRT3_MAX_ZONES * cfg.IO_TIMEOUT,
                cfg.KEEP_ALIVE_INTERVAL,
            )

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
        retries: int = 1,
    ):
        """
        Write a PRT3 command and await a matching reply.

        Serialization: the entire retry loop runs under ``core.request_lock``
        so no other command can interleave between a send and its expected
        reply, and no other command can interleave between retry attempts.

        :param command_bytes: Encoded command bytes (\\r-terminated).
        :param predicate:     callable(PRT3Message) → bool.  The first
                              message for which this returns True is returned.
        :param timeout:       Override the default IO_TIMEOUT.
        :param retries:       Total attempts (1 = no retry, 2 = one retry…).
                              Retries are only performed on timeout; a received
                              reply (ok or &fail) is returned immediately.
        :returns:             Matching PRT3Message, or None if all attempts
                              timed out.
        """
        _timeout = timeout if timeout is not None else cfg.IO_TIMEOUT
        async with self.core.request_lock:
            for attempt in range(1, retries + 1):
                self.core.connection.write(command_bytes)
                try:
                    return await self.core.connection.wait_for_message(
                        predicate, timeout=_timeout
                    )
                except asyncio.TimeoutError:
                    if attempt < retries:
                        logger.warning(
                            "PRT3: timeout on attempt %d/%d, retrying: %r",
                            attempt, retries, command_bytes,
                        )
            return None

    # ------------------------------------------------------------------
    # Startup handshake
    # ------------------------------------------------------------------

    async def initialize_communication(self, password) -> bool:
        """
        Verify the PRT3 serial link is live.

        The PRT3 module emits ``COMM&ok\\r`` only on its own power-up or when
        the EVO panel reconnects to the module's combus — NOT when the host
        opens the serial port.  If the module was already running before PAI
        started, ``COMM&ok`` was sent before we opened the port and will never
        be re-sent.

        Strategy:
        1. Listen briefly (2 s) for spontaneous data (events or COMM&ok).
           If the module is live, something usually arrives quickly.
        2. If nothing spontaneous, send RA001 (area 1 status probe) and wait
           for any response (ok, &fail, or CommStatus).
        3. Accept any PRT3 message as proof that the link is live.
        4. Return False only on hard failure: COMM&fail (panel not talking to
           PRT3 module) or complete silence after PRT3_COMM_TIMEOUT.

        The ``password`` argument is accepted for interface compatibility but
        ignored — PRT3 has no password exchange.
        """
        from paradox.hardware.prt3.parser import PRT3SystemEvent

        _any_prt3_msg = lambda m: isinstance(
            m, (PRT3CommStatus, PRT3AreaStatus, PRT3ZoneStatus, PRT3LabelReply,
                PRT3CommandEcho, PRT3SystemEvent)
        )

        logger.info("PRT3: checking serial link liveness")

        # Phase 1: brief listen for spontaneous data (events, COMM&ok etc.)
        try:
            msg = await self.core.connection.wait_for_message(
                _any_prt3_msg, timeout=2.0
            )
            if isinstance(msg, PRT3CommStatus) and not msg.ok:
                logger.error("PRT3: panel communication failure (COMM&fail)")
                return False
            logger.info("PRT3: serial link live (spontaneous: %s)", type(msg).__name__)
            return True
        except asyncio.TimeoutError:
            pass  # nothing spontaneous — fall through to probe

        # Phase 2: probe with RA001 and wait for any response
        logger.info("PRT3: no spontaneous data; sending RA001 probe")
        probe = encoder.encode_area_status_request(1)
        self.core.connection.write(probe)
        try:
            msg = await self.core.connection.wait_for_message(
                _any_prt3_msg,
                timeout=max(cfg.PRT3_COMM_TIMEOUT - 2.0, 3.0),
            )
            if isinstance(msg, PRT3CommStatus) and not msg.ok:
                logger.error("PRT3: panel communication failure (COMM&fail)")
                return False
            logger.info("PRT3: serial link live (probe response: %s)", type(msg).__name__)
            return True
        except asyncio.TimeoutError:
            logger.error(
                "PRT3: serial link unresponsive after %.0fs probe", cfg.PRT3_COMM_TIMEOUT
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

    async def _load_label_range(
        self, element_type: str, max_count: int, cmd_fn, prefix: str
    ) -> list:
        """Fetch labels for one element type (area/zone/user) via ASCII commands."""
        replies = []
        for i in range(1, max_count + 1):
            cmd = cmd_fn(i)
            expected_cmd = f"{prefix}{i:03d}"
            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_cmd, et=element_type, idx=i: (
                    (isinstance(m, PRT3LabelReply) and m.element_type == et and m.index == idx)
                    or (isinstance(m, PRT3CommandEcho) and m.cmd == ec)
                ),
            )
            if isinstance(msg, PRT3LabelReply):
                replies.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: %s %d label not found", element_type, i)
            elif msg is None:
                logger.warning("PRT3: timeout loading %s %d label", element_type, i)
        return replies

    async def load_labels(self) -> dict:
        """
        Request area, zone, and user labels via AL/ZL/UL ASCII commands.

        Sends commands one-by-one and collects PRT3LabelReply messages.
        A command that returns PRT3CommandEcho(&fail) means the element
        doesn't exist and is silently skipped.

        Returns a labels dict compatible with Paradox._on_labels_load().
        """
        logger.info("PRT3: loading labels")
        replies = (
            await self._load_label_range("area", cfg.PRT3_MAX_AREAS, encoder.encode_area_label_request, "AL")
            + await self._load_label_range("zone", cfg.PRT3_MAX_ZONES, encoder.encode_zone_label_request, "ZL")
            + await self._load_label_range("user", cfg.PRT3_MAX_USERS, encoder.encode_user_label_request, "UL")
        )
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

    async def _poll_area_statuses(self) -> list:
        """Poll RA{nnn} for all configured areas; return PRT3AreaStatus list."""
        msgs = []
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
                msgs.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: area %d status not found", area)
            elif msg is None:
                logger.warning("PRT3: timeout polling area %d status", area)
        return msgs

    async def _poll_zone_statuses(self) -> list:
        """Poll RZ{nnn} for all configured zones; return PRT3ZoneStatus list."""
        msgs = []
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
                msgs.append(msg)
            elif isinstance(msg, PRT3CommandEcho) and not msg.ok:
                logger.debug("PRT3: zone %d status not found", zone)
            elif msg is None:
                logger.warning("PRT3: timeout polling zone %d status", zone)
        return msgs

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
        area_msgs = await self._poll_area_statuses()
        zone_msgs = await self._poll_zone_statuses()
        return adapter.build_flat_status(area_msgs, zone_msgs)

    # ------------------------------------------------------------------
    # Control — partitions
    # ------------------------------------------------------------------

    def _build_partition_cmd(
        self, partition: int, command: str, user_code: str
    ) -> Optional[tuple]:
        """
        Build (cmd_bytes, expected_echo) for one partition command.

        Returns None and logs an error when the command cannot be sent
        (unknown command, or disarm without a user code).
        """
        if command == "disarm":
            if not user_code:
                logger.error("PRT3: disarm requires PRT3_USER_CODE to be configured")
                return None
            return encoder.encode_disarm(partition, user_code), f"AD{partition:03d}"

        if command in _QUICK_ARM_MODES:
            mode = _QUICK_ARM_MODES[command]
            if user_code:
                return encoder.encode_arm(partition, mode, user_code), f"AA{partition:03d}"
            return encoder.encode_quick_arm(partition, mode), f"AQ{partition:03d}"

        logger.error("PRT3: unknown partition command %r", command)
        return None

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
            built = self._build_partition_cmd(partition, command, user_code)
            if built is None:
                continue
            cmd, expected_echo = built
            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_echo: (
                    isinstance(m, PRT3CommandEcho) and m.cmd == ec
                ),
                retries=2,
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

    async def send_panic(self, partitions: list, panic_type: str, _code) -> bool:
        """
        Send a PE/PM/PF panic command.

        :param partitions: list of 1-based area numbers (1-8).
        :param panic_type: 'emergency', 'medical', or 'fire'.
        :param _code:      Not used by PRT3 (panic commands carry no code).
        """
        encode_fn = _PANIC_ENCODERS.get(panic_type)
        if encode_fn is None:
            logger.error("PRT3: unknown panic type %r", panic_type)
            return False

        accepted = False
        for partition in partitions:
            cmd = encode_fn(partition)
            expected_echo = f"{cmd[:2].decode('ascii')}{partition:03d}"

            msg = await self._prt3_send_wait(
                cmd,
                lambda m, ec=expected_echo: (
                    isinstance(m, PRT3CommandEcho) and m.cmd == ec
                ),
                retries=2,
            )
            if msg is None:
                logger.warning("PRT3: timeout on %s panic area %d", panic_type, partition)
                continue
            if not msg.ok:
                logger.warning(
                    "PRT3: %s panic area %d rejected (&fail)", panic_type, partition
                )
                continue
            logger.info("PRT3: %s panic area %d accepted", panic_type, partition)
            accepted = True
        return accepted

    # ------------------------------------------------------------------
    # Utility key
    # ------------------------------------------------------------------

    async def send_utility_key(self, key: int) -> bool:
        """
        Send a ``UK{nnn}\\r`` utility key command.

        Utility keys (1-251) trigger actions programmed into the panel
        (scene activations, output toggles, etc.).  The panel echoes
        ``UK{nnn}&OK`` on success or ``UK{nnn}&fail`` if the key is not
        programmed.

        :param key: Utility key number, 1-251.
        :returns:   True if the panel accepted the command, False otherwise.
        :raises ValueError: if *key* is out of range (from encoder).
        """
        cmd = encoder.encode_utility_key(key)
        expected_echo = f"UK{key:03d}"
        msg = await self._prt3_send_wait(
            cmd,
            lambda m, ec=expected_echo: (
                isinstance(m, PRT3CommandEcho) and m.cmd == ec
            ),
            retries=1,  # no retry — utility keys are not idempotent (gate toggles)
        )
        if msg is None:
            logger.warning("PRT3: timeout on utility key %d", key)
            return False
        if not msg.ok:
            logger.warning("PRT3: utility key %d rejected by panel (&fail)", key)
            return False
        logger.info("PRT3: utility key %d accepted", key)
        return True
