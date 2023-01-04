import datetime

from construct import (
    Adapter,
    Array,
    BitsInteger,
    BitStruct,
    Bitwise,
    Bytes,
    ByteSwapped,
    Bytewise,
    Computed,
    Construct,
    Container,
    Default,
    ExprSymmetricAdapter,
    Flag,
    Int24ub,
    ListContainer,
    Struct,
    Subconstruct,
    this,
)


class DateAdapter(Adapter):
    def _decode(self, obj, context, path):
        if obj[2] == 0:
            return None

        return datetime.datetime(
            obj[0] * 100 + obj[1],
            obj[2],
            obj[3],
            obj[4],
            obj[5],
            obj[6] if len(obj) > 6 else 0,
        )

    def _encode(self, obj, context, path):
        bts = [
            obj.year // 100,
            obj.year % 100,
            obj.month,
            obj.day,
            obj.hour,
            obj.minute,
        ]

        if self.subcon.length == 7:
            bts.append(obj.second)

        return bytes(bts)


class DictArray(Adapter):
    def __init__(self, count, first_index, subcon, pick_key: str = None):
        super().__init__(Array(count, subcon))
        self._first_index = first_index
        self._pick_key = pick_key

    def _decode(self, obj, context, path):
        if not isinstance(obj, list):
            raise TypeError("list should be passed for decoding")

        n_obj = Container()
        for item in obj:
            v = item
            if self._pick_key:
                v = item.get(self._pick_key)
            n_obj[item._index] = v

        return n_obj

    def _encode(self, obj, context, path):
        if not isinstance(obj, dict):
            raise TypeError("dict should be passed for decoding")

        n_obj = ListContainer()

        count = self.subcon.count  # Array count

        for k in range(self._first_index, self._first_index + count):
            o = {"_index": k}
            v = obj.get(k)
            if v is not None:
                if self._pick_key:
                    v = {self._pick_key: v}
                o.update(v)
            n_obj.append(o)

        return n_obj


class EnumerationAdapter(Subconstruct):
    def __init__(self, subcon):
        super().__init__(subcon)

        def find_count(s):
            if hasattr(s, "count"):
                return s.count
            else:
                return find_count(s.subcon)

        self.size = find_count(subcon)

    def _build(self, obj, stream, context, path):
        zones = list(i in obj for i in range(1, self.size + 1))

        return self.subcon._build(zones, stream, context, path)


def StatusFlags(count, start_index_from=1):
    return DictArray(
        count,
        start_index_from,
        Struct(
            "_index" / Computed(this._index + start_index_from),
            "flag" / Default(Flag, False),
        ),
        pick_key="flag",
    )


def ModuleTroubles(count, start_index_from=1):
    return DictArray(
        count=count,
        first_index=start_index_from,
        subcon=BitStruct(
            "_index" / Computed(this._index + start_index_from),
            "aux_trouble" / Flag,
            "battery_fail" / Flag,
            "ac_trouble" / Flag,
            "printer_trouble" / Flag,
            "fail_to_comm" / Flag,
            "tlm_trouble" / Flag,
            "rom_error" / Flag,
            "tamper" / Flag,
        ),
    )


def ZoneFlags(count, start_index_from=1):
    return DictArray(
        count,
        start_index_from,
        BitStruct(
            "_index" / Computed(this._index + start_index_from),
            "generated_alarm" / Default(Flag, False),
            "presently_in_alarm" / Default(Flag, False),
            "activated_entry_delay" / Default(Flag, False),
            "activated_intellizone_delay" / Default(Flag, False),
            "bypassed" / Default(Flag, False),
            "shutted_down" / Default(Flag, False),
            "tx_delay" / Default(Flag, False),
            "supervision_trouble" / Default(Flag, False),
        ),
    )


def PGMFlags(count, start_index_from=1):
    return DictArray(
        count,
        start_index_from,
        Bitwise(
            Struct(
                "_index" / Computed(this._index + start_index_from),
                "fire_2_wires" / Default(Flag, False),
                "normally_closed" / Default(Flag, False),
                "_unknown1" / BitsInteger(1),
                "disabled"
                / ExprSymmetricAdapter(
                    Default(Flag, False), lambda obj, ctx: not obj
                ),  # False when a relay is assigned
                "_unknown2" / BitsInteger(2),
                "timer_active" / Default(Flag, False),  # when timer is active
                "on" / Default(Flag, False),  # when is activated
                "time_left"
                / Bytewise(ByteSwapped(Default(Int24ub, 0))),  # byte in seconds
            ),
        ),
    )


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


class PartitionStatus(Subconstruct):
    first2 = BitStruct(
        "fire_alarm" / Flag,
        "audible_alarm" / Flag,
        "silent_alarm" / Flag,
        "was_in_alarm" / Flag,  # is in alarm
        "arm_no_entry" / Flag,
        "arm_stay" / Flag,  # Armed in Stay mode
        "arm_away" / Flag,  # Armed in Away mode
        "arm" / Flag,  # Armed
        "lockout" / Flag,
        "programming" / Flag,
        "zone_bypassed" / Flag,
        "alarm_in_memory" / Flag,
        "trouble" / Flag,
        "entry_delay" / Flag,
        "exit_delay" / Flag,
        "ready" / Flag,
    )

    last4 = BitStruct(
        "zone_supervision_trouble" / Flag,
        "zone_fire_loop_trouble" / Flag,
        "zone_low_battery_trouble" / Flag,
        "zone_tamper_trouble" / Flag,
        "voice_arming" / Flag,
        "auto_arming_engaged" / Flag,
        "fire_delay_in_progress" / Flag,
        "intellizone_engage" / Flag,
        "time_to_refresh_zone_status" / Flag,
        "panic_alarm" / Flag,
        "police_code_delay" / Flag,  # Within police code delay
        "follow_become_delay" / Flag,  # Follow become delay when is bypassed
        "remote_arming" / Flag,
        "stay_arming_auto" / Flag,  # if no entry zone is tripped
        "partition_recently_close" / Flag,
        "cancel_alarm_reporting_on_disarming" / Flag,
        "tx_delay_finished" / Flag,  # (Time Out / instant alarm)
        "auto_arm_reach" / Flag,
        "fire_delay_end" / Flag,
        "no_movement_delay_end" / Flag,
        "alarm_duration_finished" / Flag,
        "entry_delay_finished" / Flag,
        "exit_delay_finished" / Flag,
        "intellizone_delay_finished" / Flag,
        "_free0" / BitsInteger(3),
        "all_zone_closed" / Flag,  # (Bypass or not)
        "inhibit_ready" / Flag,
        "bypass_ready" / Flag,
        "force_ready" / Flag,
        "stay_instant_ready" / Flag,
    )

    def __init__(self, subcons_or_size):
        if isinstance(subcons_or_size, Construct):
            self.size = subcons_or_size.sizeof()
            subcons = subcons_or_size
        else:
            self.size = subcons_or_size
            subcons = Bytes(subcons_or_size)
        super().__init__(subcons)

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
            raise Exception("Not supported size. Only 32 or 16")

        return obj


class EventAdapter(Adapter):
    def _decode(self, obj, context, path):
        event_group = obj[0]
        event_1_high_nibble = obj[1] >> 6
        event_2_high_nibble = (obj[1] >> 4) & 0b11
        event_1 = obj[2] + (event_1_high_nibble << 8)
        event_2 = obj[3] + (event_2_high_nibble << 8)
        partition = obj[1] & 0x0F

        return Container(
            {
                "major": event_group,
                "minor": event_1,
                "minor2": event_2,
                "partition": partition,
            }
        )

    def _encode(self, obj, context, path):
        return bytes(
            [
                obj.major,
                obj.partition & 0x0F
                | (obj.minor >> 8 & 3) << 6
                | (obj.minor2 >> 8 & 3) << 4,
                obj.minor & 0xFF,
                obj.minor2 & 0xFF,
            ]
        )


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
