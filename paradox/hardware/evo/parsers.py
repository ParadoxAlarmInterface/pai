import collections

from construct import *
from ..common import CommunicationSourceIDEnum, ProductIdEnum, calculate_checksum
from .adapters import *

LoginConfirmationResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x1, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)
        ),
        "length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "result" / BitStruct(
            "not_used0" / BitsInteger(4),
            "partition_2" / Flag,
            "not_used1" / BitsInteger(3)
        ),
        "callback" / Int16ub
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

InitializeCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x00, Int8ub)),
        "module_address" / Default(Int8ub, 0x00),
        "not_used0" / Padding(2),
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
        "not_used1" / Padding(4),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "carrier_length" / Bytes(1)
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))


RAMDataParserMap = {
    1: Struct(
        "weekday" / Int8ub,
        "pgm" / Bytes(4),
        "key_switch" / StatusAdapter(Bytes(4)),
        "door_state" / StatusAdapter(Bytes(4)),
        "troubles" / BitStruct(
            "Trbl_System" / Flag,
            "Trbl_Dialer" / Flag,
            "Trbl_Mdl" / Flag,
            "Trbl_BusCom" / Flag,
            "Trbl_ZnTmpr" / Flag,
            "Trbl_ZnLoBat" / Flag,
            "Trbl_ZnFault" / Flag,
            "Trbl_TimeLost" / Flag,

            "AC_Trouble" / Flag,
            "Battery_Fail" / Flag,
            "Aux_Limit" / Flag,
            "Bell_Limit" / Flag,
            "Bell_Absent" / Flag,
            "Rom_Error" / Flag,
            "Future_Use_0" / Flag,
            "Future_Use_1" / Flag,

            "TLM_Trouble" / Flag,
            "Fail_Tel_1" / Flag,
            "Fail_Tel_2" / Flag,
            "Fail_Tel_3" / Flag,
            "Fail_Tel_4" / Flag,
            "Fail_Com_PC" / Flag,
            "Future_Use_2" / Flag,
            "Future_Use_3" / Flag,

            "Mdl_Tamper" / Flag,
            "Mdl_Rom_Error" / Flag,
            "Mdl_TLM_TROUBLE" / Flag,
            "Mdl_Fail_To_Com" / Flag,
            "Mdl_Printer_Trbl" / Flag,
            "Mdl_AC_Trouble" / Flag,
            "Mdl_Battery_Fail" / Flag,
            "Mdl_Aux_Trouble" / Flag,

            "Missing_Keypad" / Flag,
            "Missing_Module" / Flag,
            "Future_Use_4" / Flag,
            "Future_Use_5" / Flag,
            "Safety_Mismatch" / Flag,
            "Bus_Global_Fail" / Flag,
            "Bus_Overload" / Flag,
            "Mdl_Com_Error" / Flag
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
        "zone_flags" / ZoneFlagsAdapter(Bytes(64))
    ),
    3: Struct(
        "zone_flags" / ZoneFlagsAdapter(Bytes(32), start_index_from=65),
        "partition_status" / PartitionStatusAdapter(Bytes(32)),
    ),
    4: Struct(
        "partition_status" / PartitionStatusAdapter(Bytes(16)),
        "panel_state" / BitStruct(
            "installer_lock_active" / Flag,
            "_free" / Padding(7)
        ),
        "event_pointer" / Int16ub,
        "event_pointer_bus" / Int16ub,
        "recycle_system" / Array(8, Int8ub),
        "arm_disarm_report_delay_timer" / Int8ub,
        "_free" / Padding(34)
    ),
    5: Struct(
        "_free" / Padding(1),
        "module_trouble" / StatusAdapter(Bytes(63))
    )
}

LiveEvent = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0xE, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "event_source" / Const(0xFF, Int8ub),
        "event_nr" / Int16ub,
        "time" / DateAdapter(Bytes(6)),
        "event" / EventAdapter(Bytes(4)),
        "partition" / Computed(this.event.partition),
        "module_serial" / ModuleSerialAdapter(Bytes(4)),
        "label_type" / Bytes(1),
        "label" / Bytes(16),
        "not_used0" / Bytes(1),
    )), "checksum" / Checksum(
    Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

Action = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x40, Int8ub),
        ),
        "not_used0" / Default(Int8ub, 0),
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
        "not_used0" / Padding(29),
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
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Default(Int8ub, 0),
        "not_used1" / Default(Int8ub, 0),
        "action" / Int8ub,
    )),
    "reserved0" / Padding(32),
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
            "Windload_connected" / Default(Flag, False),
            "NeWare_connected" / Default(Flag, False),
            "not_used" / Default(BitsInteger(2), 0),
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
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)
        ),
        "packet_length" / Rebuild(Int8ub, lambda
            this: this._root._subcons.fields.sizeof() + this._root._subcons.checksum.sizeof()),
        "control" / BitStruct(
            "ram_access" / Flag,
            "not_used" / Padding(5),
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
        "not_used0" / Padding(4),
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
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "length" / Int8ub,
        "not_used0" / Padding(4),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PerformAction = Struct("fields" / RawCopy(Struct(
        "po" / Struct(
            "command" / Const(0x40, Int8ub)),
        "not_used0" / Padding(1),
        "action" / Enum(Int8ub,
                        Stay_Arm=0x01,
                        Stay_Arm1=0x02,
                        Sleep_Arm=0x03,
                        Full_Arm=0x04,
                        Disarm=0x05,
                        Stay_Arm_StayD=0x06,
                        Sleep_Arm_StayD=0x07,
                        Disarm_Both_Disable_StayD=0x08,
                        Bypass=0x10,
                        Beep=0x10,
                        PGM_On_Override=0x30,
                        PGM_Off_Override=0x31,
                        PGM_On=0x32,
                        PGM_Off=0x33,
                        Reload_RAM=0x80,
                        Bus_Scan=0x85,
                        Future_Use=0x90),
        "argument" / Enum(Int8ub,
                          One_Beep=0x04,
                          Fail_Beep=0x08,
                          Beep_Twice=0x0c,
                          Accept_Beep=0x10),
        "not_used1" / Padding(29),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PerformActionResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x4, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "not_used0" / Padding(1),
        "action" / Enum(Int8ub,
                        Stay_Arm=0x01,
                        Stay_Arm1=0x02,
                        Sleep_Arm=0x03,
                        Full_Arm=0x04,
                        Disarm=0x05,
                        Stay_Arm_StayD=0x06,
                        Sleep_Arm_StayD=0x07,
                        Disarm_Both_Disable_StayD=0x08,
                        Bypass=0x10,
                        Beep=0x10,
                        PGM_On_Override=0x30,
                        PGM_Off_Overrite=0x31,
                        PGM_On=0x32,
                        PGM_Of=0x33,
                        Reload_RAM=0x80,
                        Bus_Scan=0x85,
                        Future_Use=0x90),
        "not_used1" / Padding(33),
    )),
    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ErrorMessage = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x7, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag,
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
