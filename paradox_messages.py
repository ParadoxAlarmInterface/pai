# -*- coding: utf-8 -*-

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
    
    if message[0] == 0x70:
        return CloseConnection.parse(message)
    elif message[0] == 0x72 and message[1] == 0:
        return InitiateCommunication.parse(message)
    elif message[0] == 0x72 and message[1] == 0xFF:
        return InitiateCommunicationResponse.parse(message)
    elif message[0] >> 4 == 0x7:
        return ErrorMessage.parse(message)
    elif message[0] == 0x5F:
        return StartCommunication.parse(message)
    elif message[0] == 0x00 and message[4] > 0:
        return StartCommunicationResponse.parse(message)
    elif message[0] == 0x00:
        return InitializeCommunication.parse(message)
    elif message[0] == 0x10:
        return InitializeCommunicationResponse.parse(message)
    elif message[0] == 0x30:
        return SetTimeDate.parse(message)
    elif message[0] >> 4 == 0x03:
        return SetTimeDateResponse.parse(message)
    elif message[0] == 0x40:
        return PerformAction.parse(message)
    elif message[0] >> 4 == 4:
        return PerformActionResponse.parse(message)
    elif message[0] == 0x50 and message[2] == 0x80:
        return PanelStatus.parse(message)
    elif message[0] == 0x50 and message[2] < 0x80:
        return ReadEEPROM.parse(message)
    elif message[0] >> 4 == 0x05 and message[2] == 0x80:
        return PanelStatusResponse[message[3]].parse(message)
    elif message[0] >> 4 == 0x05 and message[2] < 0x80:
        return ReadEEPROMResponse.parse(message)
    elif message[0] == 0x60 and message[2] < 0x80:
        return WriteEEPROM.parse(message)
    elif message[0] >> 4 == 0x06 and message[2] < 0x80:
        return WriteEEPROMResponse.parse(message)
    elif message[0] >> 4 == 0x0e:
        return LiveEvent.parse(message)
    else:
        print("Unknown message")
        for c in message:
            print("{:02x} ".format(c), end='')
        print()
        return None


InitiateCommunication = Struct("fields" / RawCopy(
    Struct("po" / BitStruct(
                "command" / Const(7, Nibble), 
                "reserved0" / Const(2, Nibble)), 
            "reserved1" / Padding(35))), 
    "checksum" / Checksum(Bytes(1), 
        lambda data: calculate_checksum(data), this.fields.data))

InitiateCommunicationResponse = Struct("fields" / RawCopy(
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
        "product_id" / Enum(Int8ub,
            DIGIPLEX_v13=0,
            DIGIPLEX_v2=1,
            DIGIPLEX_NE=2,
            DIGIPLEX_EVO_48=3,
            DIGIPLEX_EVO_96=4,
            DIGIPLEX_EVO_192=5,
            MAGELLAN_MG5050=38), 
        "talker" / Enum(Int8ub,
            BOOT_LOADER=0,
            CONTROLLER_APPLICATION=1,
            MODULE_APPLICATION=2), 
        "application" / Struct(
            "version" / Int8ub, 
            "revision" / Int8ub, 
            "build" / Int8ub),
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
        "label" / Bytes(8))),

    "checksum" / Checksum(
        Bytes(1), 
        lambda data: calculate_checksum(data), this.fields.data))


InitializeCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x00, Int8ub)),
        "not_used0" / Padding(3),
        "product_id" / Enum(Int8ub,
            DIGIPLEX_v13=0,
            DIGIPLEX_v2=1,
            DIGIPLEX_NE=2,
            DIGIPLEX_EVO_48=3,
            DIGIPLEX_EVO_96=4,
            DIGIPLEX_EVO_192=5,
            SPECTRA_SP5500=21,
            SPECTRA_SP6000=22,
            SPECTRA_SP7000=23,
            MAGELLAN_MG5000=64,
            MAGELLAN_MG5050=65), 
        "firmware" / Struct(
            "version" / Int8ub, 
            "revision" / Int8ub, 
            "build" / Int8ub),
        "panel_id" / Int16ub, 
        "pc_password" / Default(Int16ub, 0x0000),
        "not_used1" / Padding(1),
        "source_method" / Default(Enum(Int8ub,
            Winload_Connection=0x00,
            NEware_Connection=0x55), 0x00),
        "user_code" / Default(Int32ub, 0x00000000),
        "not_used2" / Padding(16),
        "user_id" / Struct(
            "high" / Default(Int8ub, 0),
            "low" / Default(Int8ub, 0)),
        )),
    "checksum" / Checksum(
            Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

InitializeCommunicationResponse = Struct("fields" / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x10, Int8ub)),
            "neware_connection" / Int16ub,
            "user_id_low" / Int8ub, 
            "partition_rights" / BitStruct(
                "not_used" / BitsInteger(6),
                "partition_2" / Flag,
                "partition_1" / Flag),
            "not_used0" / Padding(31),
               )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

StartCommunication = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x5F, Int8ub)),
        "validation" / Const(0x20, Int8ub),
        "not_used0" / Padding(31),
        "source_id" / Default(Enum(Int8ub,
            NonValid_Source=0,
            Winload_Direct=1,
            Winload_IP=2,
            Winload_GSM=3,
            Winload_Dialer= 4,
            NeWare_Direct=5,
            NeWare_IP=6,
            NeWare_GSM=7,
            NeWare_Dialer=8,
            IP_Direct=9,
            VDMP3_Direct=10,
            VDMP3_GSM=11), 0),
        "user_id" / Struct(
            "high" / Default(Int8ub, 0),
            "low" / Default(Int8ub, 0)),
    )), "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

StartCommunicationResponse = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct("command" / Const(0, Nibble),
            "status" / Struct(
                "reserved" / Flag, 
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag, 
                "NeWare_connected" / Flag)
            ),
        "not_used0" / Bytes(3),
        "product_id" / Enum(Int8ub,
            DIGIPLEX_v13=0,
            DIGIPLEX_v2=1,
            DIGIPLEX_NE=2,
            DIGIPLEX_EVO_48=3,
            DIGIPLEX_EVO_96=4,
            DIGIPLEX_EVO_192=5,
            SPECTRA_SP5500=21,
            SPECTRA_SP6000=22,
            SPECTRA_SP7000=23,
            MAGELLAN_MG5000=64,
            MAGELLAN_MG5050=65), 
        "firmware" / Struct(
            "version" / Int8ub, 
            "revision" / Int8ub, 
            "build" / Int8ub),
        "panel_id" / Int16ub, 
        "not_used1" / Bytes(5),
        "transceiver" / Struct(
            "firmware_build" / Int8ub,
            "family" / Int8ub,
            "firmware_version" / Int8ub,
            "firmware_revision" / Int8ub,
            "noise_floor_level" / Int8ub,
            "status" / BitStruct(
                "not_used" / BitsInteger(6),
                "noise_floor_high" / Flag,
                "constant_carrier"  / Flag,
                ),
            "hardware_revision" / Int8ub,
            ),
        "not_used2" / Bytes(14),
        )), 
    "checksum" / Checksum(
            Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PanelStatus = Struct("fields" / RawCopy(
    Struct(
        "po" / Struct("command" / Const(0x50, Int8ub)),
        "not_used0" / Default(Int8ub, 0x00),
        "validation" / Default(Int8ub, 0x00),
        "status_request" / Default(Int8ub, 0x00),
        "not_used0" / Padding(29),
        "source_id" / Default(Int8ub, 0),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
        )),
    Padding(31),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

PanelStatusResponse = [ 
    Struct("fields" / RawCopy(Struct(
        "po" / BitStruct(
            "command" / Const(5, Nibble), 
            "status" / Struct(
                "reserved" / Flag, 
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag, 
                "NeWare_connected" / Flag)
        ),
        "not_used0" / Padding(1),
        "validation" / Const(0x80, Int8ub),
        "status_request" / Const(0, Int8ub),
        "troubles" /BitStruct(
            "timer_loss" / Flag,
            "fire_loop" / Flag,
            "module_tamper" / Flag,
            "zone_tamper" / Flag,
            "communication" / Flag,
            "bell" / Flag,
            "power" / Flag,
            "rf_low_battery" / Flag,
            "rf_interference" / Flag,
            "not_used0" / BitsInteger(5),
            "module_supervision" / Flag,
            "zone_supervision" / Flag,
            "not_used0" / BitsInteger(1),
            "wireless_repeater_battery" / Flag,
            "wireless_repeater_ac_loss" / Flag,
            "wireless_leypaad _battery" / Flag,
            "wireless_leypad_ac" / Flag,
            "auxiliary_output_overload" / Flag,
            "ac_failure" / Flag,
            "low_battery" / Flag,
            "not_used1" / BitsInteger(6),
            "bell_output_overload" / Flag,
            "bell_output_disconnected" / Flag,
            "not_used2" / BitsInteger(2),
            "computer_fail_to_communicate" / Flag,
            "voice_fail_to_communicate" / Flag,
            "pager_fail_to_communicate" / Flag,
            "central_2_reporting_ftc_indicator" / Flag,
            "central_1_reporting_ftc_indicator" / Flag,
            "telephone_line" / Flag),
        "time" / DateAdapter(Bytes(6)),
        "vdc" / ExprAdapter(Byte, obj_ * (20.3 - 1.4) / 255.0 + 1.4, 0),
        "dc" / ExprAdapter(Byte, obj_ * 22.8 / 255.0, 0),
        "battery" / ExprAdapter(Byte, obj_ * 22.8 / 255.0, 0),
        "rc_noise_floor" / Int8ub, 
        "zone_open_status" / StatusAdapter( Bytes(4) ),
        "zone_tamper_status" / StatusAdapter( Bytes(4) ),
        "pgm_tamper_status" / StatusAdapter( Bytes(2) ),
        "bus_tamper_status" / StatusAdapter( Bytes(2) ),
        "zone_fire_status" / StatusAdapter( Bytes(4) ),
        "not_used1" / Int8ub)),
        "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
        ,
        Struct("fields" / RawCopy(Struct(
            "po" / BitStruct(
                "command" / Const(5, Nibble), 
                "status" / Struct(
                    "reserved" / Flag, 
                    "alarm_reporting_pending" / Flag,
                    "Windload_connected" / Flag, 
                    "NeWare_connected" / Flag)),
            "not_used0" / Padding(1),
            "validation" / Const(0x80, Int8ub),
            "status_request" / Const(1, Int8ub),
            "zone_rf_supervision_trouble" / StatusAdapter( Bytes(4) ),
            "pgm_supervision_trouble" / StatusAdapter( Bytes(2) ),
            "bus_supervision_trouble" / StatusAdapter( Bytes(2) ),
            "wireless_keypad_repeater_supervision_trouble" / StatusAdapter( Bytes(1) ),
            "zone_rf_low_battery_trouble" / StatusAdapter( Bytes(4) ),
            "partition_status" / PartitionStatusAdapter( Bytes(8)),
            "wireless_repeater_ac_loss" / StatusAdapter( Bytes(1) ),
            "wireless_repeater_battery_failure" / StatusAdapter( Bytes(1) ),
            "wireless_keypad_ac_loss" / StatusAdapter( Bytes(1)),
            "wireless_keypad_battery_failure" / StatusAdapter( Bytes(1)),
            "wireless_keypad_supervision_failure" / StatusAdapter( Bytes(1)),
            "not_used1" / Padding(6)
        )),
        "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
        ,
        Struct("fields" / RawCopy(Struct(
            "po" / BitStruct(
                "command" / Const(5, Nibble), 
                "status" / Struct(
                    "reserved" / Flag, 
                    "alarm_reporting_pending" / Flag,
                    "Windload_connected" / Flag, 
                    "NeWare_connected" / Flag)),
            "not_used0" / Padding(1),
            "validation" / Const(0x80, Int8ub),
            "status_request" / Const(2, Int8ub),
            "zone_status" / ZoneStatusAdapter( Bytes(32) )
        )),
        "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
        ,
        Struct("fields" / RawCopy(Struct(
            "po" / BitStruct(
                "command" / Const(5, Nibble), 
                "status" / Struct(
                    "reserved" / Flag, 
                    "alarm_reporting_pending" / Flag,
                    "Windload_connected" / Flag, 
                    "NeWare_connected" / Flag)),
            "not_used0" / Padding(1),
            "validation" / Const(0x80, Int8ub),
            "status_request" / Const(3, Int8ub),
            "zone_signal_strength" / SignalStrengthAdapter( Bytes(32) )
        )),
        "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
        ,
        Struct("fields" / RawCopy(Struct(
            "po" / BitStruct(
                "command" / Const(5, Nibble), 
                "status" / Struct(
                    "reserved" / Flag, 
                    "alarm_reporting_pending" / Flag,
                    "Windload_connected" / Flag, 
                    "NeWare_connected" / Flag)),
            "not_used0" / Padding(1),
            "validation" / Const(0x80, Int8ub),
            "status_request" / Const(4, Int8ub),
            "pgm_signal_strength" / SignalStrengthAdapter( Bytes(16) ) ,
            "wireless_repeater_signal_strength" / SignalStrengthAdapter( Bytes(2) ),
            "wireless_keypad_signal_strength" / SignalStrengthAdapter( Bytes(8) ),
            "not_used1" / Padding(6)
        )),
        "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
        ,
        Struct("fields" / RawCopy(Struct(
            "po" / BitStruct(
                "command" / Const(5, Nibble), 
                "status" / Struct(
                    "reserved" / Flag, 
                    "alarm_reporting_pending" / Flag,
                    "Windload_connected" / Flag, 
                    "NeWare_connected" / Flag)),
            "not_used0" / Padding(1),
            "validation" / Const(0x80, Int8ub),
            "status_request" / Const(5, Int8ub),
            "zone_exit_delay" / StatusAdapter( Bytes(4) ),
            "not_used1" / Padding(28)
        )),
        "checksum" / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data))
        ]

LiveEvent = Struct("fields" / RawCopy(
    Struct(
        "po" / BitStruct(
            "command" / Const(0xE, Nibble), 
            "status" / Struct(
                "reserved" / Flag, 
                "alarm_reporting_pending" / Flag,
                "Windload_connected" / Flag, 
                "NeWare_connected" / Flag)),
        "time" / DateAdapter(Bytes(6)),
        "event" / EventAdapter(Bytes(2)),
        "partition" / ExprAdapter(Byte, obj_ + 1, obj_ - 1),
        "module_serial" / ModuleSerialAdapter(Bytes(4)),
        "label_type" / Bytes(1),
        "label" / Bytes(16),
        "unknown" / Bytes(1),
        "reserved2" / Bytes(4),
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
            PGM_On_Overwrite=0x30,
            PGM_Off_Overwrite=0x31,
            PGM_On=0x32,
            PGM_Off=0x33,
            Reload_RAM=0x80),
        "argument"/ ExprAdapter(Byte, obj_ + 1, obj_ - 1),
        "not_used0" / Padding(29),
        "source_id" / Default(Int8ub, 0),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )), 
    "checksum" / Checksum(
    Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

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
        "not_used0" / Const(0, Int8ub),
        "validation_byte" / Default(Int8ub, 0),
        "not_used1" / Padding(30),
        "message" / Default(Enum(Int8ub, panel_will_disconnect=0x05), 0x05),
        "source_id" / Default(Int8ub, 0),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
    )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ErrorMessage = Struct("fields" / RawCopy(
    Struct(
      "po" / BitStruct(
          "command" / Const(0x7, Nibble),
          "status" / Struct(
            "reserved" / Flag, 
            "alarm_reporting_pending" / Flag,
            "Windload_connected" / Flag, 
            "NeWare_connected" / Flag)),
      "not_used0" / Default(Int8ub, 0),
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
        "not_used1" / Padding(33),
    )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadEEPROM = Struct("fields" / RawCopy(
     Struct(
	"po" / Struct("command" / Const(0x50, Int8ub)),
	"not_used0" / Padding(1),
        "address" / Default(Int16ub, 0),
        "not_used0" / Padding(29),
        "source_id" / Default(Int8ub, 0),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
        )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

ReadEEPROMResponse = Struct("fields" / RawCopy(
     Struct(
        "po" / BitStruct(
          "command" / Const(0x5, Nibble),
          "status" / Struct(
            "reserved" / Flag, 
            "alarm_reporting_pending" / Flag,
            "Windload_connected" / Flag, 
            "NeWare_connected" / Flag)),
	"not_used0" / Padding(1),
        "address" / Default(Int16ub, 0),
        "data" / Bytes(32),
        )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

SetTimeDate = Struct("fields" / RawCopy(Struct(
        "po" / Struct(
            "command" / Const(0x30, Int8ub)),
	"not_used0" / Padding(3),
        "century" / Int8ub,
        "year" / Int8ub,
        "month" /Int8ub,
        "day" / Int8ub,
        "hour" / Int8ub,
        "minute" / Int8ub,
        "not_used1" / Padding(23),
        "source_id" / Default(Int8ub, 0),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
        )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

SetTimeDateResponse = Struct("fields" / RawCopy(
     Struct(
        "po" / BitStruct(
          "command" / Const(0x3, Nibble),
          "status" / Struct(
            "reserved" / Flag, 
            "alarm_reporting_pending" / Flag,
            "Windload_connected" / Flag, 
            "NeWare_connected" / Flag)),
         "not_used0" / Padding(35),
        )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

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
            PGM_On_Overwride=0x30,
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
        "source_id" / Default(Int8ub, 0),
        "user_high" / Default(Int8ub, 0),
        "user_low" / Default(Int8ub, 0),
        )),
    "checksum" / Checksum(
        Bytes(1), lambda data: calculate_checksum(data), this.fields.data))

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
            PGM_On_Overwrite=0x30,
            PGM_Off_Overrite=0x31,
            PGM_On=0x32,
            PGM_Of=0x33,
            Reload_RAM=0x80,
            Bus_Scan=0x85,
            Future_Use=0x90),
        "not_used1" / Padding(33),
        )),
        "checksum" / Checksum(
            Bytes(1), lambda data: calculate_checksum(data), this.fields.data))








