import collections

from construct import Struct, RawCopy, BitStruct, Const, Nibble, Flag, Rebuild, Int8ub, BitsInteger, Int16ub, Checksum, \
    Bytes, this, Default, Padding, Enum, Int24ub, ExprAdapter, Byte, obj_, Array, Computed, Subconstruct, \
    ValidationError, ExprSymmetricAdapter

from .adapters import PGMFlags, StatusAdapter, DateAdapter, ZoneFlags, PartitionStatus, EventAdapter
from ..common import CommunicationSourceIDEnum, ProductIdEnum, calculate_checksum

LoginConfirmationResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x1, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)
        ),
        "length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "result" / BitStruct(
            "_not_used0" / BitsInteger(4),
            "partition_2" / Flag,
            "_not_used1" / BitsInteger(3)
        ),
        "callback" / Int16ub
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

InitializeCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x00, Int8ub)),
        "module_address" / Default(Int8ub, 0x00),
        "_not_used0" / Padding(2),
        "product_id" / ProductIdEnum,
        "firmware" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub),
        "panel_id" / Int16ub,
        "pc_password" / Default(Bytes(2), b'0000'),
        "modem_speed" / Bytes(1),
        "source_method" / Default(Enum(Int8ub,
                                       Winload_Connection=0x00,
                                       NEware_Connection=0x55), 0x00),
        "user_code" / Default(Int24ub, 0x000000),
        "serial_number" / Bytes(4),
        "evo_sections" / Bytes(9),  # EVO section data 3030-3038
        "_not_used1" / Padding(4),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "carrier_length" / Bytes(1)
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))


RAMDataParserMap = {
    1: Struct(
        "weekday" / Int8ub,
        "pgm_flags" / PGMFlags(),
        "_key-switch_triggered" / StatusAdapter(Bytes(4)), # TODO: Implement key-switch
        "door_open" / StatusAdapter(Bytes(4)),
        "troubles" / BitStruct(
            "system_trouble" / Flag,
            "dialer_trouble" / Flag,
            "module_trouble" / Flag,
            "bus_com_trouble" / Flag, # BusCom
            "zone_tamper_trouble" / Flag,
            "zone_low_battery_trouble" / Flag,
            "zone_fault_trouble" / Flag,
            "time_lost_trouble" / Flag,

            "ac_trouble" / Flag,
            "battery_failure_trouble" / Flag,
            "aux_limit_trouble" / Flag,
            "bell_limit_trouble" / Flag,
            "bell_absent_trouble" / Flag,
            "rom_error_trouble" / Flag,
            "_future_use_0" / Flag,
            "_future_use_1" / Flag,

            "tlm_trouble" / Flag,
            "fail_tel_1_trouble" / Flag,
            "fail_tel_2_trouble" / Flag,
            "fail_tel_3_trouble" / Flag,
            "fail_tel_4_trouble" / Flag,
            "com_pc_trouble" / Flag,
            "_future_use_2" / Flag,
            "_future_use_3" / Flag,

            "module_tamper_trouble" / Flag,
            "module_rom_error_trouble" / Flag,
            "module_tlm_trouble" / Flag,
            "module_fail_to_com_trouble" / Flag,
            "module_printer_trouble" / Flag,
            "module_ac_trouble" / Flag,
            "module_battery_fail" / Flag,
            "module_aux_trouble" / Flag,

            "missing_keypad_trouble" / Flag,
            "missing_module_trouble" / Flag,
            "_future_use_4" / Flag,
            "_future_use_5" / Flag,
            "safety_mismatch_trouble" / Flag,
            "bus_global_fail" / Flag,
            "bus_overload_trouble" / Flag,
            "mdl_com_error" / Flag
        ),
        "time" / DateAdapter(Bytes(7)),
        "vdc" / ExprAdapter(Byte, obj_ * (20.3 - 1.4) / 255.0 + 1.4, 0),
        "battery" / ExprAdapter(Byte, obj_ * 22.8 / 255.0, 0),
        "dc" / ExprAdapter(Byte, obj_ * 22.8 / 255.0, 0),
        "zone_open" / StatusAdapter(Bytes(12)),
        "zone_tamper" / StatusAdapter(Bytes(12)),
        "zone_low_battery" / StatusAdapter(Bytes(12))
    ),
    2: Struct(
        "zone_status" / ZoneFlags(64)
    ),
    3: Struct(
        "zone_status" / ZoneFlags(32, start_index_from=65),
        "partition_status" / PartitionStatus(Bytes(32)),
    ),
    4: Struct(
        "partition_status" / PartitionStatus(Bytes(16)),
        "_panel_status" / BitStruct(
            "installer_lock_active" / Flag,
            "_free" / Padding(7)
        ),
        "event_pointer" / Int16ub,
        "event_pointer_bus" / Int16ub,
        "_recycle_system" / Array(8, Int8ub),
        "arm_disarm_report_delay_timer" / Int8ub,
        "_free" / Padding(34)
    ),
    5: Struct(
        "_free" / Padding(1),
        "bus-module_trouble" / StatusAdapter(Bytes(63))
    )
}

LiveEvent = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0xE, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "event_source" / Const(0xFF, Int8ub),
        "event_nr" / Int16ub,
        "time" / DateAdapter(Bytes(6)),
        "event" / EventAdapter(Bytes(4)),
        "partition" / Computed(this.event.partition),
        "module_serial" / Bytes(4),
        "label_type" / Bytes(1),
        "label" / Bytes(16),
        "_not_used0" / Bytes(1),
    )), "checksum" / Checksum(
    Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

# "Event 1 requested (in compressed format) 1 (12 bytes)
#   Byte 00: [7-3]: Day, [2-0]: Month (MSB)
#   Byte 01: [7]: Month (LSB), [6-0]: Century
#   Byte 02: [7-1]: Year, [0]: Hour (MSB)
#   Byte 03: [7-4]: Hour (LSB), [3-0]: Minutes (MSB)
#   Byte 04: [7-6]: Minutes (LSB), [5-0]: Event Group
#   Byte 05: [7-4]: Partition, [3-0]: Event Number High Nibble
#   Byte 06: Event Number 1
#   Byte 07: Event Number 2
#   Byte 08: Serial Number 1 & 2 (2 nibbles)
#   Byte 09: Serial Number 3 & 4 (2 nibbles)
#   Byte 10: Serial Number 5 & 6 (2 nibbles)
#   Byte 11: Serial Number 7 & 8 (2 nibbles)"

CompressedEvent = Struct(
    "compressed" / BitStruct(
        "day" / BitsInteger(5),
        "month" / BitsInteger(4),
        "century" / BitsInteger(7),
        "year" / BitsInteger(7),
        "hour" / BitsInteger(5),
        "minute" / BitsInteger(6),
        "event_group" / BitsInteger(6),
        "partition" / BitsInteger(4),
        "event_1_high_nibble" / BitsInteger(2),
        "event_2_high_nibble" / BitsInteger(2)
    ),
    "minor_1" / Int8ub,
    "minor_2" / Int8ub,
    "module_serial" / Bytes(4)
)

RequestedEvent = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0xE, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "_not_used0" / Bytes(1),
        "requested_event_nr" / Const(0x00, Int8ub),
        "event_nr" / Int16ub,
        # "data" / Bytes(lambda this: this.length - 7)
        "data" / Array(lambda this: int((this.length - 7) / 12), CompressedEvent)
    )), "checksum" / Checksum(
    Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

Action = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x40, Int8ub),
        ),
        "_not_used0" / Default(Int8ub, 0),
        "action" / Enum(Int8ub,
                        Stay_Arm=0x1,
                        Stay_Arm1=0x2,
                        Sleep_Arm=0x3,
                        Full_Arm=0x4,
                        Disarm=0x5,
                        Stay_Arm_D_Enabled=0x6,
                        Stay_Arm_Sleep_D_Enabled=0x7,
                        Disarm_Both=0x8,
                        Bypass=0x10,
                        Beep=0x20,
                        PGM_On_Override=0x30,
                        PGM_Off_Override=0x31,
                        PGM_On=0x32,
                        PGM_Off=0x33,
                        Reload_RAM=0x80),
        "argument" / ExprAdapter(Byte, obj_ + 1, obj_ - 1),
        "_not_used0" / Padding(29),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ActionResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x4, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "data" / Bytes(lambda this: this.packet_length - 3)
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

CloseConnection = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x70, Int8ub)
        ),
        "length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "message" / Default(Enum(Int8ub,
                         requested_command_failed=0x00,
                         invalid_user_code=0x01,
                         partition_in_code_lockout=0x02,
                         panel_will_disconnect=0x05,
                         panel_not_connected=0x10,
                         panel_already_connected=0x11,
                         invalid_pc_password=0x12,
                         winload_on_phone_line=0x13,
                         invalid_module_address=0x14,
                         cannot_write_in_ram=0x15,
                         upgrade_request_fail=0x16,
                         record_number_out_of_range=0x17,
                         invalid_record_type=0x19,
                         multibus_not_supported=0x1a,
                         incorrect_number_of_users=0x1b,
                         invalid_label_number=0x1c
                         ), 0x05),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))


class EvoEEPROMAddressAdapter(Subconstruct):
    def deep_update(self, d, u):
        for k, v in u.items():
            if isinstance(v, collections.Mapping):
                d[k] = self.deep_update(d.get(k, {}), v)
            else:
                d[k] = v
        return d

    def _build(self, obj, stream, context, path):
        if "control" in obj and obj["control"].get("ram_access"):  # for ram block
            ram_block = (obj["address"] & 0xf0000) >> 16
            self.deep_update(obj, dict(po=dict(block=ram_block)))
        else:  # for eeprom
            if obj["address"] >> 16 > 0x3:
                raise ValidationError("EEPROM address is out of range")
            eeprom_address_high_bits = (obj["address"] & 0x30000) >> 16
            self.deep_update(obj, dict(control=dict(eeprom_address_bits=eeprom_address_high_bits)))
        return self.subcon._build(obj, stream, context, path)

    def _parse(self, stream, context, path):
        obj = self.subcon._parsereport(stream, context, path)
        return obj


ReadEEPROM = Struct("fields" / RawCopy(
    EvoEEPROMAddressAdapter(Struct(
        "po" / BitStruct(
            "command" / Const(0x5, Nibble),
            "block" / Default(Nibble, 0),
        ),
        "packet_length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "control" / BitStruct(
            "ram_access" / Default(Flag, False),
            "alarm_reporting_pending" / Default(Flag, False),
            "Winload_connected" / Default(Flag, False),
            "NeWare_connected" / Default(Flag, False),
            "_not_used" / Default(BitsInteger(2), 0),
            "eeprom_address_bits" / Default(BitsInteger(2), 0)
        ),
        "bus_address" / Default(Int8ub, 0x00),  # 00 - Panel, 01-FF - Modules
        "address" / ExprSymmetricAdapter(Int16ub, obj_ & 0xffff),
        "length" / Int8ub
    ))),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadEEPROMResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)
        ),
        "packet_length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "control" / BitStruct(
            "ram_access" / Flag,
            "_not_used" / Padding(5),
            "eeprom_address_bits" / BitsInteger(2)
        ),
        "bus_address" / Int8ub,  # 00 - Panel, 01-FF - Modules
        "address" / Int16ub,
        "data" / Bytes(lambda this: this.packet_length - 7)
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

SetTimeDate = Struct("fields" / RawCopy(Struct(
        "po" / Struct(
            "command" / Const(0x30, Int8ub)),
        "packet_length" / Rebuild(Int8ub,
                                  lambda this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "_not_used0" / Padding(4),
        "century" / Int8ub,
        "year" / Int8ub,
        "month" / Int8ub,
        "day" / Int8ub,
        "hour" / Int8ub,
        "minute" / Int8ub,
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

SetTimeDateResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x3, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "length" / Int8ub,
        "_not_used0" / Padding(4),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

_PartitionCommandEnum = Enum(Nibble,
                             none  = 0,
                             arm = 2,
                             arm_stay = 3,
                             arm_instant = 4,
                             arm_force = 5,
                             disarm = 6,
                             beep_keypads = 8
                             )

class PartitionAdapter(Subconstruct):
    def _build(self, obj, stream, context, path):
        partitions = dict([(i, 0) for i in range(1, 9) ])
        partitions.update(obj)

        obj = {"partitions": list(partitions.values())}

        return self.subcon._build(obj, stream, context, path)

PerformPartitionAction = Struct("fields" / RawCopy(Struct(
        "po" / Struct(
            "command" / Const(0x40, Int8ub)),
        "packet_length" / Rebuild(Int8ub, lambda this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "_not_used0" / Padding(4),
        "commands" / PartitionAdapter(BitStruct(
            "partitions" / Array(8, _PartitionCommandEnum),
        )),
        "_not_used1" / Padding(4),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PerformActionResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x4, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "packet_length" / Rebuild(Int8ub, lambda this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "_not_used0" / Padding(4),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ErrorMessage = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x7, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "message" / Enum(Int8ub,
                         requested_command_failed=0x00,
                         invalid_user_code=0x01,
                         partition_in_code_lockout=0x02,
                         panel_will_disconnect=0x05,
                         panel_not_connected=0x10,
                         panel_already_connected=0x11,
                         invalid_pc_password=0x12,
                         winload_on_phone_line=0x13,
                         invalid_module_address=0x14,
                         cannot_write_in_ram=0x15,
                         upgrade_request_fail=0x16,
                         record_number_out_of_range=0x17,
                         invalid_record_type=0x19,
                         multibus_not_supported=0x1a,
                         incorrect_number_of_users=0x1b,
                         invalid_label_number=0x1c
                         ),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
