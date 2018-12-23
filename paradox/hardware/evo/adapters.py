# -*- coding: utf-8 -*-

import datetime
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


class ZoneFlags(Subconstruct):
    flag_parser = BitStruct(
        "supervision_trouble" / Flag,
        "tx_delay" / Flag,
        "shutted_down" / Flag,
        "bypassed" / Flag,
        "activated_intellizone_delay" / Flag,
        "activated_entry_delay" / Flag,
        "presently_in_alarm" / Flag,
        "generated_alarm" / Flag
    )

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
        'zone_bypass' / Flag,
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


eventGroupMap = {0: 'Zone OK',
                 1: 'Zone open',
                 2: 'Zone is tampered',
                 3: 'Zone is in fire loop trouble',
                 4: 'Non-reportable event',
                 5: 'User code entered on keypad',
                 6: 'User/card access on door',
                 7: 'Bypass programming access',
                 8: 'TX delay zone alarm',
                 9: 'Arming with master',
                 10: 'Arming with user code',
                 11: 'Arming with keyswitch',
                 12: 'Special arming',
                 13: 'Disarm with master',
                 14: 'Disarm with user code',
                 15: 'Disarm with keyswitch',
                 16: 'Disarm after alarm with master',
                 17: 'Disarm after alarm with user code',
                 18: 'Disarm after alarm with keyswitch',
                 19: 'Alarm cancelled with master',
                 20: 'Alarm cancelled with user code',
                 21: 'Alarm cancelled with keyswitch',
                 22: 'Special disarming',
                 23: 'Zone bypassed',
                 24: 'Zone in alarm',
                 25: 'Fire alarm',
                 26: 'Zone alarm restore',
                 27: 'Fire alarm restore',
                 28: 'Early to disarm by user',
                 29: 'Late to disarm by user',
                 30: 'Special alarm',
                 31: 'Duress alarm by user',
                 32: 'Zone shutdown',
                 33: 'Zone tamper',
                 34: 'Zone tamper restore',
                 35: 'Special tamper',
                 36: 'Trouble event',
                 37: 'Trouble restore',
                 38: 'Module trouble',
                 39: 'Module trouble restore',
                 40: 'Fail to communicate on telephone number',
                 41: 'Low battery on zone',
                 42: 'Zone supervision trouble',
                 43: 'Low battery on zone restored',
                 44: 'Zone supervision trouble restored',
                 45: 'Special events',
                 46: 'Early to arm by user',
                 47: 'Late to arm by user',
                 48: 'Utility key',
                 49: 'Request for exit',
                 50: 'Access denied',
                 51: 'Door left open alarm',
                 52: 'Door forced alarm',
                 53: 'Door left open restore',
                 54: 'Door forced open restore',
                 55: 'Intellizone triggered',
                 56: 'Zone excluded on Force arming',
                 57: 'Zone went back to arm status',
                 58: 'New module assigned on combus',
                 59: 'Module manually removed from combus',
                 60: 'Non-saved event',
                 61: 'Future use',
                 62: 'Access granted to user',
                 63: 'Access denied to user',
                 64: 'Status 1',
                 65: 'Status 2',
                 66: 'Status 3',
                 67: 'Special status'
                 }

_nonReportableEvents = {-1: 'NonReportable',
                        0: 'TLM trouble',
                        1: 'Smoke detector reset',
                        2: 'Arm with no entry delay',
                        3: 'Arm in Stay mode',
                        4: 'Arm in Away mode',
                        5: 'Full arm when in Stay mode',
                        6: 'Voice module access',
                        7: 'Remote control access',  # event 2: user number
                        8: 'PC fail to communicate',
                        9: 'Midnight',
                        10: 'Neware user login',
                        11: 'Neware user logout',
                        12: 'User initiated call-up',
                        13: 'Force answer',
                        14: 'Force hangup',
                        15: 'Reset to default',
                        16: 'Auxiliary output manually activated',
                        17: 'Auxiliary output manually deactivated',
                        18: 'Voice reporting failed',
                        19: 'Fail to communicate restore',  # event 2: tel number
                        20: 'Software access (VDMP3, Ip100, Neware, WinLoad)',  # event 2: module
                        21: 'IPR512 1 registration status',
                        22: 'IPR512 2 registration status',
                        23: 'IPR512 3 registration status',
                        24: 'IPR512 4 registration status',
                        }

_userLabel = {-1: 'User'}
_userLabel.update(dict((i, 'User Number {}'.format(i)) for i in range(1, 1000)))

_specialArming = {-1: 'Special',
                  0: 'Auto arming',
                  1: 'Arming with Winload',
                  2: 'Late to close',
                  3: 'No movement arming',
                  4: 'Partial arming',
                  5: 'One-touch arming',
                  6: 'Future use',
                  7: 'Future use',
                  8: '(InTouch) voice module arming',
                  9: 'Delinquency c;psomg',
                  10: 'Future use'
                  }

_specialDisarming = {-1: 'Special',
                     0: 'Auto arm cancelled',
                     1: 'One-touch stay/instant disarm',
                     2: 'Disarming with Winload',
                     3: 'Disarmining with Winload after alarm',
                     4: 'Winload cancelled alarm',
                     5: 'Future use',
                     6: 'Future use',
                     7: 'Future use',
                     8: '(InTouch) voice module disarming',
                     9: 'Future use'
                     }

_specialAlarm = {
    -1: 'Special',
    0: 'Panic non-medical emergency',
    1: 'Panic medical',
    2: 'Panic fire',
    3: 'Recent closing',
    4: 'Police code',
    5: 'Zone shutdown',
    6: 'Future use',
    7: 'Future use',
    8: 'TLM alarm',
    9: 'Central communication failure alarm',
    10: 'Module tamper alarm',
    11: 'Missing GSM module alarm',
    12: 'GSM no service alarm',
    13: 'Missing IP module alarm',
    14: 'IP no service alarm',
    15: 'Missing voice module alarm',
}

_newTrouble = {-1: 'Trouble',
               0: 'TLM trouble',
               1: 'AC failure',
               2: 'Battery failure',
               3: 'Auxiliary current overload',
               4: 'Bell current overload',
               5: 'Bell disconnected',
               6: 'Clock loss',
               7: 'Fire loop trouble',
               8: 'Fail to communicate to monitoring station telephone #1',
               9: 'Fail to communicate to monitoring station telephone #2',
               11: 'Fail to communicate to voice report',
               12: 'RF jamming',
               13: 'GSM RF jamming',
               14: 'GSM no service',
               15: 'GSM supervision lost',
               16: 'Fail To Communicate IP Receiver 1 (GPRS)',
               17: 'Fail To Communicate IP Receiver 2 (GPRS)',
               18: 'IP Module No Service',
               19: 'IP Module Supervision Loss',
               20: 'Fail To Communicate IP Receiver 1 (IP)',
               21: 'Fail To Communicate IP Receiver 2 (IP)',
               }

_troubleRestored = {-1: 'Trouble',
                    0: 'TLM trouble restore',
                    1: 'AC failure restore',
                    2: 'Battery failure restore',
                    3: 'Auxiliary current overload restore',
                    4: 'Bell current overload restore',
                    5: 'Bell disconnected restore',
                    6: 'Clock loss restore',
                    7: 'Fire loop trouble restore',
                    8: 'Fail to communicate to monitoring station telephone #1 restore',
                    9: 'Fail to communicate to monitoring station telephone #2 restore',
                    11: 'Fail to communicate to voice report restore',
                    12: 'RF jamming restore',
                    13: 'GSM RF jamming restore',
                    14: 'GSM no service restore',
                    15: 'GSM supervision lost restore',
                    16: 'Fail To Communicate IP Receiver 1 (GPRS) restore',
                    17: 'Fail To Communicate IP Receiver 2 (GPRS) restore',
                    18: 'IP Module No Service restore',
                    19: 'IP Module Supervision Loss restore',
                    20: 'Fail To Communicate IP Receiver 1 (IP) restore',
                    21: 'Fail To Communicate IP Receiver 2 (IP) restore',
                    99: 'Any trouble event restore'
                    }

_busModuleEvent = {-1: 'Bus Module',
                   0: 'A bus module was added',
                   1: 'A bus module was removed',
                   2: '2-way RF Module Communication Failure',
                   3: '2-way RF Module Communication Restored'
                   }

_moduleTrouble = {-1: 'Bus Module',
                  0: 'Combus fault',
                  1: 'Module tamper',
                  2: 'ROM/RAM error',
                  3: 'TLM trouble',
                  4: 'Fail to communicate',
                  5: 'Printer fault',
                  6: 'AC failure',
                  7: 'Battery failure',
                  8: 'Auxiliary failure',
                  9: 'Future use',
                  # 99: 'Any bus module new trouble event'
                  }

_moduleTroubleRestore = {-1: 'Bus Module',
                         0: 'Combus fault restored',
                         1: 'Module tamper restored',
                         2: 'ROM/RAM error restored',
                         3: 'TLM trouble restored',
                         4: 'Fail to communicate restored',
                         5: 'Printer fault restored',
                         6: 'AC failure restored',
                         7: 'Battery failure restored',
                         8: 'Auxiliary failure restored',
                         9: 'Future use',
                         # 99: 'Any bus module trouble restored event'
                         }
_specialTamper = {-1: 'Special',
                  0: 'Keypad Lockout',
                  1: 'Voice lockout'
                  }

_nonSavedEvent = {-1: 'Non-saved event',
                  0: 'Remote control rejected',
                  1: 'Future use'
                  }

_specialEvent = {-1: 'Special',
                 0: 'Power-up after total power down',
                 1: 'Software reset (watchdog)',
                 2: 'Test report',
                 3: 'Listen-in request',
                 4: 'WinLoad in (connected)',
                 5: 'WinLoad out (disconnected)',
                 6: 'Installer in programming',
                 7: 'Installer out of programming',
                 8: 'Future use',
                 # 99: 'Any special event'
                 }

_status1 = {-1: 'Status 1',
            0: 'Armed',
            1: 'Force armed',
            2: 'Stay armed',
            3: 'Instant armed',
            4: 'Strobe alarm',
            5: 'Silent alarm',
            6: 'Audible alarm',
            7: 'Fire alarm'
            }
_status2 = {-1: 'Status 2',
            0: 'Ready',
            1: 'Exit delay',
            2: 'Entry delay',
            3: 'System in trouble',
            4: 'Alarm in memory',
            5: 'Zones bypassed',
            6: 'Bypass, master, installer programming',
            7: 'Keypad lockout'
            }
_status3 = {-1: 'Status 3',
            0: 'Intellizone delay engaged',
            1: 'Fire delay engaged',
            2: 'Auto arm',
            3: 'Arming with voice module (set until exit delay finishes)',
            4: 'Tamper',
            5: 'Zone low battery',
            6: 'Fire loop trouble',
            7: 'Zone supervision trouble'
            }

_specialStatus = {-1: 'Special status',
                  # 0-3: Chime in partition 1-4
                  4: 'Smoke detector power reset',
                  5: 'Ground start',
                  6: 'Kiss off',
                  7: 'Telephone ring',
                  # 8-15: Bell on partition 1-8
                  # 16-23: Pulsed alarm in partition
                  # 24-31: Open/close Kiss off in partition
                  # 32-63: Keyswitch/PGM input
                  # 64-95: Status of access door
                  96: 'Trouble in system',
                  97: 'Trouble in dialer',
                  98: 'Trouble in module',
                  99: 'Trouble in combus',
                  103: 'Time and date trouble',
                  104: 'AC failure',
                  105: 'Battery failure',
                  106: 'Auxiliary current limit',
                  107: 'Bell current limit',
                  108: 'Bell absent',
                  109: 'ROM error',
                  110: 'RAM error',
                  111: 'Future use',
                  112: 'TLM 1 trouble',
                  113: 'Fail to communicate 1',
                  114: 'Fail to communicate 2',
                  115: 'Fail to communicate 3',
                  116: 'Fail to communicate 4',
                  117: 'Fail to communicate with PC',
                  120: 'Module tamper trouble',
                  121: 'Module ROM error',
                  122: 'Module TLM error',
                  123: 'Module Failure to communicate',
                  124: 'Module printer trouble',
                  125: 'Module AC failure',
                  126: 'Module battery trouble',
                  127: 'Module auxiliary failure',
                  128: 'Missing  keypad',
                  129: 'Missing  module',
                  133: 'Global combus failure',
                  134: 'Combus overload',
                  136: 'Dialer relay',
                  }

_specialStatus.update(dict((i, 'Chime in partition {}'.format(i)) for i in range(0, 4)))
_specialStatus.update(dict((i, 'Bell on partition {}'.format(i - 7)) for i in range(8, 16)))
_specialStatus.update(dict((i, 'Pulsed alarm in partition {}'.format(i - 15)) for i in range(16, 24)))
_specialStatus.update(dict((i, 'Open/close Kiss off in partition {}'.format(i - 23)) for i in range(24, 32)))
_specialStatus.update(dict((i, 'Keyswitch/PGM input {}'.format(i - 31)) for i in range(32, 64)))
_specialStatus.update(dict((i, 'Status of access door {}'.format(i - 63)) for i in range(64, 96)))

_keyswitchLabel = {-1: 'Keyswitch'}
_keyswitchLabel.update(dict((i, 'Keyswitch {}'.format(i)) for i in range(1, 33)))

_doorLabel = {-1: 'Door'}
_doorLabel.update(dict((i, 'Door {}'.format(i)) for i in range(1, 33)))

_zoneLabel = {-1: 'Zone'}
_zoneLabel.update(dict((i, 'Zone {}'.format(i)) for i in range(1, 193)))

_utilityKey = {-1: 'Utility key'}
_utilityKey.update(dict((i, 'Utility key {}'.format(i)) for i in range(1, 256)))

_moduleBus = {-1: 'Module Bus Address'}
_moduleBus.update(dict((i, 'Module Bus Address {}'.format(i)) for i in range(1, 255)))

'''dictionary consisting of dictionary'''
subEventGroupMap = {0: _zoneLabel,  # Zone OK
                    1: _zoneLabel,  # Zone open
                    2: _zoneLabel,  # Zone is tampered
                    3: _zoneLabel,  # Zone is in fire loop trouble
                    4: _nonReportableEvents,  # Non-reportable event
                    5: _userLabel,  # User code entered on keypad
                    6: _doorLabel,  # User/card access on door
                    7: _userLabel,  # Bypass programming access
                    8: _zoneLabel,  # TX delay zone alarm
                    9: _userLabel,  # Arming with master
                    10: _userLabel,  # Arming with user code
                    11: _keyswitchLabel,  # Arming with keyswitch
                    12: _specialArming,  # Special arming
                    13: _userLabel,  # Disarm with master
                    14: _userLabel,  # Disarm with user code
                    15: _keyswitchLabel,  # Disarm with keyswitch
                    16: _userLabel,  # Disarm after alarm with master
                    17: _userLabel,  # Disarm after alarm with user code
                    18: _keyswitchLabel,  # Disarm after alarm with keyswitch
                    19: _userLabel,  # Alarm cancelled with master
                    20: _userLabel,  # Alarm cancelled with user code
                    21: _keyswitchLabel,  # Alarm cancelled with keyswitch
                    22: _specialDisarming,  # Special disarming
                    23: _zoneLabel,  # Zone bypassed
                    24: _zoneLabel,  # Zone in alarm
                    25: _zoneLabel,  # Fire alarm
                    26: _zoneLabel,  # Zone alarm restore
                    27: _zoneLabel,  # Fire alarm restore
                    28: _userLabel,  # Early to disarm by user
                    29: _userLabel,  # Late to disarm by user
                    30: _specialAlarm,  # Special alarm
                    31: _userLabel,  # Duress alarm by user
                    32: _zoneLabel,  # Zone shutdown
                    33: _zoneLabel,  # Zone tamper
                    34: _zoneLabel,  # Zone tamper restore
                    35: _specialTamper,  # Special tamper
                    36: _newTrouble,  # Trouble event
                    37: _troubleRestored,  # Trouble restore
                    38: _moduleTrouble,  # Module trouble
                    39: _moduleTroubleRestore,  # Module trouble restore
                    # 40: 'Fail to communicate on telephone number',
                    41: _zoneLabel,  # Low battery on zone
                    42: _zoneLabel,  # Zone supervision trouble
                    43: _zoneLabel,  # Low battery on zone restored
                    44: _zoneLabel,  # Zone supervision trouble restored
                    45: _specialEvent,  # Special events
                    46: _userLabel,  # Early to arm by user
                    47: _userLabel,  # Late to arm by user
                    48: _utilityKey,  # Utility key
                    49: _doorLabel,  # Request for exit
                    50: _doorLabel,  # Access denied
                    51: _doorLabel,  # Door left open alarm
                    52: _doorLabel,  # Door forced alarm
                    53: _doorLabel,  # Door left open restore
                    54: _doorLabel,  # Door forced open restore
                    55: _zoneLabel,  # Intellizone triggered
                    56: _zoneLabel,  # Zone excluded on Force arming
                    57: _zoneLabel,  # Zone went back to arm status
                    58: _moduleBus,  # New module assigned on combus
                    59: _moduleBus,  # Module manually removed from combus
                    60: _nonSavedEvent,  # Non-saved event
                    # 61: 'Future use',
                    62: _userLabel,  # Access granted to user
                    63: _userLabel,  # Access denied to user
                    64: _status1,  # Status 1
                    65: _status2,  # Status 2
                    66: _status3,  # Status 3
                    67: _specialStatus  # Special status
                    }

'''mapping of Label Types'''
labelTypeMap = {0: 'No label',
                1: 'User label',
                2: 'Zone label',
                3: 'Door label',
                4: 'Area label',
                5: 'Module label',
                6: 'Future'}


class EventAdapter(Adapter):
    def _decode(self, obj, context, path):
        event_group = obj[0]
        event_high_nibble = obj[1] >> 4
        event_1 = obj[2] + (event_high_nibble << 8)
        event_2 = obj[3] + (event_high_nibble << 8)
        partition = obj[1] & 0x0f

        return {
            'major': (event_group, eventGroupMap[event_group]),
            'minor': (event_1, subEventGroupMap[event_group][event_1]),
            'minor2': (event_2, None),
            'type': subEventGroupMap[event_group][-1],
            'partition': partition
        }
