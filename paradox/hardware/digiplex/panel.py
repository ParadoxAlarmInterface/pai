from binascii import hexlify
import hashlib
from collections import defaultdict
import asyncio
import inspect
import logging
import time
import typing

from construct import Construct, Container

from paradox.config import config as cfg, get_limits_for_type
from paradox.data.model import DetectedPanel
from paradox.exceptions import AuthenticationFailed, StatusRequestException
from paradox.lib.utils import describe_connection

from . import parsers
from ..panel import Panel as PanelBase
from .adapters import PARTITION_COUNT
from .property import RAMDataParserMap, property_map

logger = logging.getLogger("PAI").getChild(__name__)

DIGIPLEX_PRODUCTS = ("DIGIPLEX_v13", "DIGIPLEX_v2", "DIGIPLEX_NE")

# How many bytes to request per status block (READ count, 1..32).
STATUS_READ_LENGTHS = {
    0x8153: 12,  # zones 1-48 + tamper 1-48
    0x8185: 32,  # 0x0185..0x01A4 (partition status blocks at 0x0195)
    0x800B: 3,  # PSU / battery voltages
}

# Zones 1-48 (DGP-848). Where the NE96 keeps zones 49-96 is not known.
ZONES = 48

# EEPROM: zone label table (16 byte slots, \0 separates words).
# Verified live on 2026-10-24: z.1='vaiku rytu lang.' ... z.48='gaisras'.
ZONE_LABELS_BASE = 0x2000

# The panel releases a stale PC session only after ~15-25 s of line silence.
SESSION_RELEASE_SILENCE = 30
DETECT_DEADLINE = 120


class PanelDGP848(PanelBase):
    """Paradox Digiplex panel (DGP-48 / DGP-848 / DGP-NE96).

    Protocol facts (all verified live against a DGP-848, firmware A095):

    - The panel ignores InitiateCommunication (0x72) and identifies itself in
      the StartCommunication (0x5F) response. Only ``source_id=0`` is accepted.
    - Login echoes that response with the PC password (BCD) in bytes [8..9].
    - The panel never broadcasts; status is polled from RAM (READ 0x5x).
    - Only one PC session at a time. After a connection loss the panel keeps
      the session and releases it only after ~15-25 s of absolute line silence
      - every request, even a rejected one, resets that timer. Retries must
      therefore be slow (see detect()).
    """

    property_map = property_map

    # Fixed 37 byte frames
    # (variable_message_length=False is passed by create_panel)

    # EEPROM label layout is unknown for this family; labels are synthesized
    # in load_labels() instead (same approach as the PRT3 panel).
    mem_map = {}

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
        # Zones / partitions published by this installation (see load_labels)
        self._zones: set = set()
        self._partitions: set = set()
        # Last published partition state, for change-only logging
        self._last_partitions: dict | None = None

        if self.settings.get("product_id") == "DIGIPLEX_NE":
            logger.warning(
                "Digiplex NE: only zones 1-%d and partitions 1-%d are supported, "
                "the memory map beyond these is not known",
                ZONES,
                PARTITION_COUNT,
            )

    @classmethod
    async def detect(cls, core):
        """Discovery when InitiateCommunication went unanswered (issue #257).

        The panel identifies itself in the StartCommunication response, which
        it only accepts with source_id=0. A reply other than 0x0 means the
        panel still holds a previous session; it is released only after line
        silence, so retries are slow and silent.
        """
        core.install_panel(cls(core))
        reply = await cls._wait_for_session(core)

        value = reply.fields.value
        if value.product_id not in DIGIPLEX_PRODUCTS:
            raise ConnectionError(
                "Unsupported Digiplex product_id: %s" % value.product_id
            )

        serial_number = hexlify(value.serial_number).decode()
        if not any(value.serial_number):
            # Recorded panels report no serial: derive a stable per-installation
            # identity so two panels on one MQTT broker do not merge.
            digest = hashlib.sha256(describe_connection().encode()).hexdigest()
            serial_number = f"digiplex_{digest[:8]}"

        panel = cls(core, reply)
        core.install_panel(panel)
        return panel, DetectedPanel(
            product_id=value.product_id,
            model="Digiplex DGP",
            firmware_version="{}.{} build {:#06x}".format(
                value.firmware.version, value.firmware.revision, value.firmware_build
            ),
            serial_number=serial_number,
        )

    @staticmethod
    async def _wait_for_session(core):
        """Send StartCommunication until the panel accepts it (command 0x00)."""
        deadline = time.monotonic() + DETECT_DEADLINE
        while True:
            try:
                reply = await core.send_wait(
                    parsers.StartCommunication,
                    args={"source_id": 0},
                    reply_expected=[0x0, 0x7],
                    retries=1,
                )
            except asyncio.TimeoutError:
                reply = None

            if reply is not None and reply.fields.value.po.command == 0x0:
                return reply

            if reply is None:
                logger.info(
                    "Digiplex panel did not reply. Waiting %ds before retry",
                    SESSION_RELEASE_SILENCE,
                )
            else:
                logger.info(
                    "Digiplex panel reports a busy session. Waiting %ds of "
                    "line silence for the panel to release it",
                    SESSION_RELEASE_SILENCE,
                )

            if time.monotonic() + SESSION_RELEASE_SILENCE >= deadline:
                raise ConnectionError("Panel did not release its previous session")
            await asyncio.sleep(SESSION_RELEASE_SILENCE)

    def build_close_connection(self):
        # No logout command: the generic CloseConnection frame is an error
        # and would reset the panel's session release timer.
        return None

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
        dump).

        The zone definition layout of this family is unknown, so which zones
        are in use cannot be read from the panel: zones 1-48 are published
        unless ``LIMITS["zone"]`` restricts them. Unlabelled zones get a
        "Zone <n>" fallback; their keys are allocated after the labelled
        zones, so a fallback never changes the key of a labelled zone.
        Partitions 1-2 are published unless ``LIMITS["partition"]`` restricts
        them; ``DIGIPLEX_PARTITION_NAMES`` only supplies their labels.
        """
        data = defaultdict(dict)
        raw = bytearray()
        failed = set()
        for base in range(ZONE_LABELS_BASE, ZONE_LABELS_BASE + ZONES * 16, 32):
            chunk = await self._read_eeprom(base, 32)
            if len(chunk) != 32:
                first = (base - ZONE_LABELS_BASE) // 16 + 1
                failed.update((first, first + 1))
                chunk = bytes(32)
            raw.extend(chunk)

        labels = {
            i: self.decode_label(bytes(raw[(i - 1) * 16 : i * 16])).strip()
            for i in range(1, ZONES + 1)
        }
        # A failed read on reconnect keeps the zone already published (key
        # reserved first), so its MQTT topics do not change.
        known = self.core.storage.get_container("zone")
        elements = {}
        for i in failed & set(known):
            elements[i] = self.label_element("zone", i, known[i]["label"])
            elements[i]["key"] = known[i]["key"]

        # Keys are allocated over all zones (labelled first) before LIMITS is
        # applied, so neither fallbacks nor LIMITS change a labelled zone's key.
        rest = [i for i in range(1, ZONES + 1) if i not in elements]
        named = [i for i in rest if labels[i]]
        unnamed = [i for i in rest if not labels[i]]
        for i in named + unnamed:
            elements[i] = self.label_element("zone", i, labels[i])
            elements[i]["label"] = labels[i] or f"Zone {i}"
        self._make_keys_unique(elements.values())

        for i in self._selected("zone", ZONES):
            data["zone"][i] = elements[i]
        self._zones = set(data["zone"])

        partition_names = {
            int(k): v for k, v in (cfg.DIGIPLEX_PARTITION_NAMES or {}).items()
        }
        partition_elements = {
            i: self.label_element(
                "partition", i, partition_names.get(i) or f"Partition {i}"
            )
            for i in range(1, PARTITION_COUNT + 1)
        }
        self._make_keys_unique(partition_elements.values())
        for i in self._selected("partition", PARTITION_COUNT, partition_names):
            data["partition"][i] = partition_elements[i]
        self._partitions = set(data["partition"])

        logger.info(
            "Digiplex: labels loaded from EEPROM - zones %s, partitions %s",
            sorted(self._zones),
            sorted(self._partitions),
        )
        return dict(data)

    @staticmethod
    def _make_keys_unique(elements) -> None:
        """Suffix a key already taken by an earlier element with the element
        ID (e.g. zones 7 and 24 are both 'garazo vartai' -> 'garazo_vartai_24')."""
        keys = set()  # case-insensitive: HA lowercases entity IDs
        for element in elements:
            while element["key"].lower() in keys:
                element["key"] = f"{element['key']}_{element['id']}"
            keys.add(element["key"].lower())

    @staticmethod
    def _selected(elem_type: str, supported: int, configured=()) -> list:
        """IDs 1..supported, restricted by ``LIMITS[elem_type]``. Configured IDs
        beyond what this driver reads are reported instead of silently dropped."""
        selected = get_limits_for_type(elem_type, list(range(1, supported + 1)))
        unsupported = sorted(
            {i for i in [*selected, *configured] if not 1 <= i <= supported}
        )
        if unsupported:
            logger.warning(
                "Digiplex: %s %s not supported (only 1-%d are read)",
                elem_type,
                unsupported,
                supported,
            )
        return sorted({i for i in selected if 1 <= i <= supported})

    async def _read_eeprom(self, address: int, count: int) -> bytes:
        """EEPROM read (address without the 0x8000 bit). A longer timeout is
        used because EEPROM reads are occasionally slow; on failure an empty
        result is returned."""
        try:
            reply = await self.core.send_wait(
                message=parsers.build_read_ram(address, count),
                reply_expected=lambda m, a=address: m.fields.value.po.command == 0x5
                and m.fields.value.address == a,
                timeout=3.0,
                retries=2,
            )
        except asyncio.TimeoutError:
            logger.warning("Digiplex EEPROM read at %#x timed out", address)
            return b""
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

        self._keep_published(result)
        self._log_partition_changes(result)
        return result

    def _keep_published(self, result):
        """Publish only the zones and partitions selected in load_labels().

        Tamper is published for every published zone.
        """
        selections = (
            ("zone_open", self._zones),
            ("zone_tamper", self._zones),
            ("partition_status", self._partitions),
        )
        for key, published in selections:
            if key in result:
                result[key] = {i: v for i, v in result[key].items() if i in published}

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

        try:
            selected = [int(partition) for partition in partitions]
        except (TypeError, ValueError):
            logger.warning("Invalid Digiplex partition selection: %r", partitions)
            return False
        if not selected or any(
            not 1 <= partition <= PARTITION_COUNT for partition in selected
        ):
            logger.warning(
                "Unsupported Digiplex partition selection: %r (supported: 1-%d)",
                partitions,
                PARTITION_COUNT,
            )
            return False

        message = parsers.build_partition_action(dict.fromkeys(selected, code))
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


# Keep the original name available for integrations importing it directly.
Panel_DGP848 = PanelDGP848
