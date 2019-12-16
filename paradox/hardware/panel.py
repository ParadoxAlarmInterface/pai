import inspect
import logging
import typing
from collections import defaultdict, namedtuple
from itertools import chain

from construct import Construct, Container, EnumIntegerString

from paradox.config import config as cfg
from paradox.lib.utils import sanitize_key
from . import parsers

logger = logging.getLogger('PAI').getChild(__name__)

IndexAddress = namedtuple('IndexAddress', 'idx address')


class Panel:
    mem_map = {}
    event_map = {}
    property_map = {}

    def __init__(self, core, product_id, variable_message_length=True):
        self.core = core
        self.product_id = product_id
        self.variable_message_length = variable_message_length

    def parse_message(self, message, direction='topanel') -> typing.Optional[Container]:
        if message is None or len(message) == 0:
            return None

        if direction == 'topanel':
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
            raise ResourceWarning('{} parser not found'.format(name))

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
        res = [0] * 2

        if password is None or password in [b'0000', '0000', 0]:
            return b'\x00\x00'

        if isinstance(password, int):
            password = str(password).zfill(4)

        if len(password) != 4:
            raise (Exception("Password length must be equal to 4. Got {}".format(len(password))))

        if not password.isdigit():
            raise (Exception("Not supported password {}".format(password)))

        int_password = int(password)
        i = min(4, len(password))
        i2 = i // 2 - 1

        while i > 0:
            b = int(int_password % 10)
            if b == 0:
                b = 0x0a

            int_password = int_password // 10

            if i % 2 == 0:
                res[i2] = b
            else:
                res[i2] = ((b << 4) | res[i2]) & 0xff
                i2 -= 1

            i -= 1

        return bytes(res)

    async def load_definitions(self):
        logger.info("Updating Definitions from Panel")

        data = defaultdict(dict)
        try:
            parsers = self.get_message('DefinitionsParserMap')

            for elem_type in self.mem_map['definitions']:
                if elem_type not in parsers:
                    logger.warning('No parser for %s definitions', elem_type)
                parser = parsers[elem_type]
                assert isinstance(parser, Construct)
                elem_def = self.mem_map['definitions'][elem_type]

                addresses = enumerate(chain.from_iterable(elem_def['addresses']), start=1)

                async for index, raw_data in self._eeprom_batch_reader(addresses, parser.sizeof()):
                    data[elem_type][index] = parser.parse(raw_data)
        except ResourceWarning:
            pass

        return data

    async def load_labels(self):
        logger.info("Updating Labels from Panel")

        data = defaultdict(dict)

        for elem_type in self.mem_map['labels']:
            elem_def = self.mem_map['labels'][elem_type]

            addresses = enumerate(chain.from_iterable(elem_def['addresses']), start=1)
            limits = cfg.LIMITS.get(elem_type)
            if limits is not None:
                addresses = iter((i, a) for i, a in addresses if i in limits)

            await self._load_labels(data[elem_type], addresses, label_offset=elem_def['label_offset'])

            logger.info("{}: {}".format(elem_type.title(), ', '.join([v["label"] for v in data[elem_type].values()])))

        return data

    async def _eeprom_read_address(self, address, length):
        args = dict(address=address, length=length)
        reply = await self.core.send_wait(self.get_message('ReadEEPROM'), args, reply_expected=lambda
            m: m.fields.value.po.command == 0x05 and m.fields.value.address == address)

        if reply is None:
            logger.error("Could not fully load labels")
            return

        return reply.fields.value.data

    async def _eeprom_batch_reader(self, addresses, field_length, max_request_length=64):
        batch = []
        while True:
            send_batch = None
            try:
                ia = IndexAddress(*next(addresses))
                if batch and (
                        (batch[0].address + len(batch) * field_length != ia.address)  # Addresses are not sequential
                        or ((len(batch) + 1) * field_length > max_request_length)  # one more field will not fit
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
                    data = await self._eeprom_read_address(send_batch[0].address, request_length)
                    for i, ia2 in enumerate(send_batch, start=0):
                        yield ia2.idx, data[i * field_length:(i + 1) * field_length]

    async def _load_labels(self,
                           data_dict: dict,
                           addresses: typing.Iterator[typing.Tuple[int, int]],
                           field_length=16,
                           label_offset=0,
                           template=None):
        """
        Load labels from panel

        :param data_dict: Dict to fill
        :param addresses: Addresses list with indexes
        :param field_length: Text field length
        :param label_offset: Label offset
        :param template: Default template
        :return:
        """
        if template is None:
            template = {}

        async for index, data in self._eeprom_batch_reader(addresses, field_length):
            b_label = data[label_offset:label_offset + field_length].strip(b'\0 ')

            label = b_label.replace(b'\0', b' ')

            try:
                label = label.decode(cfg.LABEL_ENCODING)
            except UnicodeDecodeError:
                logger.warning('Unable to properly decode label {} using the {} encoding.\n \
                    Specify a different encoding using the LABEL_ENCODING configuration option.'.format(b_label,
                                                                                                        cfg.LABEL_ENCODING))
                label = label.decode('utf-8', errors='ignore')

            properties = template.copy()
            properties['id'] = index
            properties['key'] = sanitize_key(label)
            properties['label'] = label
            data_dict[index] = properties

    def initialize_communication(self, reply, password):
        raise NotImplementedError("override initialize_communication in a subclass")

    def request_status(self, nr):
        raise NotImplementedError("override request_status in a subclass")

    def handle_status(self, message: Container, parser_map):
        """Handle MessageStatus"""
        mvars = message.fields.value

        if mvars.address not in parser_map:
            logger.error(
                "Parser for memory address ({}) is not implemented. Please review your STATUS_REQUESTS setting. "
                "Skipping.".format(mvars.address)
            )
            return

        parser = parser_map[mvars.address]
        try:
            return parser.parse(mvars.data)
        except Exception:
            logger.exception("Unable to parse RAM Status Block ({})".format(mvars.address))
            return

    def control_zones(self, zones, command) -> bool:
        raise NotImplementedError("override control_zones in a subclass")

    def control_partitions(self, partitions, command) -> bool:
        raise NotImplementedError("override control_partitions in a subclass")

    def control_outputs(self, outputs, command) -> bool:
        raise NotImplementedError("override control_outputs in a subclass")

    def dump_memory(self):
        raise NotImplementedError("override dump_memory in a subclass")


