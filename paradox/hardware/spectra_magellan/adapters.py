# -*- coding: utf-8 -*-

from construct import Adapter
import datetime


class DateAdapter(Adapter):
    def _decode(self, obj, context, path):
        return datetime.datetime(obj[0] * 100 + obj[1], obj[2], obj[3], obj[4], obj[5])

    def _encode(self, obj, context, path):
        return [obj.year / 100, obj.year % 100, obj.month, obj.day, obj.hour, obj.minute]


class ModuleSerialAdapter(Adapter):
    def _decode(self, obj, context, path):
        return hex(int(obj[0]) * 10 ^ 8 + int(obj[1]) * 10 ^ 4 + int(obj[2]) * 10 ^ 2 + int(
            obj[3]) * 10 ^ 0)


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
                r[i * 8 + j + 1] = (((status >> j) & 0x01) == 0x01)

        return r


class PartitionStatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        partition_status = dict()

        for i in range(0, 2):
            partition_status[i + 1] = dict(
                alarm=(obj[0 + i * 4] & 0xf0 != 0) or (obj[2 + i * 4] & 0x80 != 0),  # Combined status
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
                was_bypassed=(obj[i] & 0x01) != 0)

        return zone_status


class SignalStrengthAdapter(Adapter):
    def _decode(self, obj, context, path):
        strength = dict()
        for i in range(0, len(obj)):
            strength[i + 1] = obj[i]
        return strength

