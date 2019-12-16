from construct import Struct, BitStruct, Const, Nibble, Checksum, Padding, Bytes, this, RawCopy, Int8ub, \
    Default, Enum, Flag, BitsInteger, Int16ub, Rebuild

from .common import calculate_checksum, ProductIdEnum, CommunicationSourceIDEnum, HexInt

InitiateCommunication = Struct(
    "fields" / RawCopy(
        Struct(
            "po" / BitStruct(
                "command" / Const(7, Nibble),
                "reserved0" / Const(2, Nibble)
            ),
            "reserved1" / Padding(35)
        )
    ),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data)
)

InitiateCommunicationResponse = Struct(
    "fields" / RawCopy(
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
                "version" / HexInt,
                "revision" / HexInt,
                "build" / HexInt),
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
            "label" / Bytes(8)
        )
    ),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

StartCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x5F, Int8ub)),
        "validation" / Const(0x20, Int8ub),
        "_not_used0" / Padding(31),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_id" / Struct(
            "high" / Default(Int8ub, 0),
            "low" / Default(Int8ub, 0)),
    )), "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

StartCommunicationResponse = Struct(
    "fields" / RawCopy(
        Struct(
            "po" / BitStruct("command" / Const(0, Nibble),
                             "status" / Struct(
                                 "reserved" / Flag,
                                 "alarm_reporting_pending" / Flag,
                                 "Winload_connected" / Flag,
                                 "NeWare_connected" / Flag)
                             ),
            "_not_used0" / Bytes(3),
            "product_id" / ProductIdEnum,
            "firmware" / Struct(
                "version" / Int8ub,
                "revision" / Int8ub,
                "build" / Int8ub),
            "panel_id" / Int16ub,
            "_not_used1" / Bytes(5),
            "transceiver" / Struct(
                "firmware_build" / Int8ub,
                "family" / Int8ub,
                "firmware_version" / Int8ub,
                "firmware_revision" / Int8ub,
                "noise_floor_level" / Int8ub,
                "status" / BitStruct(
                    "_not_used" / BitsInteger(6),
                    "noise_floor_high" / Flag,
                    "constant_carrier" / Flag,
                ),
                "hardware_revision" / Int8ub,
            ),
            "_not_used2" / Bytes(14),
        )
    ),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data)
)

CloseConnection = Struct(
    "fields" / RawCopy(
        Struct(
            "po" / Struct(
                "command" / Const(0x70, Int8ub)
            ),
            "length" / Rebuild(Int8ub, lambda
                this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
            "_not_used0" / Padding(34),
        )
    ),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data)
)
