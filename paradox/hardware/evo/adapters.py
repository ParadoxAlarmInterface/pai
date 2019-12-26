# -*- coding: utf-8 -*-

import datetime
from typing import Callable, Any

from construct import *


class DateAdapter(Adapter):
    def _decode(self, obj, context, path):
        return datetime.datetime(obj[0] * 100 + obj[1], obj[2], obj[3], obj[4], obj[5], obj[6] if len(obj) > 6 else 0)

    def _encode(self, obj, context, path):
        return [obj.year / 100, obj.year % 100, obj.month, obj.day, obj.hour, obj.minute, obj.second]


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


ZoneFlagBitStruct = BitStruct(
    "generated_alarm" / Default(Flag, False),
    "presently_in_alarm" / Default(Flag, False),
    "activated_entry_delay" / Default(Flag, False),
    "activated_intellizone_delay" / Default(Flag, False),
    "bypassed" / Default(Flag, False),
    "shutted_down" / Default(Flag, False),
    "tx_delay" / Default(Flag, False),
    "supervision_trouble" / Default(Flag, False),
)


# noinspection PyUnresolvedReferences,PyUnresolvedReferences
class ZoneFlags(Subconstruct):
    flag_parser = ZoneFlagBitStruct

    def __init__(self, count, start_index_from=1):
        super(ZoneFlags, self).__init__(self.flag_parser)

        self.count = count
        self.start_index_from = start_index_from

    def _parse(self, stream, context, path):
        count = self.count
        obj = Container()
        for i in range(self.start_index_from, self.start_index_from + count):
            obj[i] = self.subcon._parsereport(stream, context, path)
        return obj

    def _encode(self, obj, context, path):
        return b"".join([self.flag_parser.build(i) for i in obj])


class FlexibleFlagArrayAdapter(Adapter):
    def __init__(self, subcon, value_decode_fn: Callable[[Any], Any]):
        super(FlexibleFlagArrayAdapter, self).__init__(subcon)
        self.value_decode_fn = value_decode_fn

    def _decode(self, obj, context, path):
        r = dict()
        for i in range(0, len(obj)):
            r[i + 1] = self.value_decode_fn(obj[i])

        return r


class StatusFlagArrayAdapter(Adapter):
    def _decode(self, obj, context, path):
        r = dict()
        for i in range(0, len(obj)):
            status = obj[i]
            r[i + 1] = status

        return r


class StatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        r = dict()
        for i in range(0, len(obj)):
            status = obj[i]
            for j in range(0, 8):
                r[i * 8 + j + 1] = (((status >> j) & 0x01) == 0x01)

        return r


# noinspection PyUnresolvedReferences,PyUnresolvedReferences,PyUnresolvedReferences
class PartitionStatus(Subconstruct):
    first2 = BitStruct(
        'fire_alarm' / Flag,
        'audible_alarm' / Flag,
        'silent_alarm' / Flag,
        'was_in_alarm' / Flag,  # is in alarm
        'arm_no_entry' / Flag,
        'arm_stay' / Flag,  # Armed in Stay mode
        'arm_away' / Flag,  # Armed in Away mode
        'arm' / Flag,  # Armed

        'lockout' / Flag,
        'programming' / Flag,
        'zone_bypassed' / Flag,
        'alarm_in_memory' / Flag,
        'trouble' / Flag,
        'entry_delay' / Flag,
        'exit_delay' / Flag,
        'ready' / Flag
    )

    last4 = BitStruct(
        'zone_supervision_trouble' / Flag,
        'zone_fire_loop_trouble' / Flag,
        'zone_low_battery_trouble' / Flag,
        'zone_tamper_trouble' / Flag,
        'voice_arming' / Flag,
        'auto_arming_engaged' / Flag,
        'fire_delay_in_progress' / Flag,
        'intellizone_engage' / Flag,

        'time_to_refresh_zone_status' / Flag,
        'panic_alarm' / Flag,
        'police_code_delay' / Flag,  # Within police code delay
        'follow_become_delay' / Flag,  # Follow become delay when is bypassed
        'remote_arming' / Flag,
        'stay_arming_auto' / Flag,  # if no entry zone is tripped
        'partition_recently_close' / Flag,
        'cancel_alarm_reporting_on_disarming' / Flag,

        'tx_delay_finished' / Flag,  # (Time Out / instant alarm)
        'auto_arm_reach' / Flag,
        'fire_delay_end' / Flag,
        'no_movement_delay_end' / Flag,
        'alarm_duration_finished' / Flag,
        'entry_delay_finished' / Flag,
        'exit_delay_finished' / Flag,
        'intellizone_delay_finished' / Flag,

        '_free0' / BitsInteger(3),
        'all_zone_closed' / Flag,  # (Bypass or not)
        'inhibit_ready' / Flag,
        'bypass_ready' / Flag,
        'force_ready' / Flag,
        'stay_instant_ready' / Flag,
    )

    def __init__(self, subcons_or_size):
        if isinstance(subcons_or_size, Construct):
            self.size = subcons_or_size.sizeof()
            subcons = subcons_or_size
        else:
            self.size = subcons_or_size
            subcons = Bytes(subcons_or_size)
        super(PartitionStatus, self).__init__(subcons)

    def _parse(self, stream, context, path):
        obj = Container()

        if self.size == 32:
            for i in range(1, 6):
                obj[i] = self.first2._parsereport(stream, context, path)
                obj[i].update(self.last4._parsereport(stream, context, path))

            obj[6] = self.first2._parsereport(stream, context, path)
        elif self.size == 16:
            obj[6] = self.last4._parsereport(stream, context, path)
            for i in range(7, 9):
                obj[i] = self.first2._parsereport(stream, context, path)
                obj[i].update(self.last4._parsereport(stream, context, path))
        else:
            raise Exception('Not supported size. Only 32 or 16')

        return obj


class PGMFlags(Subconstruct):
    parser = BitStruct(
        'chime_zone_partition' / StatusFlagArrayAdapter(Array(4, Flag)),
        'power_smoke' / Flag,
        'ground_start' / Flag,
        'kiss_off' / Flag,
        'line_ring' / Flag,

        'bell_partition' / StatusFlagArrayAdapter(Array(8, Flag)),

        'fire_alarm' / StatusFlagArrayAdapter(Array(8, Flag)),

        'open_close_kiss_off' / StatusFlagArrayAdapter(Array(8, Flag))
    )

    def __init__(self):
        super(PGMFlags, self).__init__(self.parser)

class EventAdapter(Adapter):
    def _decode(self, obj, context, path):
        event_group = obj[0]
        event_1_high_nibble = obj[1] >> 6
        event_2_high_nibble = (obj[1] >> 4) & 0b11
        event_1 = obj[2] + (event_1_high_nibble << 8)
        event_2 = obj[3] + (event_2_high_nibble << 8)
        partition = obj[1] & 0x0f

        return Container({
            'major': event_group,
            'minor': event_1,
            'minor2': event_2,
            'partition': partition
        })

# class CompressedEventAdapter(Adapter):
#     def _decode(self, obj, context, path):
#         day = obj[0] >> 3
#         month = (obj[0] & 0b111) << 1 | obj[1] >> 7
#         century = obj[1] & 0b1111111
#         year = century * 100 + (obj[2] >> 1)
#         hour = (obj[2] & 0b1) << 4 | obj[3] >> 4
#         minute = (obj[3] & 0b1111) << 2 | obj[4] >> 6
#
#         Container({
#             'time': datetime.datetime(year, month, day, hour, minute)
#         })
#
#     def _encode(self, obj, context, path):
#         return [obj.year / 100, obj.year % 100, obj.month, obj.day, obj.hour, obj.minute, obj.second]