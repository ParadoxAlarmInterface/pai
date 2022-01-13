from construct import (BitsInteger, BitStruct, Bytes, Const, Default, Enum,
                       Flag, Int8ub, Int16ub, Nibble, Padding, RawCopy, Struct)

from .common import (CommunicationSourceIDEnum, HexInt, PacketChecksum,
                     PacketLength, ProductIdEnum, FamilyIdEnum)

InitiateCommunication = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct("command" / Const(7, Nibble), "reserved0" / Const(2, Nibble)),
            "reserved1" / Padding(35),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

InitiateCommunicationResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / BitStruct("command" / Const(7, Nibble), "message_center" / Nibble),
            "new_protocol" / Const(0xFF, Int8ub),
            "protocol_id" / Int8ub,
            "protocol"
            / Struct("version" / Int8ub, "revision" / Int8ub, "build" / Int8ub),
            "family_id" / FamilyIdEnum,
            "product_id" / ProductIdEnum,
            "talker"
            / Enum(
                Int8ub, BOOT_LOADER=0, CONTROLLER_APPLICATION=1, MODULE_APPLICATION=2
            ),
            "application"
            / Struct("version" / HexInt, "revision" / HexInt, "build" / HexInt),
            "serial_number" / Bytes(4),
            "hardware" / Struct("version" / Int8ub, "revision" / Int8ub),
            "bootloader"
            / Struct(
                "version" / Int8ub,
                "revision" / Int8ub,
                "build" / Int8ub,
                "day" / Int8ub,
                "month" / Int8ub,
                "year" / Int8ub,
            ),
            "processor_id" / Int8ub,
            "encryption_id" / Int8ub,
            "reserved0" / Bytes(2),
            "label" / Bytes(8),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

StartCommunication = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x5F, Int8ub)),
            "validation" / Const(0x20, Int8ub),
            "_not_used0" / Padding(31),
            "source_id" / Default(CommunicationSourceIDEnum, 1),
            "user_id" / Struct("high" / Default(Int8ub, 0), "low" / Default(Int8ub, 0)),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

StartCommunicationResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "_not_used0" / Bytes(3),
            "product_id" / ProductIdEnum,
            "firmware"
            / Struct("version" / Int8ub, "revision" / Int8ub, "build" / Int8ub),
            "panel_id" / Int16ub,
            "_not_used1" / Bytes(5),
            "transceiver"
            / Struct(
                "firmware_build" / Int8ub,
                "family" / Int8ub,
                "firmware_version" / Int8ub,
                "firmware_revision" / Int8ub,
                "noise_floor_level" / Int8ub,
                "status"
                / BitStruct(
                    "_not_used" / BitsInteger(6),
                    "noise_floor_high" / Flag,
                    "constant_carrier" / Flag,
                ),
                "hardware_revision" / Int8ub,
            ),
            "_not_used2" / Bytes(14),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

CloseConnection = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x70, Int8ub)),
            "length" / PacketLength(Int8ub),
            "_not_used0" / Padding(34),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)
