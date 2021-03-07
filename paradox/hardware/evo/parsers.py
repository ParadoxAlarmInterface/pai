import binascii
from collections.abc import Mapping

from construct import (Array, BitsInteger, BitsSwapped, BitStruct, Bitwise,
                       Byte, Bytes, ByteSwapped, Checksum, Computed, Const,
                       Default, Embedded, Enum, ExprAdapter,
                       ExprSymmetricAdapter, Flag, Int8ub, Int16ub, Int16ul,
                       Int24ub, Nibble, Padding, RawCopy, Struct, Subconstruct,
                       ValidationError, obj_, this)

from ..common import (CommunicationSourceIDEnum, PacketChecksum, PacketLength,
                      ProductIdEnum, calculate_checksum)
from .adapters import (DateAdapter, DictArray, EnumerationAdapter,
                       EventAdapter, ModuleTroubles, PartitionStatus, PGMFlags,
                       StatusFlags, ZoneFlagBitStruct, ZoneFlags)

LoginConfirmationResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0x1, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "length" / PacketLength(Int8ub),
            "result"
            / BitStruct(
                "_not_used0" / BitsInteger(3),
                "neware_answer" / Flag,
                "_not_used1" / BitsInteger(4),
            ),
            "callback" / Int16ub,
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

InitializeCommunication = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x00, Int8ub)),
            "module_address" / Default(Int8ub, 0x00),  # (00= panel/module)
            "_not_used0" / Padding(2),
            "product_id" / ProductIdEnum,
            "firmware"
            / Struct("version" / Int8ub, "revision" / Int8ub, "build" / Int8ub),
            "panel_id" / Int16ub,
            "pc_password" / Default(Bytes(2), b"0000"),
            "modem_speed" / Bytes(1),
            "source_method"
            / Default(
                Enum(Int8ub, Winload_Connection=0x00, NEware_Connection=0x55), 0x00
            ),
            "user_code" / Default(Int24ub, 0x000000),
            "serial_number" / Bytes(4),
            "system_options"
            / BitsSwapped(
                BitStruct(
                    Embedded(
                        Struct(  # EVO section data 3030
                            "pgm1_smoke" / Flag,
                            "no_bell_cut_off" / Flag,
                            "daylight_saving_time" / Flag,
                            "shabbat_feature" / Flag,
                            "battery_charge_current" / Flag,
                            "ac_failure_not_displayed_as_trouble" / Flag,
                            "clear_bell_limit_trouble" / Flag,
                            "combus_speed" / Flag,
                        )
                    ),
                    "partitions" / StatusFlags(8),  # EVO section data 3031
                    "siren_output_partition" / StatusFlags(8),  # EVO section data 3032
                    Embedded(
                        Struct(  # EVO section data 3033
                            "multiple_actions_user_menu" / Flag,
                            "user_code_length_flexible" / Flag,
                            "user_code_length_6" / Flag,
                            "power_save_mode" / Flag,
                            "bypass_not_displayed_when_armed" / Flag,
                            "trouble_latch" / Flag,
                            "eol_resistor_on_harwire_zones" / Flag,
                            "atz" / Flag,
                        )
                    ),
                    Embedded(
                        Struct(  # EVO section data 3034
                            "wireless_transmitter_supervision_options" / BitsInteger(2),
                            "generate_supervision_failure_on_bypassed_wireless_zone"
                            / Flag,
                            "restrict_arming_on_wireless_transmitter_supervision_failure"
                            / Flag,
                            "tamper_recognition_options" / BitsInteger(2),
                            "generate_tamper_if_detected_on_bypassed_zone" / Flag,
                            "restrict_arming_on_tamper" / Flag,
                        )
                    ),
                    Embedded(
                        Struct(  # EVO section data 3035
                            "restrict_arming_on_ac_failure" / Flag,
                            "restrict_arming_on_battery_failure" / Flag,
                            "restrict_arming_on_bell_or_aux_failure" / Flag,
                            "restrict_arming_on_tlm_failure" / Flag,
                            "restrict_arming_on_module_troubles" / Flag,
                            "account_number_transmission" / Flag,
                            "transmit_zone_status_on_serial_port" / Flag,
                            "serial_port_baud_rate_57600" / Flag,
                        )
                    ),
                    Embedded(
                        Struct(  # EVO section data 3036
                            "telephone_line_monitoring" / BitsInteger(2),
                            "dialer_reporting" / Flag,
                            "dialing_method" / Flag,
                            "pulse_ratio" / Flag,
                            "busy_tone_detection" / Flag,
                            "switch_to_pulse_dialing" / Flag,
                            "bell_siren_upon_communication_failure" / Flag,
                        )
                    ),
                    Embedded(
                        Struct(  # EVO section data 3037
                            "call_back" / Flag,
                            "automatic_event_buffer_transmission" / Flag,
                            "autotest_report_transmission_options" / BitsInteger(2),
                            "keypad_beep_on_successful_arming_disarming_report" / Flag,
                            "alternate_dialing" / Flag,
                            "dial_tone_delay" / Flag,
                            "report_zone_restore" / Flag,
                        )
                    ),
                    Embedded(
                        Struct(  # EVO section data 3038
                            "access_control_feature" / Flag,
                            "log_request_for_exit" / Flag,
                            "log_door_left_open_restore" / Flag,
                            "log_door_forced_restore" / Flag,
                            "bulglar_alarm_on_forced_door" / Flag,
                            "skip_exit_delay_when_arming_with_access_card" / Flag,
                            "bulglar_alarm_on_door_left_open" / Flag,
                            "who_has_access_during_clock_loss" / Flag,
                        )
                    ),
                )
            ),
            "_not_used1" / Padding(4),
            "source_id" / Default(CommunicationSourceIDEnum, 1),
            "carrier_length" / Bytes(1),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

RAMDataParserMap = {
    1: Struct(
        "_weekday" / Int8ub,
        "_system_flags" / BitStruct(  # TODO: Do we need BitsSwapped here?
            "chime_zone_partition" / BitsSwapped(StatusFlags(4)),
            "power_smoke" / Flag,
            "ground_start" / Flag,
            "kiss_off" / Flag,
            "line_ring" / Flag
        ),
        "partition_bell" / BitsSwapped(Bitwise(StatusFlags(8))),
        "partition_fire_alarm" / BitsSwapped(Bitwise(StatusFlags(8))),
        "partition_open_close_kiss_off" / BitsSwapped(Bitwise(StatusFlags(8))),
        "key-switch_triggered" / BitsSwapped(Bitwise(StatusFlags(32))),
        "door_open" / BitsSwapped(Bitwise(StatusFlags(32))),
        "system"
        / Struct(
            "troubles"
            / BitStruct( # time_lost_trouble when actually battery_failure
                "time_lost_trouble" / Flag,
                "zone_fault_trouble" / Flag,
                "zone_low_battery_trouble" / Flag,
                "zone_tamper_trouble" / Flag,
                "module_supervision_trouble" / Flag,  # BusCom
                "module_trouble" / Flag,
                "dialer_trouble" / Flag,
                "system_trouble" / Flag,

                "panel_tamper_trouble" / Flag,
                "_future_use_0" / Flag,
                "rom_error_trouble" / Flag,
                "bell_absent_trouble" / Flag,
                "bell_limit_trouble" / Flag,
                "aux_limit_trouble" / Flag,
                "battery_failure_trouble" / Flag,
                "ac_trouble" / Flag,

                "_future_use_1" / Flag,
                "_future_use_2" / Flag,
                "com_pc_trouble" / Flag,
                "fail_central_4_trouble" / Flag,
                "fail_central_3_trouble" / Flag,
                "fail_central_2_trouble" / Flag,
                "fail_central_1_trouble" / Flag,
                "tlm_trouble" / Flag,

                "module_aux_trouble" / Flag,
                "module_battery_fail" / Flag,
                "module_ac_trouble" / Flag,
                "module_printer_trouble" / Flag,
                "module_fail_to_com_trouble" / Flag,
                "module_tlm_trouble" / Flag,
                "module_rom_error_trouble" / Flag,
                "module_tamper_trouble" / Flag,

                "mdl_com_error" / Flag,
                "bus_overload_trouble" / Flag,
                "bus_global_fail" / Flag,
                "safety_mismatch_trouble" / Flag,
                "_future_use_3" / Flag,
                "_future_use_4" / Flag,
                "missing_module_trouble" / Flag,
                "missing_keypad_trouble" / Flag,
            ),
            "date"
            / Struct(
                "weekday" / Computed(lambda ctx: ctx._._._weekday),
                "time" / DateAdapter(Bytes(7)),
            ),
            "power"
            / Struct(
                "vdc"
                / ExprAdapter(
                    Byte, lambda obj, ctx: round(obj * (20.3 - 1.4) / 255.0 + 1.4, 1), 0
                ),
                "battery"
                / ExprAdapter(Byte, lambda obj, ctx: round(obj * 22.8 / 255.0, 1), 0),
                "dc"
                / ExprAdapter(Byte, lambda obj, ctx: round(obj * 22.8 / 255.0, 1), 0),
            ),
        ),
        "zone_open" / BitsSwapped(Bitwise(StatusFlags(96))),
        "zone_tamper" / BitsSwapped(Bitwise(StatusFlags(96))),
        "zone_low_battery" / BitsSwapped(Bitwise(StatusFlags(96))),
    ),
    2: Struct("zone_status" / ZoneFlags(64)),
    3: Struct(
        "zone_status" / ZoneFlags(32, start_index_from=65),
        "partition_status" / PartitionStatus(Bytes(32)),
    ),
    4: Struct(
        "partition_status" / PartitionStatus(Bytes(16)),
        "system"
        / Struct(
            "panel_status"
            / BitStruct("installer_lock_active" / Flag, "_free" / Padding(7)),
            "event"
            / Struct("_event_pointer" / Int16ub, "_event_pointer_bus" / Int16ub,),
            "_recycle_system" / Array(8, Int8ub),
            "report" / Struct("arm_disarm_delay_timer" / Int8ub,),
        ),
        "_free" / Padding(34),
    ),
    5: Struct(
        "_not_used" / Int8ub,
        "module_trouble" / ModuleTroubles(count=63, start_index_from=1),
    ),
    6: Struct("module_trouble" / ModuleTroubles(count=64, start_index_from=64)),
    7: Struct("module_trouble" / ModuleTroubles(count=64, start_index_from=128)),
    8: Struct(
        "module_trouble" / ModuleTroubles(count=63, start_index_from=192),
        "_not_used" / Int8ub,
    ),
    9: Struct(
        "zone_open" / BitsSwapped(Bitwise(StatusFlags(96, start_index_from=97))),
        "zone_tamper" / BitsSwapped(Bitwise(StatusFlags(96, start_index_from=97))),
        "zone_low_battery" / BitsSwapped(Bitwise(StatusFlags(96, start_index_from=97))),
        "zone_status" / ZoneFlags(28, start_index_from=97),
    ),
    10: Struct("zone_status" / ZoneFlags(64, start_index_from=125)),
    11: Struct(
        "zone_status" / ZoneFlags(4, start_index_from=189), "_not_used" / Bytes(60),
    ),
    16: Struct( # TODO: here should be panel modules
        "module_assigned" / BitsSwapped(Bitwise(StatusFlags(256, start_index_from=1))),
        "module_missing" / BitsSwapped(Bitwise(StatusFlags(256, start_index_from=1))),
    ),
    # 51: Doors [open, state, ...]
    # 56: Disarm delays
    57: Struct("pgm_status" / PGMFlags(16)),
    58: Struct("pgm_status" / PGMFlags(16, start_index_from=17)),
}
# We also need parsers for:
# 17 ram address - EBUS Troubles 24 bytes
# 32 ram address
# 33 ram address
# 34 ram address
# 35 ram address
# 37 ram address
# 38 ram address
# 39 ram address
# 48 ram address
# 49 ram address
# 50 ram address
# 51 ram address - Door Status
# 56 ram address
# 58 ram address


def get_user_definition(settings):
    if (
        settings.system_options.user_code_length_6
        or settings.system_options.user_code_length_flexible
    ):
        code = ExprAdapter(
            Bytes(3),
            lambda obj, path: binascii.hexlify(obj)
            .decode()
            .rstrip("0")
            .replace("a", "0")
            or None,
            lambda obj, path: binascii.unhexlify(obj.replace("0", "a")),
        )
    else:
        code = ExprAdapter(
            Bytes(3),
            lambda obj, path: binascii.hexlify(obj)
            .decode()
            .rstrip("0")
            .replace("a", "0")[:4]
            or None,
            lambda obj, path: binascii.unhexlify((obj + obj[:2]).replace("0", "a")),
        )

    return Struct(
        "code" / code,
        "options"
        / BitsSwapped(
            BitStruct(
                "type" / Enum(BitsInteger(2), FullMaster=0x3, Master=0x2, Regular=0x0),
                "duress" / Flag,
                "bypass" / Flag,
                "arm_only" / Flag,
                "stay_instant_arming" / Flag,
                "force_arming" / Flag,
                "all_subsystems" / Flag,
            )
        ),
        "partitions" / BitsSwapped(Bitwise(StatusFlags(8))),
        "access" / BitStruct("level" / Nibble, "schedule" / Nibble),
        "access_options" / Bytes(1),
        "card_serial_number" / Bytes(3),
    )


DefinitionsParserMap = {
    "zone": BitStruct(
        "definition"
        / Enum(
            Nibble,
            disabled=0x0,
            entry_delay1=0x1,
            entry_delay2=0x2,
            follow=0x3,
            instant=0x4,
            buzzer_24h=0x5,
            burglary_24h=0x6,
            holdup_24h=0x7,
            gas_24h=0x8,
            heat_24h=0x9,
            water_24h=0xA,
            freeze_24h=0xB,
            delayed_fire_24h=0xC,
            standard_fire_24h=0xD,
            stay_delay1=0xE,
            stay_delay2=0xF,
        ),
        "partition" / Nibble,
        "options"
        / ByteSwapped(
            Struct(
                "auto_zone_shutdown_enabled" / Flag,
                "bypass_enabled" / Flag,
                "stay_zone" / Flag,
                "force_zone" / Flag,
                "alarm_type"
                / Enum(
                    BitsInteger(2),
                    steady_alarm=0x0,
                    pulsed_alarm=0x1,
                    silent_alarm=0x2,
                    report_only=0x3,
                ),
                "intellizone" / Flag,
                "delay_before_transmission" / Flag,
            )
        ),
    ),
    "partition": BitsSwapped(  # No need as we get this data during connect in InitializeCommunication system_options
        Bitwise(
            DictArray(
                8,
                1,
                Struct(
                    "_index" / Computed(this._index + 1),
                    "definition"
                    / ExprAdapter(
                        Default(Flag, False),
                        lambda obj, context: "enabled" if obj else "disabled",
                        lambda obj, context: obj == "enabled",
                    ),
                ),
            )
        )
    ),
    "user": get_user_definition,
}

LiveEvent = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0xE, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "event_source" / Const(0xFF, Int8ub),
            "event_nr" / Int16ub,
            "time" / DateAdapter(Bytes(6)),
            "event" / EventAdapter(Bytes(4)),
            "partition" / Computed(this.event.partition),
            "module_serial" / Bytes(4),
            "label_type" / Bytes(1),
            "label" / Bytes(16),
            "_not_used0" / Bytes(1),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

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
    "compressed"
    / BitStruct(
        "day" / BitsInteger(5),
        "month" / BitsInteger(4),
        "century" / BitsInteger(7),
        "year" / BitsInteger(7),
        "hour" / BitsInteger(5),
        "minute" / BitsInteger(6),
        "event_group" / BitsInteger(6),
        "partition" / BitsInteger(4),
        "event_1_high_nibble" / BitsInteger(2),
        "event_2_high_nibble" / BitsInteger(2),
    ),
    "minor_1" / Int8ub,
    "minor_2" / Int8ub,
    "module_serial" / Bytes(4),
)

RequestedEvent = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0xE, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "length" / PacketLength(Int8ub),
            "_not_used0" / Bytes(1),
            "requested_event_nr" / Const(0x00, Int8ub),
            "event_nr" / Int16ub,
            # "data" / Bytes(lambda this: this.length - 7)
            "data" / Array(lambda x: int((x.length - 7) / 12), CompressedEvent),
        )
    ),
    "checksum"
    / Checksum(Bytes(1), lambda data: calculate_checksum(data), this.fields.data),
)

CloseConnection = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x70, Int8ub)),
            "length" / PacketLength(Int8ub),
            "message"
            / Default(
                Enum(
                    Int8ub,
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
                    multibus_not_supported=0x1A,
                    incorrect_number_of_users=0x1B,
                    invalid_label_number=0x1C,
                ),
                0x05,
            ),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)


class EvoEEPROMAddressAdapter(Subconstruct):
    def deep_update(self, d, u):
        for k, v in u.items():
            if isinstance(v, Mapping):
                d[k] = self.deep_update(d.get(k, {}), v)
            else:
                d[k] = v
        return d

    def _build(self, obj, stream, context, path):
        if "control" in obj and obj["control"].get("ram_access"):  # for ram block
            ram_block = (obj["address"] & 0xF0000) >> 16
            self.deep_update(obj, dict(po=dict(block=ram_block)))
        else:  # for eeprom
            if obj["address"] >> 16 > 0x3:
                raise ValidationError("EEPROM address is out of range")
            eeprom_address_high_bits = (obj["address"] & 0x30000) >> 16
            self.deep_update(
                obj, dict(control=dict(_eeprom_address_bits=eeprom_address_high_bits))
            )
        return self.subcon._build(obj, stream, context, path)

    def _parse(self, stream, context, path):
        obj = self.subcon._parsereport(stream, context, path)
        obj.address += obj.control._eeprom_address_bits << 16
        return obj


ReadEEPROM = Struct(
    "fields"
    / RawCopy(
        EvoEEPROMAddressAdapter(
            Struct(
                "po"
                / BitStruct(
                    "command" / Const(0x5, Nibble), "block" / Default(Nibble, 0),
                ),
                "packet_length" / PacketLength(Int8ub),
                "control"
                / BitStruct(
                    "ram_access" / Default(Flag, False),
                    "alarm_reporting_pending" / Default(Flag, False),
                    "Winload_connected" / Default(Flag, False),
                    "NeWare_connected" / Default(Flag, False),
                    "_not_used" / Default(BitsInteger(2), 0),
                    "_eeprom_address_bits" / Default(BitsInteger(2), 0),
                ),
                "bus_address" / Default(Int8ub, 0x00),  # 00 - Panel, 01-FF - Modules
                "address" / ExprSymmetricAdapter(Int16ub, obj_ & 0xFFFF),
                "length" / Int8ub,
            )
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

ReadEEPROMResponse = Struct(
    "fields"
    / RawCopy(
        EvoEEPROMAddressAdapter(
            Struct(
                "po"
                / BitStruct(
                    "command" / Const(0x5, Nibble),
                    "status"
                    / Struct(
                        "reserved" / Flag,
                        "alarm_reporting_pending" / Flag,
                        "Winload_connected" / Flag,
                        "NeWare_connected" / Flag,
                    ),
                ),
                "packet_length" / PacketLength(Int8ub),
                "control"
                / BitStruct(
                    "ram_access" / Flag,  # RAM = 0 or EEPROM = 1
                    "_not_used" / Padding(5),
                    "_eeprom_address_bits"
                    / BitsInteger(2),  # EEPROM address bit 17 and 16
                ),
                "bus_address" / Default(Int8ub, 0x00),  # 00 - Panel, 01-FE - Modules
                "address" / ExprSymmetricAdapter(Int16ub, obj_ & 0xFFFF),
                "data" / Bytes(lambda x: x.packet_length - 7),
            )
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

SetTimeDate = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x30, Int8ub)),
            "packet_length" / PacketLength(Int8ub),
            "_not_used0" / Padding(4),
            "century" / Int8ub,
            "year" / Int8ub,
            "month" / Int8ub,
            "day" / Int8ub,
            "hour" / Int8ub,
            "minute" / Int8ub,
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

SetTimeDateResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0x3, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "length" / Int8ub,
            "_not_used0" / Padding(4),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

_PartitionCommandEnum = Enum(
    Nibble,
    none=0,
    arm=2,
    arm_stay=3,
    arm_instant=4,
    arm_force=5,
    disarm=6,
    beep_keypads=8,
)

PerformPartitionAction = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x40, Int8ub)),
            "packet_length" / PacketLength(Int8ub),
            "_not_used0" / Padding(4),
            "partitions"
            / Bitwise(
                DictArray(
                    8,
                    1,
                    Struct(
                        "_index" / Computed(this._index + 1),
                        "command" / Default(_PartitionCommandEnum, "none"),
                    ),
                    pick_key="command",
                )
            ),
            "instant" / Default(Flag, False),
            "_not_used1" / Padding(3),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

# Used for partitions and PGMs
PerformActionResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0x4, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "packet_length" / PacketLength(Int8ub),
            "_not_used0" / Padding(4),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

ZoneActionBitOperation = Enum(Int8ub, set=0x08, clear=0x00)

PerformZoneAction = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0xD0, Int8ub)),
            "packet_length" / PacketLength(Int8ub),
            "flags" / ZoneFlagBitStruct,
            "operation" / ZoneActionBitOperation,
            "_not_used" / Padding(2),
            "zones" / BitsSwapped(Bitwise(EnumerationAdapter(Array(192, Flag)))),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

PerformZoneActionResponse = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0xD, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "packet_length" / PacketLength(Int8ub),
            "flags" / ZoneFlagBitStruct,
            "operation" / ZoneActionBitOperation,
            "_not_used" / Padding(2),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

_PGMCommandEnum = Enum(Int8ub, release=0, off=1, on=3, on_override=4, off_override=2)

PerformPGMAction = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x40, Int8ub)),
            "packet_length" / PacketLength(Int8ub),
            "unknown0" / Const(0x06, Int8ub),
            "_not_used0" / Padding(3),
            "pgms" / BitsSwapped(Bitwise(EnumerationAdapter(Array(32, Flag)))),
            "_not_used1" / Padding(4),
            "command" / _PGMCommandEnum,
            "_not_used2" / Padding(3),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

_PGMBroadcastCommandEnum = Enum(
    Int8ub,
    no_change=0,
    override_off=1,  # deactivate
    override_on=2,  # activate
    release_off=3,  # My brain breaks while I am trying to understand this
    release=4,  # activate and follow events
)

PGMBroadcastCommand = DictArray(
    16,
    1,
    Struct(
        "_index" / Computed(this._index + 1),
        "command" / Default(_PGMBroadcastCommandEnum, "no_change"),
    ),
    pick_key="command",
)

BroadcastRequest = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0xA, Nibble),
                "module_type" / Default(Flag, False),
                "sub_command"
                / Enum(
                    BitsInteger(3),
                    general_broadcast=0,
                    lcd_message_off=1,
                    lcd_message_low_prority=2,
                    lcd_message_high_prority=3,
                    pgm_override=4,
                ),
            ),
            "packet_length" / PacketLength(Int8ub),
            "bus_address" / Default(Int8ub, 0x00),  # 00 - Panel, 01-FE - Modules
            "_not_used" / Padding(3),
            "data" / Bytes(16),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

BroadcastResponse = Struct(
    "fields"
    / RawCopy(
        EvoEEPROMAddressAdapter(
            Struct(
                "po"
                / BitStruct(
                    "command" / Const(0xA, Nibble),
                    "status"
                    / Struct(
                        "reserved" / Flag,
                        "alarm_reporting_pending" / Flag,
                        "Winload_connected" / Flag,
                        "NeWare_connected" / Flag,
                    ),
                ),
                "packet_length" / PacketLength(Int8ub),
                "bus_address" / Default(Int8ub, 0x00),  # 00 - Panel, 01-FE - Modules
                "control"
                / BitStruct(
                    "ram_access" / Default(Flag, False),
                    "_not_used" / Default(BitsInteger(5), 0),
                    "_eeprom_address_bits" / Default(BitsInteger(2), 0),
                ),
                "address" / ExprSymmetricAdapter(Int16ub, obj_ & 0xFFFF),
            )
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

ErrorMessage = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po"
            / BitStruct(
                "command" / Const(0x7, Nibble),
                "status"
                / Struct(
                    "reserved" / Flag,
                    "alarm_reporting_pending" / Flag,
                    "Winload_connected" / Flag,
                    "NeWare_connected" / Flag,
                ),
            ),
            "length" / PacketLength(Int8ub),
            "message"
            / Enum(
                Int8ub,
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
                multibus_not_supported=0x1A,
                incorrect_number_of_users=0x1B,
                invalid_label_number=0x1C,
            ),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

SendPanicAction = Struct(  # Supported on firmware versions 7.15+
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x40, Int8ub)),
            "packet_length" / PacketLength(Int8ub),
            "unknown0" / Const(0x09, Int8ub),
            "_not_used" / Padding(3),
            "user_id" / Int16ub,
            "panic_type" / Enum(Int8ub, emergency=0, medical=1, fire=2,),  # wild guess
            "partitions" / BitsSwapped(Bitwise(EnumerationAdapter(Array(8, Flag)))),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)

PerformDoorAction = Struct(
    "fields"
    / RawCopy(
        Struct(
            "po" / Struct("command" / Const(0x40, Int8ub)),
            "packet_length" / PacketLength(Int8ub),
            "unknown0" / Const(0x2, Int8ub),
            "_not_used0" / Padding(3),
            "doors" / BitsSwapped(Bitwise(EnumerationAdapter(Array(32, Flag)))),
            "command" / Enum(Int8ub, lock=1, unlock=2),
            "_not_used1" / Padding(2),
            "unknown1" / Const(0x55, Int8ub),
            "user_id" / Default(Int16ul, 0),
        )
    ),
    "checksum" / PacketChecksum(Bytes(1)),
)
