from construct import *
from ..common import CommunicationSourceIDEnum, ProductIdEnum, calculate_checksum
from .adapters import *

InitializeCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x00, Int8ub)),
        "_not_used0" / Padding(3),
        "product_id" / ProductIdEnum,
        "firmware" / Struct(
            "version" / Int8ub,
            "revision" / Int8ub,
            "build" / Int8ub),
        "panel_id" / Int16ub,
        "pc_password" / Default(Bytes(2), b'0000'),
        "_not_used1" / Bytes(1),
        "source_method" / Default(Enum(Int8ub,
                                       Winload_Connection=0x00,
                                       NEware_Connection=0x55), 0x00),
        "user_code" / Default(Int32ub, 0x00000000),
        "_not_used2" / Padding(15),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_id" / Struct(
            "high" / Default(Int8ub, 0),
            "low" / Default(Int8ub, 0)),
    )),
                                 "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data),
                                                       this.fields.data))

InitializeCommunicationResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x10, Int8ub)),
        "neware_connection" / Int16ub,
        "user_id_low" / Int8ub,
        "partition_rights" / BitStruct(
            "_not_used" / BitsInteger(6),
            "partition_2" / Flag,
            "partition_1" / Flag),
        "_not_used0" / Padding(31),
    )),
                                         "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data),
                                                               this.fields.data))

PanelStatus = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x50, Int8ub)),
        "_not_used0" / Default(Int8ub, 0x00),
        "validation" / Default(Int8ub, 0x00),
        "status_request" / Default(Int8ub, 0x00),
        "_not_used1" / Padding(29),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
                     Padding(31),
                     "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

RAMDataParserMap = {
    0: Struct(
        "troubles" / BitStruct(
            "timer_loss_trouble" / Flag,
            "fire_loop_trouble" / Flag,
            "module_tamper_trouble" / Flag,
            "zone_tamper_trouble" / Flag,
            "communication_trouble" / Flag,
            "bell_trouble" / Flag,
            "power_trouble" / Flag,
            "rf_low_battery_trouble" / Flag,
            "rf_interference_trouble" / Flag,
            "_not_used0" / BitsInteger(5),
            "module_supervision_trouble" / Flag,
            "zone_supervision_trouble" / Flag,
            "_not_used1" / BitsInteger(1),
            "wireless_repeater_battery_trouble" / Flag,
            "wireless_repeater_ac_loss_trouble" / Flag,
            "wireless_keypad_battery_trouble" / Flag,
            "wireless_keypad_ac_trouble" / Flag,
            "auxiliary_output_overload_trouble" / Flag,
            "ac_failure_trouble" / Flag,
            "low_battery_trouble" / Flag,
            "_not_used2" / BitsInteger(6),
            "bell_output_overload_trouble" / Flag,
            "bell_output_disconnected_trouble" / Flag,
            "_not_used3" / BitsInteger(2),
            "computer_fail_to_communicate_trouble" / Flag,
            "voice_fail_to_communicate_trouble" / Flag,
            "pager_fail_to_communicate_trouble" / Flag,
            "central_2_reporting_ftc_indicator_trouble" / Flag,
            "central_1_reporting_ftc_indicator_trouble" / Flag,
            "telephone_line" / Flag),

        "system" / Struct(
            "date" / Struct("time" / DateAdapter(Bytes(6))),
            "power" / Struct(
                "vdc" / ExprAdapter(Byte, lambda obj, ctx: round(obj * (20.3 - 1.4) / 255.0 + 1.4, 1), 0),
                "battery" / ExprAdapter(Byte, lambda obj, ctx: round(obj * 22.8 / 255.0, 1), 0),
                "dc" / ExprAdapter(Byte, lambda obj, ctx: round(obj * 22.8 / 255.0, 1), 0),
            ),
            "rf" / Struct(
                "noise_floor" / Int8ub,
            )
        ),
        "zone_open" / StatusAdapter(Bytes(4)),
        "zone_tamper" / StatusAdapter(Bytes(4)),
        "pgm_tamper" / StatusAdapter(Bytes(2)),
        "bus-module_tamper" / StatusAdapter(Bytes(2)),
        "zone_fire" / StatusAdapter(Bytes(4)),
        "_not_used0" / Int8ub
    ),
    1: Struct(
        "zone_rf_supervision_trouble" / StatusAdapter(Bytes(4)),
        "pgm_supervision_trouble" / StatusAdapter(Bytes(2)),
        "bus-module_supervision_trouble" / StatusAdapter(Bytes(2)),
        "repeater_supervision_trouble" / StatusAdapter(Bytes(1)),
        "zone_rf_low_battery_trouble" / StatusAdapter(Bytes(4)),
        "partition_status" / PartitionStatusAdapter(Bytes(8)),
        "repeater_ac_loss_trouble" / StatusAdapter(Bytes(1)),
        "repeater_battery_failure_trouble" / StatusAdapter(Bytes(1)),
        "keypad_ac_loss_trouble" / StatusAdapter(Bytes(1)),
        "keypad_battery_failure_trouble" / StatusAdapter(Bytes(1)),
        "keypad_supervision_failure_trouble" / StatusAdapter(Bytes(1)),
        "_not_used0" / Padding(6)
    ),
    2: Struct(
        "zone_status" / ZoneStatusAdapter(Bytes(32))
    ),
    3: Struct(
        "zone_signal_strength" / SignalStrengthAdapter(Bytes(32))
    ),
    4: Struct(
        "pgm_signal_strength" / SignalStrengthAdapter(Bytes(16)),
        "repeater_signal_strength" / SignalStrengthAdapter(Bytes(2)),
        "keypad_signal_strength" / SignalStrengthAdapter(Bytes(8)),
        "_not_used1" / Padding(6)
    ),
    5: Struct(
        "zone_exit_delay" / StatusAdapter(Bytes(4)),
        "_not_used0" / Padding(28)
    ),
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
        "time" / DateAdapter(Bytes(6)),
        "event" / Struct(
            "major" / Int8ub,
            "minor" / Int8ub
        ),
        "partition" / ExprAdapter(Byte, obj_ + 1, obj_ - 1),
        "module_serial" / ModuleSerialAdapter(Bytes(4)),
        "unknown0" / Bytes(1),
        "label" / Bytes(16),
        "unknown1" / Bytes(1),
        "reserved0" / Bytes(4),
    )),
                   "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

CloseConnection = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x70, Int8ub)
        ),
        "_not_used0" / Const(0, Int8ub),
        "validation_byte" / Default(Int8ub, 0),
        "_not_used1" / Padding(29),
        "message" / Default(Enum(Int8ub,
                                 authentication_failed=0x12,
                                 panel_will_disconnect=0x05), 0x05),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
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
        "_not_used0" / Default(Int8ub, 0),
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
        "_not_used1" / Padding(33),
    )),
                      "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadEEPROM = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x50, Int8ub)),
        "_not_used0" / Padding(1),
        "address" / Default(Int16ub, 0),
        "_not_used1" / Padding(29),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
                    "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadEEPROMResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "_not_used0" / Padding(1),
        "address" / Int16ub,
        "data" / Bytes(32),
    )),
                            "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadStatusResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0x5, Nibble),
            "status" / Struct(
                "reserved" / Flag,
                "alarm_reporting_pending" / Flag,
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "_not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "address" / Int8ub,
        "data" / Bytes(32),
    )),
                            "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

# noinspection PyUnresolvedReferences
SetTimeDate = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x30, Int8ub)),
        "_not_used0" / Padding(3),
        "century" / Int8ub,
        "year" / Int8ub,
        "month" / Int8ub,
        "day" / Int8ub,
        "hour" / Int8ub,
        "minute" / Int8ub,
        "_not_used1" / Padding(23),
        "source_id" / Default(CommunicationSourceIDEnum, 1),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
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
        "_not_used0" / Padding(35),
    )),
                             "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PerformAction = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct(
            "command" / Const(0x40, Int8ub)),
        "_not_used0" / Padding(1),
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
        "_not_used1" / Padding(29),
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
                "Winload_connected" / Flag,
                "NeWare_connected" / Flag)),
        "_not_used0" / Padding(1),
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
        "_not_used1" / Padding(33),
    )),
                               "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

## EEPROM Structures
DefinitionsParserMap = {
    "zone": Struct(
        "definition" / Enum(Int8ul,
                            disabled=0,
                            delay_1=1,
                            delay_2=2,
                            entry_delay_1_full=3,
                            entry_delay_2_full=4,
                            follow=5,
                            follow_sleep_full=6,
                            follow_full=7,
                            instant=8,
                            instant_sleep_full=9,
                            instant_full=10,
                            instant_fire=11,
                            delayed_fire=12,
                            instant_fire_silent=13,
                            delayed_fire_silent=14,
                            buzzer_24h=15,
                            burglary_24h=16,
                            hold_up_24h=17,
                            gas_24hr=18,
                            heat_24h=19,
                            water_24h=20,
                            freeze_24h=21,
                            panic_24h=22,
                            follow_no_pre_alarm=23,
                            instant_no_pre_alarm=24,
                            keyswitch_maintain=25,
                            keyswitch_momentary=26,
                            instant_no_pre_alarm_stay=33,
                            instant_no_pre_alarm_sleep=34,
                            entry_delay_1_stay_full_instant=35,
                            entry_delay_1_full_instant=36
                            ),
        "partition" / Int8ul,
        "options" / BitStruct(
            "auto_zone_shutdown" / Flag,
            "bypassable" / Flag,
            "rf_supervision" / Flag,
            "alarm_type" / Enum(BitsInteger(2),
                                audible_alarm_steady=0,
                                silent_alarm=1,
                                audible_alarm_pulse=2,
                                report_only=3
                                ),
            "intellizone" / Flag,
            "delay_alarm_transmission" / Flag,
            "force_arming" / Flag
        )
    )
}
