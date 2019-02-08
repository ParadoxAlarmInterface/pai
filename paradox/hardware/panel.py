import inspect
import logging
import sys
from itertools import chain
from typing import Optional

from construct import Construct, Struct, BitStruct, Const, Nibble, Checksum, Padding, Bytes, this, RawCopy, Int8ub, \
    Default, Enum, Flag, BitsInteger, Int16ub, Container

from .common import calculate_checksum, ProductIdEnum, CommunicationSourceIDEnum

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)


def iterate_properties(data):
    if isinstance(data, list):
        for key, value in enumerate(data):
            yield (key, value)
    elif isinstance(data, dict):
        for key, value in data.items():
            if type(key) == str and key.startswith('_'):  # ignore private properties
                continue
            yield (key, value)


class Panel:
    mem_map = {}
    event_map = {}

    def __init__(self, core, product_id):
        self.core = core
        self.product_id = product_id

    def parse_message(self, message) -> Optional[Container]:
        if message is None or len(message) == 0:
            return None

        if message[0] == 0x72 and message[1] == 0:
            return InitiateCommunication.parse(message)
        elif message[0] == 0x72 and message[1] == 0xFF:
            return InitiateCommunicationResponse.parse(message)
        elif message[0] == 0x5F:
            return StartCommunication.parse(message)
        elif message[0] == 0x00 and message[4] > 0:
            return StartCommunicationResponse.parse(message)
        else:
            return None

    def get_message(self, name) -> Construct:
        clsmembers = dict(inspect.getmembers(sys.modules[__name__]))
        if name in clsmembers:
            return clsmembers[name]
        else:
            raise ResourceWarning('{} parser not found'.format(name))

    def encode_password(self, password) -> bytes:
        res = [0] * 2

        if password is None:
            return b'\x00\x00'

        if not password.isdigit():
            return password

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

    def update_labels(self):
        logger.info("Updating Labels from Panel")

        for elem_type in self.mem_map['elements']:
            elem_def = self.mem_map['elements'][elem_type]

            addresses = list(chain.from_iterable(elem_def['addresses']))
            limits = cfg.LIMITS.get(elem_type)
            if limits is not None:
                addresses = [a for i, a in enumerate(addresses) if i + 1 in limits]

            self.load_labels(self.core.data[elem_type],
                             addresses,
                             label_offset=elem_def['label_offset'])

            logger.info("{}: {}".format(elem_type.title(), ', '.join([v["label"] for v in self.core.data[elem_type].values()])))

    def load_labels(self,
                    data_dict,
                    addresses,
                    field_length=16,
                    label_offset=0,
                    template=None):
        """Load labels from panel"""
        index = 1
        if template is None:
            template = {}

        for address in list(addresses):
            args = dict(address=address, length=field_length)
            reply = self.core.send_wait(self.get_message('ReadEEPROM'), args, reply_expected=0x05)

            retry_count = 3
            for retry in range(1, retry_count + 1):
                # Avoid errors due to collision with events. It should not come here as we use reply_expected=0x05
                if reply is None:
                    logger.error("Could not fully load labels")
                    return

                if reply.fields.value.address != address:
                    logger.debug(
                        "EEPROM label addresses do not match (received: %d, requested: %d). Retrying %d of %d" % (
                            reply.fields.value.address, address, retry, retry_count))
                    reply = self.core.send_wait(None, None, reply_expected=0x05)
                    continue

                if retry == retry_count:
                    logger.error('Failed to fetch label at address: %d' % address)

                break

            data = reply.fields.value.data
            b_label = data[label_offset:label_offset + field_length].strip(b'\0 ')

            key = b_label \
                .replace(b'\0', b'_') \
                .replace(b' ', b'_') \
                .replace(b' ', b'_') \
                .decode('utf-8')

            label = b_label \
                .replace(b'\0', b' ') \
                .decode('utf-8')

            properties = template.copy()
            properties['id'] = index
            properties['key'] = key
            properties['label'] = label
            if index not in data_dict:
                data_dict[index] = {}
            data_dict[index].update(properties)

            index += 1

    def process_properties_bulk(self, properties, address):
        if cfg.LOGGING_DUMP_STATUS:
            logger.debug("address: %s, properties: %s", address, properties)

        for key, value in iterate_properties(properties):

            if not isinstance(value, (list, dict)):
                continue

            element_type = key.split('_')[0]
            limit_list = cfg.LIMITS.get(element_type)

            if key in self.core.status_cache and self.core.status_cache[address][key] == value:
                continue
            if address not in self.core.status_cache:
                self.core.status_cache[address] = {}

            self.core.status_cache[address][key] = value
            prop_name = '_'.join(key.split('_')[1:])

            if not prop_name:
                continue

            for i, status in iterate_properties(value):
                if limit_list is None or i in limit_list:
                    if prop_name == 'status':
                        self.core.update_properties(element_type, i, status)
                    else:
                        self.core.update_properties(element_type, i, {prop_name: status})

    def initialize_communication(self, reply, password):
        raise NotImplementedError("override initialize_communication in a subclass")

    def request_status(self, nr):
        raise NotImplementedError("override request_status in a subclass")

    def handle_status(self, reply):
        raise NotImplementedError("override handle_status in a subclass")

    def control_zones(self, zones, command) -> bool:
        raise NotImplementedError("override control_zones in a subclass")

    def control_partitions(self, partitions, command) -> bool:
        raise NotImplementedError("override control_partitions in a subclass")

    def control_outputs(self, outputs, command) -> bool:
        raise NotImplementedError("override control_outputs in a subclass")


InitiateCommunication = Struct("fields" / RawCopy(
    Struct("po" / BitStruct(
        "command" / Const(7, Nibble),
        "reserved0" / Const(2, Nibble)),
        "reserved1" / Padding(35))),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

InitiateCommunicationResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(7, Nibble),
            "message_center" / Nibble
        ),
        "new_protocol" / Const(0xFF, Int8ub),
        "protocol_id" / Int8ub,
        "protocol" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub
        ),
        "family_id" / Int8ub,
        "product_id" / ProductIdEnum,
        "talker" / Enum(Int8ub,
                        BOOT_LOADER=0,
                        CONTROLLER_APPLICATION=1,
                        MODULE_APPLICATION=2),
        "application" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub),
        "serial_number" / Bytes(4),
        "hardware" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub),
        "bootloader" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub,
            "day" / Int8ub,
            "month" / Int8ub,
            "year" / Int8ub),
        "processor_id" / Int8ub,
        "encryption_id" / Int8ub,
        "reserved0" / Bytes(2),
        "label" / Bytes(8))),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

StartCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x5F, Int8ub)),
        "validation" / Const(0x20, Int8ub),
        "not_used0" / Padding(31),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_id" / Struct(
            "high" / Default(Int8ub, 0),
            "low" / Default(Int8ub, 0)),
    )), "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

StartCommunicationResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct("command" / Const(0, Nibble),
                         "status" / Struct(
                             "reserved" / Flag,
                             "alarm_reporting_pending" / Flag,
                             "Windload_connected" / Flag,
                             "NeWare_connected" / Flag)
                         ),
        "not_used0" / Bytes(3),
        "product_id" / ProductIdEnum,
        "firmware" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub),
        "panel_id" / Int16ub,
        "not_used1" / Bytes(5),
        "transceiver" / Struct(
            "firmware_build" / Int8ub,
            "family" / Int8ub,
            "firmware_version" / Int8ub,
            "firmware_revision" / Int8ub,
            "noise_floor_level" / Int8ub,
            "status" / BitStruct(
                "not_used" / BitsInteger(6),
                "noise_floor_high" / Flag,
                "constant_carrier" / Flag,
            ),
            "hardware_revision" / Int8ub,
        ),
        "not_used2" / Bytes(14),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
