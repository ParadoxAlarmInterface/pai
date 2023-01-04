import binascii
import inspect
import logging
import typing
from abc import abstractmethod
from collections import defaultdict, namedtuple
from itertools import chain
from time import time

from construct import Construct, Container, EnumIntegerString

from paradox.config import config as cfg, get_limits_for_type
from paradox.lib.utils import construct_free, sanitize_key

from ..lib import ps
from . import parsers

logger = logging.getLogger("PAI").getChild(__name__)

IndexAddress = namedtuple("IndexAddress", "idx address")


class Panel:
    mem_map = {}  # override in a subclass
    event_map = {}  # override in a subclass
    property_map = {}  # override in a subclass
    max_eeprom_response_data_length = 0  # override in a subclass
    status_request_addresses = []  # override in a subclass

    def __init__(self, core, variable_message_length=True):
        self.core = core
        self.settings = {}
        self.variable_message_length = variable_message_length

    def parse_message(self, message, direction="topanel") -> typing.Optional[Container]:
        if message is None or len(message) == 0:
            return None

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
            else:
                return None

    def get_message(self, name) -> Construct:
        clsmembers = dict(inspect.getmembers(parsers))
        if name in clsmembers:
            return clsmembers[name]
        else:
            raise ResourceWarning("{} parser not found".format(name))

    @staticmethod
    def get_error_message(error_code) -> str:
        # This is from EVO and may not apply to all panels

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
                if isinstance(parser, typing.Callable):
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

                cfg.LIMITS[elem_type] = get_limits_for_type(elem_type, list(enabled_indexes))
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

            logger.info(
                f"{elem_type.title()} labels loaded ({round(time()-start_time, 2)}s): "
                + f"{', '.join([v['label'] for v in data[elem_type].values()])}"
            )

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
            b_label = data[label_offset : label_offset + field_length].strip(b"\0 ")

            label = b_label.replace(b"\0", b" ")

            try:
                label = label.decode(cfg.LABEL_ENCODING)
            except UnicodeDecodeError:
                logger.warning(
                    "Unable to properly decode label {} using the {} encoding.\n \
                    Specify a different encoding using the LABEL_ENCODING configuration option.".format(
                        b_label, cfg.LABEL_ENCODING
                    )
                )
                label = label.decode("utf-8", errors="ignore")

            properties = template.copy()
            properties["id"] = index
            properties["key"] = sanitize_key(label) or sanitize_key(
                f"{elem_type} {index}"
            )
            properties["label"] = label
            element_dict[index] = properties

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
            logger.error(
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
        except:
            logger.exception(
                "Unable to parse RAM Status Block ({})".format(mvars.address)
            )
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
    def control_doors(self, doors, command) -> bool:
        raise NotImplementedError("override control_doors in a subclass")

    @abstractmethod
    def dump_memory(self, file, memory_type):
        raise NotImplementedError("override dump_memory in a subclass")

    @abstractmethod
    def send_panic(self, partition, panic_type, user_id):
        raise NotImplementedError("override send_panic in a subclass")
