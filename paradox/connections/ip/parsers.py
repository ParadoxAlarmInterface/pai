from construct import (Aligned, BitsInteger, BitStruct, Bytes, Const, Default,
                       Enum, Flag, GreedyBytes, Int8ub, Int16ub, Int16ul,
                       Struct)
from paradox.hardware.common import HexInt

IPMessageType = Enum(
    Int8ub,
    ip_response=0x1,
    serial_passthrough_response=0x2,
    ip_request=0x3,
    serial_passthrough_request=0x4,
)


IPMessageCommand = Enum(
    Int8ub,
    ip_authentication=0xF0,
    F2=0xF2,
    F3=0xF3,
    F4=0xF4,
    F5=0xF5,
    F8=0xF8,
    FB=0xFB,
    panel_communication=0x00,
)


IPPayloadConnectResponse = Struct(
    "login_status"
    / Enum(
        Int8ub,
        success=0x00,
        invalid_password=0x01,
        user_already_connected=0x02,
        user_already_connected1=0x04,
    ),
    "key" / Bytes(16),
    "hardware_version" / Int16ub,
    "ip_firmware_major" / Default(HexInt, 5),
    "ip_firmware_minor" / Default(HexInt, 2),
    "ip_module_serial" / Bytes(4),
)


IPMessageRequest = Struct(
    "header"
    / Aligned(
        16,
        Struct(
            "sof" / Const(0xAA, Int8ub),
            "length" / Int16ul,
            "message_type" / Default(IPMessageType, 0x03),
            "flags"
            / BitStruct(
                "other" / Default(BitsInteger(7), 4), "encrypt" / Default(Flag, True),
            ),
            "command" / Default(IPMessageCommand, 0x00),
            "sub_command" / Default(Int8ub, 0x00),
            "unknown1" / Default(Int8ub, 0x00),
            "unknown2" / Default(Int8ub, 0x00),
        ),
        b"\xee",
    ),
    "payload" / Aligned(16, GreedyBytes, b"\xee"),
)


IPMessageResponse = Struct(
    "header"
    / Aligned(
        16,
        Struct(
            "sof" / Const(0xAA, Int8ub),
            "length" / Int16ul,
            "message_type" / Default(IPMessageType, 0x01),
            "flags"
            / BitStruct(
                "other" / Default(BitsInteger(7), 4), "encrypt" / Default(Flag, True),
            ),
            "command" / Default(IPMessageCommand, 0x00),
            "sub_command" / Default(Int8ub, 0x00),
            "unknown1" / Default(Int8ub, 0x00),
            "unknown2" / Default(Int8ub, 0x03),
        ),
        b"\xee",
    ),
    "payload" / Aligned(16, GreedyBytes, b"\xee"),
)
