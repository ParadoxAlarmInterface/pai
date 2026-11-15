from abc import abstractmethod
from collections import defaultdict, namedtuple
from itertools import chain
import logging
from time import time
import typing

from construct import Construct, Container

from paradox.config import config as cfg, get_limits_for_type
from paradox.lib.utils import construct_free, sanitize_key

from ..lib import ps

logger = logging.getLogger("PAI").getChild(__name__)

IndexAddress = namedtuple("IndexAddress", "idx address")


class Panel:
    mem_map = {}  # override in a subclass
    event_map = {}  # override in a subclass
    property_map = {}  # override in a subclass
    max_eeprom_response_data_length = 0  # override in a subclass
    status_request_addresses = []  # override in a subclass
    supports_time_sync = False  # opt in when clock synchronization is implemented

    def __init__(self, core, variable_message_length=True):
        self.core = core
        self.settings = {}
        self.variable_message_length = variable_message_length

    def build_close_connection(self) -> typing.Optional[bytes]:
        """Logout frame sent on teardown, or None if the panel has none."""
        return None

    def parse_message(self, message, direction="topanel") -> typing.Optional[Container]:
        raise NotImplementedError("override parse_message in a subclass")

    def handle_async_message(self, message):
        """Handle protocol-specific unsolicited messages, if any."""

    def on_partition_command(self, partitions, command):
        """Apply protocol-specific state after an accepted partition command."""

    async def send_utility_key(self, key: int) -> bool:
        raise NotImplementedError("Utility keys are not supported by this panel")

    def make_framer(self):
        """A framer to replace the connection's default one, or None to keep it."""
        return None

    def get_message(self, name) -> Construct:
        raise ResourceWarning(f"{name} parser not found")

    @staticmethod
    def get_error_message(error_code) -> str:
        return str(error_code)

    async def load_memory(self):
        logger.info("Loading definitions")
        definitions = await self.load_definitions()
        ps.sendMessage("definitions_loaded", data=definitions)

        logger.info("Loading labels")
        labels = await self.load_labels()
        ps.sendMessage("labels_loaded", data=labels)

    async def load_definitions(self):
        if "definitions" not in self.mem_map:
            return {}
        logger.info("Updating Definitions from Panel")

        data = defaultdict(dict)
        try:
            def_parsers = self.get_message("DefinitionsParserMap")

            definitions = self.mem_map["definitions"]
            for elem_type in definitions:
                if elem_type not in def_parsers:
                    logger.warning("No parser for %s definitions", elem_type)
                    continue

                start_time = time()
                parser = def_parsers[elem_type]
                if callable(parser):
                    parser = parser(self.settings)

                assert isinstance(parser, Construct)
                elem_def = definitions[elem_type]
                enabled_indexes = set()

                addresses = enumerate(
                    chain.from_iterable(elem_def["addresses"]), start=1
                )

                async for index, raw_data in self._eeprom_batch_reader(
                    addresses, parser.sizeof()
                ):
                    element = parser.parse(raw_data)

                    if cfg.LOGGING_DUMP_MESSAGES:
                        logger.debug(f"EEPROM parsed ({elem_type}/{index}): {element}")
                    if elem_def.get("bit_encoded"):
                        for elem_index, elem_data in element.items():
                            definition = elem_data.get("definition")
                            data_index = (index - 1) * len(element) + elem_index
                            data[elem_type][data_index] = elem_data
                            if definition != "disabled":
                                enabled_indexes.add(data_index)
                    else:
                        data[elem_type][index] = element
                        definition = element.get("definition")
                        if definition != "disabled":
                            enabled_indexes.add(index)

                cfg.LIMITS[elem_type] = get_limits_for_type(
                    elem_type, list(enabled_indexes)
                )
                cfg.LIMITS[elem_type] = list(
                    set(cfg.LIMITS[elem_type]).intersection(enabled_indexes)
                )

                logger.info(
                    f"{elem_type.title()} definitions loaded ({round(time() - start_time, 2)}s)"
                )

        except ResourceWarning:
            pass

        return construct_free(data)

    async def load_labels(self):
        logger.info("Updating Labels from Panel")

        data = defaultdict(dict)

        for elem_type in self.mem_map["labels"]:
            start_time = time()
            elem_def = self.mem_map["labels"][elem_type]

            addresses = enumerate(chain.from_iterable(elem_def["addresses"]), start=1)
            limits = get_limits_for_type(elem_type)
            if limits is not None:
                addresses = iter((i, a) for i, a in addresses if i in limits)

            await self._load_labels(
                data, elem_type, addresses, label_offset=elem_def["label_offset"]
            )

            self.log_labels_loaded(elem_type, data[elem_type], start_time)

        return data

    async def _eeprom_read_address(self, address, length):
        args = dict(address=address, length=length)
        reply = await self.core.send_wait(
            self.get_message("ReadEEPROM"),
            args,
            reply_expected=lambda m: m.fields.value.po.command == 0x5
            and m.fields.value.address == address,
        )

        if reply is None:
            logger.error("Could not fully load labels")
            return

        return reply.fields.value.data

    async def _eeprom_batch_reader(self, addresses, field_length):
        if self.max_eeprom_response_data_length < 1:
            raise AssertionError("Wrong max_eeprom_response_data_length")

        batch = []
        while True:
            send_batch = None
            try:
                ia = IndexAddress(*next(addresses))
                batch_len = len(batch)
                if batch and (
                    (
                        batch[0].address + batch_len * field_length != ia.address
                    )  # Addresses are not sequential
                    or (
                        (batch_len + 1) * field_length
                        > self.max_eeprom_response_data_length
                    )  # one more field will not fit
                ):
                    send_batch = batch
                    batch = []

                batch.append(ia)
            except StopIteration:
                send_batch = batch
                batch = []

            if send_batch is not None:
                request_length = len(send_batch) * field_length
                if request_length == 0:
                    break
                else:
                    data = await self._eeprom_read_address(
                        send_batch[0].address, request_length
                    )
                    for i, ia2 in enumerate(send_batch, start=0):
                        yield ia2.idx, data[i * field_length : (i + 1) * field_length]

    async def _load_labels(
        self,
        data: dict,
        elem_type: str,
        addresses: typing.Iterator[typing.Tuple[int, int]],
        field_length=16,
        label_offset=0,
        template=None,
    ):
        """
        Load labels from panel

        :param data_dict: Dict to fill
        :param addresses: Addresses list with indexes
        :param field_length: Text field length
        :param label_offset: Label offset
        :param template: Default template
        :return:
        """
        element_dict = data[elem_type]

        if template is None:
            template = {}

        async for index, data in self._eeprom_batch_reader(addresses, field_length):
            label = self.decode_label(data[label_offset : label_offset + field_length])
            element_dict[index] = self.label_element(elem_type, index, label, template)

    @staticmethod
    def decode_label(raw: bytes) -> str:
        """Decode a raw label field using cfg.LABEL_ENCODING."""
        b_label = raw.strip(b"\0 ")

        label = b_label.replace(b"\0", b" ")

        try:
            return label.decode(cfg.LABEL_ENCODING)
        except UnicodeDecodeError:
            logger.warning(
                "Unable to properly decode label {} using the {} encoding.\n \
                Specify a different encoding using the LABEL_ENCODING configuration option.".format(
                    b_label, cfg.LABEL_ENCODING
                )
            )
            return label.decode("utf-8", errors="ignore")

    @staticmethod
    def label_element(elem_type: str, index: int, label: str, template=None) -> dict:
        """Element properties (template + id, key, label) for the labels dict."""
        properties = dict(template or {})
        properties["id"] = index
        properties["key"] = sanitize_key(label) or sanitize_key(f"{elem_type} {index}")
        properties["label"] = label
        return properties

    @staticmethod
    def log_labels_loaded(elem_type: str, elements: dict, start_time: float):
        logger.info(
            f"{elem_type.title()} labels loaded ({round(time()-start_time, 2)}s): "
            + f"{', '.join([v['label'] for v in elements.values()])}"
        )

    @abstractmethod
    def initialize_communication(self, password):
        raise NotImplementedError("override initialize_communication in a subclass")

    def get_status_requests(self) -> typing.Iterable[typing.Awaitable]:
        return (self.request_status(i) for i in self.status_request_addresses)

    @abstractmethod
    async def request_status(self, nr) -> typing.Optional[Container]:
        raise NotImplementedError("override request_status in a subclass")

    @staticmethod
    def handle_status(message: Container, parser_map):
        """Handle MessageStatus"""
        mvars = message.fields.value

        if mvars.address not in parser_map:
            logger.warning(
                "Parser for memory address ({}) is not implemented. "
                "Skipping.".format(mvars.address)
            )
            return

        parser = parser_map[mvars.address]
        try:
            res = parser.parse(mvars.data)
            if cfg.LOGGING_DUMP_MESSAGES:
                logger.debug(f"Status parsed({mvars.address}): {res}")
            return res
        except Exception:
            logger.exception(f"Unable to parse RAM Status Block ({mvars.address})")
            return

    @abstractmethod
    def control_zones(self, zones, command) -> bool:
        raise NotImplementedError("override control_zones in a subclass")

    @abstractmethod
    def control_partitions(self, partitions, command) -> bool:
        raise NotImplementedError("override control_partitions in a subclass")

    @abstractmethod
    def control_outputs(self, outputs, command) -> bool:
        raise NotImplementedError("override control_outputs in a subclass")

    @abstractmethod
    def control_module_pgm_outputs(self, module_address, pgm_index, command) -> bool:
        raise NotImplementedError("override control_module_pgm_outputs in a subclass")

    @abstractmethod
    def control_doors(self, doors, command) -> bool:
        raise NotImplementedError("override control_doors in a subclass")

    @abstractmethod
    def dump_memory(self, file, memory_type):
        raise NotImplementedError("override dump_memory in a subclass")

    @abstractmethod
    def send_panic(self, partition, panic_type, user_id):
        raise NotImplementedError("override send_panic in a subclass")
