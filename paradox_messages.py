import logging

from construct import *
from paradox_message_adapters import *

def calculate_checksum(message):
    r = 0
    for c in message:
        r += c
    r = (r % 256)
    return bytes([r])

def parse(message):
    if message is None or len(message) == 0:
        return None
    if message[0] == 0x72 and message[1] == 0x00:
        return InitiateCommunication.parse(message)
    elif message[0] == 0x72 and message[1] == 0xFF:
        return InitiateCommunicationResponse.parse(message)
    elif message[0] == 0x50:
        return SerialInitialization.parse(message)
    elif message[0] == 0x00:
        return Initialization.parse(message)
    elif message[0] >> 4 == 0x1:
        return LoginConfirmation.parse(message)
    elif message[0] >> 4 == 0x05:
        if message[2] == 0x80 and message[3] == 0:
            return UploadResponseStatus0.parse(message)
        elif message[2] == 0x80 and message[3] == 1:
            return UploadResponseStatus1.parse(message)
        elif message[2] == 0x80 and message[3] == 2:
            return UploadResponseStatus2.parse(message)
        # elif message[2] == 0x80 and message[3] == 3:
        #     return UploadResponseStatus3.parse(message)
        # elif message[2] == 0x80 and message[3] == 4:
        #     return UploadResponseStatus4.parse(message)        
        # elif message[2] == 0x80 and message[3] == 5:
        #     return UploadResponseStatus5.parse(message)
        # elif message[2] == 0x80 and message[3] == 6:
        #     return UploadResponseStatus6.parse(message)
        # elif message[2] == 0x80 and message[3] == 7:
        #     return UploadResponseStatus7.parse(message)
        # elif message[2] == 0x1f and message[3] == 0xe8:
            return UploadResponseStatus1f.parse(message)
        else:
            return UploadResponse.parse(message)

    elif message[0] >> 4 == 0x0e:
        return LiveEvent.parse(message)
    else:
        return None

InitiateCommunication = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(7, Nibble),
            "reserved0" / Const(2, Nibble)
        ),
        "reserved1" / Padding(35),
    )),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

InitiateCommunicationResponse = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command"   / Const(7, Nibble),
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
        "product_id" / Enum(Int8ub,
            DIGIPLEX_v13=0,
            DIGIPLEX_v2=1,
            DIGIPLEX_NE=2,
            DIGIPLEX_EVO_48=3,
            DIGIPLEX_EVO_96=4,
            DIGIPLEX_EVO_192=5
        ),
        "talker" / Enum(Int8ub,
            BOOT_LOADER=0,
            CONTROLLER_APPLICATION=1,
            MODULE_APPLICATION=2
        ),
        "application" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub
        ),
        "serial_number" / Bytes(4),
        "hardware" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
        ),
        "bootloader" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub,
            "day" / Int8ub,
            "month" / Int8ub,
            "year" / Int8ub,
        ),
        "processor_id" / Int8ub,
        "encryption_id" / Int8ub,
        "reserved0" / Padding(10)
    )),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

SerialInitialization = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(0x5, Nibble),
            "reserved0" / Const(0xF, Nibble)
        ),
        "const" / Const(0x20, Int8ub),
        "reserved0" / Padding(34), 
        )
    ),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

Initialization = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(0, Nibble),
            "reserved0" / Const(0, Nibble)
        ),
        "module_address" / Enum(Int8ub,
            PANEL=0,
            PC=1),
        "reserved0" / Padding(2),
        "product_id" / Enum(Int8ub,
            DIGIPLEX_v13=0,
            DIGIPLEX_v2=1,
            DIGIPLEX_NE=2,
            DIGIPLEX_EVO_48=3,
            DIGIPLEX_EVO_96=4,
            DIGIPLEX_EVO_192=5,
            MG5050=65),
        "software" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "id" / Int8ub
        ),
        "module_id" / Int16ub,
        "module_password" / Bytes(2),
        "modem_speed" / Int8ub,
        "windload_id" / Int8ub,
        "user_code" / Bytes(3),
        "module_serial_number" / Bytes(4),
        "evo_data" / Bytes(9),
        "reserved1" / Padding(4),
        "source_id" / Enum(Int8ub,
            NonValid_Source=0,
            Winload_Direct=1,
            Winload_IP=2,
            Winload_GSM=3,
            Winload_Dialer=4,
            NeWare_Direct=5,
            NeWare_IP=6,
            NeWare_GSM=7,
            NeWare_Dialer=8,
            IP_Direct=9,
            VDMP3_Direct=10,
            VDMP3_GSM=11,
            ),
        "carrier_length" / Int8ub
        )
    ),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

InitializationResponse = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(0, Nibble),
            "message_center" / Const(0, Nibble)
        ),
        "module_address" / Enum(Int8ub,
            PANEL=0,
            PC=1),
        "reserved1" / Padding(2), 
        "product_id" / Enum(Int8ub,
            DIGIPLEX_v13=0,
            DIGIPLEX_v2=1,
            DIGIPLEX_NE=2,
            DIGIPLEX_EVO_48=3,
            DIGIPLEX_EVO_96=4,
            DIGIPLEX_EVO_192=5),
        "software" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "id" / Int8ub
        ),
        "module_id" / Int16ub,
        "module_password" / Int16ub,
        "windload_id" / Int8ub,
        "memory_map" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub
        ),
        "event_list" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub
        ),
        "firmware_build" / Int16ub,
        "module_serial_number" / Bytes(4),
        "evo_data" / Bytes(9),
        "reserved1" / Padding(6),
        "carrier_length" / Int8ub
        )
    ),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

LoginConfirmation = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(1, Nibble),            
            "message_center" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "winload_connected" / Flag,
                "neware_connected" / Flag
                )
        ),
        "number_of_bytes" / Int8ub,
        "k" / BitStruct(
            "reserved0" / BitsInteger(3),
            "answer" / Enum(Bit,
                winload=0,
                neware=1
            ),
            "reserved1" / BitsInteger(4),
        ),
        "callback" / Enum(Int16ub,
            callback_disabled=0x0000,
            callback_enabled=0xFFFF
        ),
        "user_number" / Int16ub,
        "user_assignment" / BitStruct(
            "partition_7" / Flag,
            "partition_6" / Flag,
            "partition_5" / Flag,
            "partition_4" / Flag,
            "partition_3" / Flag,
            "partition_2" / Flag,
            "partition_1" / Flag,
            "partition_0" / Flag,
        )
    )),
    "reserved" / Padding(28),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

Upload = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "block_number" / Default(Nibble, 0)
            ),
        #"number_of_bytes" / Default(Int8ub, 0),
        "control_byte" / BitStruct(
            "ram_access" / Default(Bit, 0),
            "alarm_reporting_pending" / Default(Bit, 0),
            "Windload_connected" / Default(Bit, 0),
            "NeWare_connected" / Default(Bit, 0),
            "reserved0" / Default(BitsInteger(2), 0),
            "eeprom_b17" / Default(Bit, 0),
            "eeprom_b16" / Default(Bit, 0),
        ),
        #"bus_address" / Default(Int8ub, 0),
        "address" / Default(Int16ub, 0),
        "bytes_to_read" / Default(Int8ub, 0),
    )),
    Padding(31),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

UploadResponse = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "message_center" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag
                )
        ),
        "number_of_bytes" / Int8ub,
        "control_byte" / BitStruct(
            "ram_access" / Flag,
            "reserved0" / BitsInteger(5),
            "eeprom_b17" / Flag,
            "eeprom_b16" / Flag,
        ),
        "bus_address" / Int8ub,
        #"address" / Int16ub,
        "data" / Bytes(32)
    )),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

UploadResponseStatus0 = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "message_center" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag
                )
        ),
        "control_byte" / BitStruct(
            "ram_access" / Flag,
            "reserved0" / BitsInteger(5),
            "eeprom_b17" / Flag,
            "eeprom_b16" / Flag,
        ),
        "bus_address" / Int8ub,
        "address" / Int8ub,
        "reserved0" / Bytes(5),
        "time" / DateAdapter(Bytes(6)),
        "vdc" /  ExprAdapter(Byte, obj_ * (20.3 - 1.4) / 255.0 + 1.4, 0),
        "dc" / ExprAdapter(Byte, obj_  * 22.8 / 255.0, 0),
        "battery" / ExprAdapter(Byte, obj_ * 22.8 / 255.0, 0),
        "reserved1" / Int8ub,
        "zone_status" / ZoneOpenStatusAdapter(Bytes(16)),
        "reserved2" / Int8ub
    )),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

UploadResponseStatus1 = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "message_center" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag
                )
        ),
        "control_byte" / BitStruct(
            "ram_access" / Flag,
            "reserved0" / BitsInteger(5),
            "eeprom_b17" / Flag,
            "eeprom_b16" / Flag,
        ),
        "bus_address" / Int8ub,
        "address" / Int8ub,
        "reserved0" / Bytes(14),
        "partition_status" / PartitionStatusAdapter(Bytes(8)),
        "reserved1" / Bytes(10)
    )),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

UploadResponseStatus2 = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble),
            "message_center" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag
                )
        ),
        "control_byte" / BitStruct(
            "ram_access" / Flag,
            "reserved0" / BitsInteger(5),
            "eeprom_b17" / Flag,
            "eeprom_b16" / Flag,
        ),
        "bus_address" / Int8ub,
        "address" / Int8ub,
        "zone_status" / ZoneStatusAdapter(Bytes(32)),
    )),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )

LiveEvent = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(0xE, Nibble),
            "message_center" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag
                )
        ),
        "time" / DateAdapter(Bytes(6)),
        "event" / EventAdapter(Bytes(2)),
        "partition" / ExprAdapter(Byte, obj_+1, obj_-1),
        "module_serial" / ModuleSerialAdapter(Bytes(4)),
        "label_type" / Bytes(1),
        "label" / Bytes(16),
        "unknown" / Bytes(1),
        "reserved2" / Bytes(4),
    )),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )


PartitionStateCommand = Struct(
    "fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(0x4, Nibble),
            "reserved0" / Default(Nibble, 0),
        ),
        "reserved0" / Default(Int8ub, 0),
        "state" / PartitionStateAdapter(Bytes(1)),
        "partition" / ExprAdapter(Byte, obj_+1, obj_-1),
    )),
    "reserved0" / Padding(32),
    "checksum" / Checksum(Bytes(1),
        lambda data: calculate_checksum(data),
        this.fields.data)
    )


StatusMemory0 = Struct(

)