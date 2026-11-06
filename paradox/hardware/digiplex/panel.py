from collections import defaultdict
import inspect
import logging
import typing

from construct import Construct, Container

from paradox.exceptions import AuthenticationFailed, StatusRequestException
from paradox.lib.utils import sanitize_key

from . import parsers
from ..panel import Panel as PanelBase
from .adapters import publishes_tamper, zone_device_class
from .property import RAMDataParserMap, property_map

logger = logging.getLogger("PAI").getChild(__name__)

DIGIPLEX_PRODUCTS = ("DIGIPLEX_v13", "DIGIPLEX_v2", "DIGIPLEX_NE")

# How many bytes to request per status block (READ count, 1..32).
STATUS_READ_LENGTHS = {
    0x8153: 12,  # zones 1-48 + tamper 1-48
    0x8185: 32,  # 0x0185..0x01A4 (partition status blocks at 0x0195)
    0x800B: 3,  # PSU / battery voltages
}

ZONES = 48  # DGP-848 has 48 on-board zones

# EEPROM: zone label table (16 byte slots, \0 separates words).
# Verified live on 2026-10-24: z.1='vaiku rytu lang.' ... z.48='gaisras'.
ZONE_LABELS_BASE = 0x2000


class Panel_DGP848(PanelBase):
    """Paradox Digiplex panel (DGP-48 / DGP-848 / DGP-NE96).

    Protocol facts (all verified live against a DGP-848, firmware A095):

    - The panel ignores InitiateCommunication (0x72) and identifies itself in
      the StartCommunication (0x5F) response. Only ``source_id=0`` is accepted.
    - Login echoes that response with the PC password (BCD) in bytes [8..9].
    - The panel never broadcasts; status is polled from RAM (READ 0x5x).
    - Only one PC session at a time. After a connection loss the panel keeps
      the session and releases it only after ~15-25 s of absolute line silence
      - every request, even a rejected one, resets that timer. Retries must
      therefore be slow (see Paradox._digiplex_connect).
    """

    property_map = property_map

    # Fixed 37 byte frames
    # (variable_message_length=False is passed by create_panel)

    # EEPROM label layout is unknown for this family; labels are synthesized
    # in load_labels() instead (same approach as the PRT3 panel).
    mem_map = {}

    # Digiplex has no logout command; sending the generic CloseConnection
    # frame would be an error and would reset the panel's session timer.
    close_connection_supported = False

    def __init__(
        self, core, start_communication_response=None, variable_message_length=False
    ):
        super().__init__(core, variable_message_length)

        self.settings = (
            start_communication_response.fields.value
            if start_communication_response is not None
            else Container()
        )
        # Keep the raw init response: the login frame is built by echoing it.
        self.init_response_raw = (
            bytes(start_communication_response.fields.data)
            if start_communication_response is not None
            else b""
        )
        # Zones that have a label (really used by this installation)
        self._named_zones: set = set()
        # Zone number -> device_class, used for tamper filtering
        self._zone_device_class: dict = {}
        # Last published partition state, for change-only logging
        self._last_partitions: dict | None = None

    @property
    def status_request_addresses(self):
        return list(STATUS_READ_LENGTHS.keys())

    def get_message(self, name: str) -> Construct:
        try:
            clsmembers = dict(inspect.getmembers(parsers))
            if name in clsmembers:
                return clsmembers[name]
        except ResourceWarning:
            pass

        return super().get_message(name)

    def parse_message(
        self, message: bytes, direction="topanel"
    ) -> typing.Optional[Container]:
        if message is None or len(message) < 2:
            return None

        if direction == "frompanel":
            # NOTE: the init response has product_id 0 (DIGIPLEX_v13), which
            # the generic Panel.parse_message rejects ("message[4] > 0") -
            # issue #257 root cause number two.
            if message[0] == 0x00:
                return parsers.StartCommunicationResponse.parse(message)
            if message[0] >> 4 == 0x1:
                return parsers.InitializeCommunicationResponse.parse(message)
            if message[0] >> 4 == 0x7:
                return parsers.ErrorMessage.parse(message)
            if message[0] >> 4 == 0x5:
                return parsers.ReadRAMResponse.parse(message)

            # 0x4 = MONITOR response (the panel echoes the command frame)
            if message[0] >> 4 == 0x4:
                return parsers.PerformPartitionAction.parse(message)

            # 0xE = event frames. We do not interpret them yet (offsets still
            # being confirmed) - just log the raw bytes so a single keypad
            # action reveals the real layout.
            if message[0] >> 4 == 0xE:
                logger.info("Digiplex: event frame %s", message.hex(" "))
                return parsers.EventResponse.parse(message)

        return super().parse_message(message, direction)

    async def initialize_communication(self, password) -> bool:
        """Digiplex login: echo the init response with the PC password (BCD)
        in bytes [8..9]. Verified live - no installer code is needed."""
        if not self.init_response_raw:
            logger.error("Digiplex login impossible: no StartCommunication response")
            return False

        payload = parsers.build_login(
            self.init_response_raw, self.encode_password(password)
        )
        reply = await self.core.send_wait(message=payload, reply_expected=[0x1, 0x7])

        if reply is None:
            logger.error("Digiplex login failed: no reply")
            return False

        if reply.fields.value.po.command == 0x1:
            logger.info("Authentication Success")
            return True

        error = self.get_error_message(reply.fields.value.message)
        logger.error("Digiplex login rejected: %s", error)
        raise AuthenticationFailed("Wrong PASSWORD")

    async def load_definitions(self) -> dict:
        """The DGP EEPROM definition layout is unknown; no definitions."""
        return {}

    async def load_labels(self) -> dict:
        """Zone labels are read straight from EEPROM (verified live):
        16 byte slots starting at 0x2000, \0 separates words (e.g.
        'vaiku\\0pietu\\0lang'). Read in 32 byte blocks (two zones per block),
        which proved the most reliable way (no timeouts during the EEPROM
        dump). Zones without a label are skipped - they are not assigned.
        """
        data = defaultdict(dict)
        raw = bytearray()
        for base in range(ZONE_LABELS_BASE, ZONE_LABELS_BASE + ZONES * 16, 32):
            chunk = await self._read_eeprom(base, 32)
            raw.extend(chunk if len(chunk) == 32 else bytes(32))

        keys = set()
        for i in range(1, ZONES + 1):
            slot = bytes(raw[(i - 1) * 16 : i * 16])
            label = slot.replace(b"\x00", b" ").decode("ascii", "replace").strip()
            if not label:
                continue  # unassigned zone (empty EEPROM slot) - skip it
            key = sanitize_key(label) or f"zone_{i}"
            if key in keys:  # e.g. zones 7 and 24 are both 'garazo vartai'
                key = f"{key}_{i}"
            keys.add(key)
            data["zone"][i] = {
                "id": i,
                "key": key,
                "label": label,
                "device_class": zone_device_class(label),
            }
        self._named_zones = set(data["zone"].keys())
        self._zone_device_class = {
            i: info["device_class"] for i, info in data["zone"].items()
        }
        for i, name in ((1, "Namas"), (2, "Garažas")):
            data["partition"][i] = {"id": i, "key": sanitize_key(name), "label": name}

        logger.info("Digiplex: labels loaded from EEPROM — %d named zones", len(keys))
        return dict(data)

    async def _read_eeprom(self, address: int, count: int) -> bytes:
        """EEPROM read (address without the 0x8000 bit). A longer timeout is
        used because EEPROM reads are occasionally slow; on failure an empty
        result is returned."""
        reply = await self.core.send_wait(
            message=parsers.build_read_ram(address, count),
            reply_expected=lambda m, a=address: m.fields.value.po.command == 0x5
            and m.fields.value.address == a,
            timeout=3.0,
            retries=2,
        )
        return reply.fields.value.data[:count] if reply is not None else b""

    async def request_status(self, nr: int):
        count = STATUS_READ_LENGTHS[nr]
        reply = await self.core.send_wait(
            message=parsers.build_read_ram(nr, count),
            reply_expected=lambda m, a=nr: m.fields.value.po.command == 0x5
            and m.fields.value.address == a,
            timeout=2.0,  # weak WiFi link: latency spikes up to ~1 s
            retries=2,  # fewer retries means fewer late replies
        )
        if reply is None:
            raise StatusRequestException("No reply to status request: %#x" % nr)

        result = self.handle_status(reply, RAMDataParserMap)
        if result is None:
            return None

        self._keep_published_zones(result)
        self._log_partition_changes(result)
        return result

    def _keep_published_zones(self, result):
        """Publish only what the panel actually has.

        Zones without an EEPROM label are not assigned, and tamper is only
        reported for zone types that have a tamper switch (motion, glass
        break, siren/cabinet); contacts and the fire detector would just add
        noise.
        """
        if not self._named_zones:
            return

        for k in ("zone_open", "zone_tamper"):
            if k in result:
                result[k] = {
                    i: v for i, v in result[k].items() if i in self._named_zones
                }

        if "zone_tamper" in result:
            result["zone_tamper"] = {
                i: v
                for i, v in result["zone_tamper"].items()
                if publishes_tamper(self._zone_device_class.get(i, "motion"))
            }

    def _log_partition_changes(self, result):
        """Log partition changes only when they happen, so the add-on log
        alone shows every arm/disarm without extra tooling."""
        if "partition_status" not in result:
            return

        partitions = {
            key: self._partition_state(value)
            for key, value in result["partition_status"].items()
        }
        if partitions != self._last_partitions:
            logger.info("Digiplex: partitions %s", partitions)
            self._last_partitions = partitions

    @staticmethod
    def _partition_state(value) -> str:
        if not value.get("arm"):
            return "disarmed"
        return "perimeter" if value.get("arm_stay") else "armed"

    # control_zones / control_outputs / send_panic / dump_memory stay
    # NotImplementedError: the PGM/siren command set of this family is not
    # documented yet (control of partitions is implemented above).

    async def control_partitions(self, partitions: list, command: str) -> bool:
        """Arm/disarm partitions via the MONITOR (0x40) frame.

        The panel answers with an echo of the frame; an ErrorMessage (0x70)
        means the command was rejected.
        """
        code = parsers.PARTITION_ACTION_COMMANDS.get(command)
        if code is None:
            logger.warning('Partition command "%s" is not supported', command)
            return False

        message = parsers.build_partition_action(
            {int(partition): code for partition in partitions}
        )
        reply = await self.core.send_wait(
            message=message,
            reply_expected=[0x4, 0x7],
            timeout=2.0,
            retries=1,
        )

        if reply is None:
            logger.warning('Partition command "%s" failed: no reply', command)
            return False

        if reply.fields.value.po.command == 0x7:
            error = self.get_error_message(reply.fields.value.message)
            logger.warning('Partition command "%s" rejected: %s', command, error)
            return False

        logger.info(
            'Partition command "%s" accepted for partitions %s', command, partitions
        )
        return True
