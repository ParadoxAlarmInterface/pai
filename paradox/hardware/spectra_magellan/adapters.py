import datetime
from enum import Enum

from construct import Adapter


class DateAdapter(Adapter):
    def _decode(self, obj, context, path):
        return datetime.datetime(obj[0] * 100 + obj[1], obj[2], obj[3], obj[4], obj[5])

    def _encode(self, obj, context, path):
        return [
            obj.year / 100,
            obj.year % 100,
            obj.month,
            obj.day,
            obj.hour,
            obj.minute,
        ]


class ModuleSerialAdapter(Adapter):
    def _decode(self, obj, context, path):
        return hex(
            int(obj[0]) * 10
            ^ 8 + int(obj[1]) * 10
            ^ 4 + int(obj[2]) * 10
            ^ 2 + int(obj[3]) * 10
            ^ 0
        )


class PartitionStateAdapter(Adapter):
    states = dict(arm=4, disarm=5, arm_sleep=3, arm_stay=1, none=0)

    def _decode(self, obj, context, path):
        for k, v in enumerate(self.states):
            if v == obj[0]:
                return k

        return "unknown"

    def _encode(self, obj, context, path):
        if obj in self.states:
            return self.states[obj]

        return 0


class ZoneStateAdapter(Adapter):
    states = dict(bypass=0x10)

    def _decode(self, obj, context, path):
        for k, v in enumerate(self.states):
            if v == obj[0]:
                return k

        return "unknown"

    def _encode(self, obj, context, path):
        if obj in self.states:
            return self.states[obj]

        return 0


class StatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        r = dict()
        for i in range(0, len(obj)):
            status = obj[i]
            for j in range(0, 8):
                r[i * 8 + j + 1] = ((status >> j) & 0x01) == 0x01

        return r


class PartitionStatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        partition_status = dict()

        for i in range(0, 2):
            partition_status[i + 1] = dict(
                alarm=(obj[0 + i * 4] & 0xF0 != 0)
                or (obj[2 + i * 4] & 0x80 != 0),  # Combined status
                pulse_fire_alarm=obj[0 + i * 4] & 0x80 != 0,
                audible_alarm=obj[0 + i * 4] & 0x40 != 0,
                silent_alarm=obj[0 + i * 4] & 0x20 != 0,
                strobe_alarm=obj[0 + i * 4] & 0x10 != 0,
                arm_stay=obj[0 + i * 4] & 0x04 != 0,
                arm_sleep=obj[0 + i * 4] & 0x02 != 0,
                arm=obj[0 + i * 4] & 0x01 != 0,
                bell_activated=obj[1 + i * 4] & 0x80 != 0,
                auto_arming_engaged=obj[1 + i * 4] & 0x40 != 0,
                recent_closing_delay=obj[1 + i * 4] & 0x20 != 0,
                intellizone_delay=obj[1 + i * 4] & 0x10 != 0,
                zone_bypassed=obj[1 + i * 4] & 0x08 != 0,
                alarms_in_memory=obj[1 + i * 4] & 0x04 != 0,
                entry_delay=obj[1 + i * 4] & 0x02 != 0,
                exit_delay=obj[1 + i * 4] & 0x01 != 0,
                paramedic_alarm=obj[2 + i * 4] & 0x80 != 0,
                _not_used1=obj[2 + i * 4] & 0x40 != 0,
                arm_with_remote=obj[2 + i * 4] & 0x20 != 0,
                transmission_delay_finished=obj[2 + i * 4] & 0x10 != 0,
                bell_delay_finished=obj[2 + i * 4] & 0x08 != 0,
                entry_delay_finished=obj[2 + i * 4] & 0x04 != 0,
                exit_delay_finished=obj[2 + i * 4] & 0x02 != 0,
                intellizone_delay_finished=obj[2 + i * 4] & 0x01 != 0,
                _not_used2=obj[3 + i * 4] & 0x80 != 0,
                wait_window=obj[3 + i * 4] & 0x40 != 0,
                _not_used3=obj[3 + i * 4] & 0x20 != 0,
                in_remote_delay=obj[3 + i * 4] & 0x10 != 0,
                _not_used4=obj[3 + i * 4] & 0x08 != 0,
                stayd_mode_active=obj[3 + i * 4] & 0x04 != 0,
                arm_force=obj[3 + i * 4] & 0x02 != 0,
                ready_status=obj[3 + i * 4] & 0x01 != 0,
            )

        return partition_status


class ZoneStatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        zone_status = dict()
        for i in range(0, len(obj)):
            zone_status[i + 1] = dict(
                was_in_alarm=(obj[i] & 0x80) != 0,
                alarm=(obj[i] & 0x40) != 0,
                fire_delay=(obj[i] & 0b00110000) == 0b00110000,
                entry_delay=(obj[i] & 0b00010000) == 0b00010000,
                intellizone_delay=(obj[i] & 0b00100000) == 0b00010000,
                no_delay=(obj[i] & 0b00110000) == 0,
                bypassed=(obj[i] & 0x08) != 0,
                shutdown=(obj[i] & 0x04) != 0,
                in_tx_delay=(obj[i] & 0x02) != 0,
                was_bypassed=(obj[i] & 0x01) != 0,
            )

        return zone_status


class PGMStatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        pgm_status = dict()
        for i in range(0, len(obj)):
            pgm_status[i + 1] = dict(
                on=(obj[i] & 32) != 0,
            )

        return pgm_status


class SignalStrengthAdapter(Adapter):
    def _decode(self, obj, context, path):
        strength = dict()
        for i in range(0, len(obj)):
            strength[i + 1] = obj[i]
        return strength


class PGMDefinitionAdapter(Adapter):
    class PGMEvent(Enum):
        zone_ok = 0
        zone_open = 1
        partition_status = 2
        bell_status = 3
        non_reportable_event = 6
        remote_control_access = 7
        pgm_activation_8 = 8
        pgm_activation_9 = 9
        pgm_activation_10 = 10
        pgm_activation_11 = 11
        cold_start_wireless_zone = 12
        cold_start_wireless_output_module = 13
        bypass_programming = 14
        user_code_activated_output = 15
        wireless_smoke_maintenance_signal = 16
        delay_zone_alarm_transmission = 17
        zone_signal_strength_weak_1 = 18
        zone_signal_strength_weak_2 = 19
        zone_signal_strength_weak_3 = 20
        zone_signal_strength_weak_4 = 21
        button_pressed_on_remote1 = 22
        button_pressed_on_remote2 = 23
        fire_delay_started = 24
        upload_download_software_access = 26
        bus_module_added_removed = 27
        stayd_pass_acknowledged = 28
        arming_with_user = 29
        special_arming = 30
        disarming_with_user = 31
        disarming_after_alarm_with_user = 32
        alarm_cancelled_with_user = 33
        special_disarming = 34
        zone_bypassed = 35
        zone_in_alarm = 36
        fire_alarm = 37
        zone_alarm_restore = 38
        fire_alarm_restore = 39
        special_alarm = 40
        zone_shutdown = 41
        zone_tampered = 42
        zone_tamper_restored = 43
        new_trouble = 44
        trouble_restored = 45
        bus_module_new_trouble = 46
        bus_module_trouble_restored = 47
        special = 48
        low_battery_on_zone = 49
        low_battery_on_zone_restore = 50
        zone_supervision_trouble = 51
        zone_supervision_restore = 52
        wireless_output_supervision_trouble = 53
        wireless_output_supervision_restore = 54
        wireless_output_tamper_trouble = 55
        wireless_output_tamper_trouble_restore = 56
        non_medical_alarm = 57
        zone_was_forced = 58
        zone_included = 59
        force_zone_has_been_rearmed = 60
        system_status = 64

    def _decode(self, obj, context, path):
        disabled = sum(obj) == 0

        if disabled:
            return "disabled"

        try:
            activation_event = (
                PGMDefinitionAdapter.PGMEvent(obj[0])
                if sum(obj[:3]) != 0
                else "disabled"
            )
        except Exception:
            activation_event = "unknown"

        try:
            deactivation_event = (
                PGMDefinitionAdapter.PGMEvent(obj[3])
                if sum(obj[3:]) != 0
                else "disabled"
            )
        except Exception:
            deactivation_event = "unknown"

        return dict(activation=activation_event, deactivation=deactivation_event)
