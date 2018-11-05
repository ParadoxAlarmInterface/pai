from construct import Struct, Aligned, Const, Int8ub, Bytes, this, Int16ub, Int16ul, BitStruct, Default, BitsInteger, Flag, Enum, GreedyBytes

ip_message = Struct(
        "header" / Aligned(16,Struct(
            "sof" / Const(0xaa, Int8ub), 
            "length" / Int16ul,
            "unknown0" / Default(Int8ub, 0x01),
            "flags" / Int8ub,
            "command" / Int8ub,
            "sub_command" / Default(Int8ub, 0x00),
            'unknown1' / Default(Int8ub, 0x0a),
            'unknown2' / Default(Int8ub, 0x00),
            'encrypt' / Default(Int8ub, 0x00),
        ), b'\xee'),    
        "payload" / Aligned(16, GreedyBytes, b'\xee')
      )

ip_payload_connect_response = Struct(
    'command' / Const(0x00, Int8ub),
    'key'   / Bytes(16),
    'major' / Int8ub,
    'minor' / Int8ub,
    'ip_major' / Default(Int8ub, 5),
    'ip_minor' / Default(Int8ub, 2),
    'unknown'   / Default(Int8ub, 0x00))
