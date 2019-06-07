from construct import Struct, Aligned, Const, Int8ub, Bytes, Int16ub, Int16ul, Default, Enum, GreedyBytes

from paradox.hardware.common import HexInt

ip_message = Struct(
        "header" / Aligned(16, Struct(
            "sof" / Const(0xaa, Int8ub), 
            "length" / Int16ul,
            "unknown0" / Default(Int8ub, 0x01),
            "flags" / Int8ub,
            "command" / Int8ub,
            "sub_command" / Default(Int8ub, 0x00),
            'unknown1' / Default(Int8ub, 0x0a),
            'encrypt' / Default(Int8ub, 0x00),
        ), b'\xee'),    
        "payload" / Aligned(16, GreedyBytes, b'\xee')
      )

ip_payload_connect_response = Struct(
    'login_status' / Enum(Int8ub,
    	success=0x00,
    	invalid_password=0x01,
    	user_already_connected=0x02,
    	user_already_connected1=0x04),
    'key'   / Bytes(16),
    'hardware_version' / Int16ub,
    'ip_firmware_major' / Default(HexInt, 5),
    'ip_firmware_minor' / Default(HexInt, 2),
    'ip_module_serial'	/ Bytes(4),
    )
