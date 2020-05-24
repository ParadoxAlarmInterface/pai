from construct import (Adapter, Aligned, BitStruct, Bytes, Const, Default,
                       Enum, Flag, GreedyBytes, IfThenElse, Int8ub, Int16ub,
                       Int16ul, Padding, Pointer, Rebuild, Struct, len_, this)

from paradox.hardware.common import HexInt
from paradox.lib.crypto import decrypt, encrypt

IPMessageType = Enum(
    Int8ub,
    ip_response=0x1,
    serial_passthrough_response=0x2,
    ip_request=0x3,
    serial_passthrough_request=0x4,
)


IPMessageCommand = Enum(
    Int8ub,
    connect=0xF0,
    send_user_label=0xF1,
    keep_alive=0xF2,
    upload_download_connection=0xF3,
    upload_download_disconnection=0xF4,
    boot_loader=0xF5,
    web_page_connect=0xF6,
    web_page_disconnect=0xF7,
    toggle_keep_alive=0xF8,
    reset=0xF9,
    set_baud_rate=0xFA,
    multicommand=0xFB,
    single_panel=0xFC,
    unsupported_request=0xFD,
    boot_ip=0xFE,
    disconnect=0xFF,
    passthrough=0x00,
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
    "ip_type"
    / Default(
        Pointer(21, Enum(Int8ub, IP150=0x71, IP100=0x70)),
        lambda ctx: ctx.ip_module_serial[0],
    ),
)


class EncryptionAdapter(Adapter):
    def _decode(self, obj, context, path):
        try:
            return decrypt(obj, context._.password)[: context.header.length]
        except AttributeError:
            raise

    def _encode(self, obj, context, path):
        try:
            return encrypt(obj, context._.password)
        except AttributeError:
            raise


IPMessageRequest = Struct(
    "header"
    / Aligned(
        16,
        Struct(
            "sof" / Const(0xAA, Int8ub),
            "length"
            / Rebuild(
                Int16ul, lambda ctx: len(ctx._.payload) if "payload" in ctx._ else 0
            ),
            "message_type" / Default(IPMessageType, 0x03),
            "flags"
            / BitStruct(
                "bit8" / Default(Flag, False),
                "keep_alive" / Default(Flag, False),
                "live_events" / Default(Flag, False),
                "neware" / Default(Flag, False),
                "installer_mode" / Default(Flag, False),
                "bit3" / Default(Flag, False),
                "upload_download" / Default(Flag, False),
                "encrypt" / Default(Flag, True),
            ),
            "command" / Default(IPMessageCommand, 0x00),
            "sub_command" / Default(Int8ub, 0x00),
            "wt" / Default(Int8ub, 0x00),  # WT - 14
            "sb" / Default(Int8ub, 0x00),  # SB: 0
            "cryptor_code"
            / Default(Enum(Int8ub, none=0, aes_256_ecb=1, old_module=0xEE), "none"),
            "_not_used" / Padding(1, b"\xee"),
            "sequence_id" / Default(Int8ub, 0xEE),
        ),
        b"\xee",
    ),
    "payload"
    / Default(
        IfThenElse(
            this.header.flags.encrypt,
            EncryptionAdapter(Aligned(16, GreedyBytes, b"\xee")),
            Bytes(this.header.length),
        ),
        b"",
    ),
)


IPMessageResponse = Struct(
    "header"
    / Aligned(
        16,
        Struct(
            "sof" / Const(0xAA, Int8ub),
            "length"
            / Rebuild(
                Int16ul, lambda ctx: len(ctx._.payload) if "payload" in ctx._ else 0
            ),
            "message_type" / Default(IPMessageType, 0x01),
            "flags"
            / BitStruct(
                "bit8" / Default(Flag, False),
                "keep_alive" / Default(Flag, False),
                "live_events" / Default(Flag, False),
                "neware" / Default(Flag, False),
                "installer_mode" / Default(Flag, False),
                "bit3" / Default(Flag, False),
                "upload_download" / Default(Flag, False),
                "encrypt" / Default(Flag, True),
            ),
            "command" / Default(IPMessageCommand, 0x00),
            "sub_command" / Default(Int8ub, 0x00),
            "wt" / Default(Int8ub, 0x00),  # WT
            "sb" / Default(Int8ub, 0x03),  # SB
            "cryptor_code"
            / Default(Enum(Int8ub, none=0, aes_256_ecb=1, old_module=0xEE), "none"),
        ),
        b"\xee",
    ),
    "payload"
    / Default(
        IfThenElse(
            this.header.flags.encrypt,
            EncryptionAdapter(Aligned(16, GreedyBytes, b"\xee")),
            Bytes(this.header.length),
        ),
        b"",
    ),
)
