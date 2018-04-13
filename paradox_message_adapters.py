from construct import Adapter
import datetime

class DateAdapter(Adapter):
    def _decode(self, obj, context, path):
        return datetime.datetime(obj[0]*100+obj[1], obj[2], obj[3], obj[4], obj[5])


    def _encode(self, obj, context, path):
        return [obj.year / 100, obj.year % 100, obj.month, obj.day, obj.hour, obj.minute]


class ModuleSerialAdapter(Adapter):
    def _decode(self, obj, context, path):
      return hex(int(obj[0]) * 10^8 + int(obj[1]) * 10^4 + int(obj[2]) * 10^2 + int(
                obj[3]) * 10^0)

class PartitionStateAdapter(Adapter):
    states = dict(arm=4, disarm=5, arm_sleep=3, arm_stay=1, none=0)

    def _decode(self, obj, context, path):

        for k,v in enumerate(self.states):
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

        for k,v in enumerate(self.states):
          if v == obj[0]:
            return k

        return "unknown"

    def _encode(self, obj, context, path):
      if obj in self.states:
        return self.states[obj]

      return 0


class ZoneOpenStatusAdapter(Adapter):

    def _decode(self, obj, context, path):
        zone_status = dict()
        for i in range(0, 4):
          status = obj[i]
          for j in range(0, 8):
              zone_status[i * 8 + j + 1]=dict(open=((status >> j) & 0x01) == 0x01) 
        
        return zone_status

class PartitionStatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        partition_status=dict()
        for i in range(0, 2):
            partition = dict(
              arm=obj[i * 4] & 0x01 != 0,
              arm_sleep=obj[i * 4] & 0x02 != 0,
              arm_stay=obj[i * 4] & 0x04 != 0,
              arm_full=(obj[i * 4] & 0x01 != 0) and obj[i * 4] & 0x06 ==0,
              arm_noentry=obj[i * 4] & 0x08 != 0,
              alarm=obj[i * 4] & 0x10 != 0,
              alarm_silent=obj[i * 4] & 0x20 != 0,
              alarm_audible=obj[i * 4] & 0x40 != 0,
              alarm_fire=obj[i * 4] & 0x80 != 0,
              
              exit_delay=obj[i * 4 + 1] & 0x01 != 0,
              entry_delay=obj[i * 4 + 1] & 0x02 != 0,
              #ready_to_arm=obj[i * 4 + 1] & 0x01 != 0,
              #ready_to_arm=obj[i * 4 + 1] & 0x01 != 0,
              trouble=obj[i * 4 + 1] & 0x08 != 0,
              alarm_memory=obj[i * 4 + 1] & 0x10 != 0,
              zone_bypass=obj[i * 4 + 1] & 0x20 != 0,
              programming=obj[i * 4 + 1] & 0x40 != 0,
              lockout=obj[i * 4 + 1] & 0x80 != 0,
              
              intelizone_engage=obj[i * 4 + 2] & 0x01 != 0,
              fire_delay=obj[i * 4 + 2] & 0x02 != 0,
              auto_arming=obj[i * 4 + 2] & 0x04 != 0,
              voice_arming=obj[i * 4 + 2] & 0x08 != 0,
              zone_tamper_trouble=obj[i * 4 + 2] & 0x10 != 0,
              zone_low_battery_trouble=obj[i * 4 + 2] & 0x20 != 0,
              zone_fire_loop_trouble=obj[i * 4 + 2] & 0x40 != 0,
              zone_supervision_trouble=obj[i * 4 + 2] & 0x80 != 0,
              )
              
            partition_status[i + 1] = partition
        
        return partition_status

class ZoneStatusAdapter(Adapter):
    def _decode(self, obj, context, path):
        zone_status = dict()
        for i in range(0, 32):
            zone_status[i+1] = dict(
              supervision_trouble=obj[i] & 0x01 != 0,
              tx_delay=obj[i] & 0x02 != 0,
              shutdown=obj[i] & 0x04 != 0,
              bypass=obj[i] & 0x08 != 0,
              intellizone_delay=obj[i] & 0x0f != 0,
              entry_delay=obj[i] & 0x20 != 0,
              in_alarm=obj[i] & 0x40 != 0,
              generated_alarm=obj[i] & 0x40 != 0)

        return zone_status

eventGroupMap = {0: 'Zone OK',
                 1: 'Zone open',
                 2: 'Partition status',
                 3: 'Bell status (Partition 1)',
                 # 5: 'Non-Reportable Event',
                 6: 'Non-reportable event',
                 # 7: 'PGM Activation',
                 8: 'Button B pressed on remote',
                 9: 'Button C pressed on remote',
                 10: 'Button D pressed on remote',
                 11: 'Button E pressed on remote',
                 12: 'Cold start wireless zone',
                 13: 'Cold start wireless module (Partition 1)',
                 14: 'Bypass programming',
                 15: 'User code activated output (Partition 1)',
                 16: 'Wireless smoke maintenance signal',
                 17: 'Delay zone alarm transmission',
                 18: 'Zone signal strength weak 1 (Partition 1)',
                 19: 'Zone signal strength weak 2 (Partition 1)',
                 20: 'Zone signal strength weak 3 (Partition 1)',
                 21: 'Zone signal strength weak 4 (Partition 1)',
                 22: 'Button 5 pressed on remote',
                 23: 'Button 6 pressed on remote',
                 24: 'Fire delay started',
                 # 25: 'N/A',
                 26: 'Software access',
                 27: 'Bus module event',
                 28: 'StayD pass acknowledged',
                 29: 'Arming with user',
                 30: 'Special arming',
                 31: 'Disarming with user',
                 32: 'Disarming after alarm with user',
                 33: 'Alarm cancelled with user',
                 34: 'Special disarming',
                 35: 'Zone bypassed',
                 36: 'Zone in alarm',
                 37: 'Fire alarm',
                 38: 'Zone alarm restore',
                 39: 'Fire alarm restore',
                 40: 'Special alarm',
                 41: 'Zone shutdown',
                 42: 'Zone tampered',
                 43: 'Zone tamper restore',
                 44: 'New trouble (Partition 1, both for sub event 7',
                 45: 'Trouble restored ',
                 46: 'Bus / EBus / Wireless module new trouble (Partition 1)',
                 47: 'Bus / EBus / Wireless module trouble restored (Partition 1)',
                 48: 'Special (Partition 1)',
                 49: 'Low battery on zone',
                 50: 'Low battery on zone restore',
                 51: 'Zone supervision trouble',
                 52: 'Zone supervision restore',
                 53: 'Wireless module supervision trouble (Partition 1)',
                 54: 'Wireless module supervision restore (Partition 1)',
                 55: 'Wireless module tamper trouble (Partition 1)',
                 56: 'Wireless module tamper restore (Partition 1)',
                 57: 'Non-medical alarm (paramedic)',
                 58: 'Zone forced',
                 59: 'Zone included',
                 64: 'System Status'
                 }

_partitionStatus = {-1: 'Partition',
                    0: 'N/A',
                    1: 'N/A',
                    2: 'Silent alarm',
                    3: 'Buzzer alarm',
                    4: 'Steady alarm',
                    5: 'Pulse alarm',
                    6: 'Strobe',
                    7: 'Alarm stopped',
                    8: 'Squawk ON (Partition 1)',
                    9: 'Squawk OFF (Partition 1)',
                    10: 'Ground Start (Partition 1)',
                    11: 'Disarm partition',
                    12: 'Arm partition',
                    13: 'Entry delay started',
                    14: 'Exit delay started',
                    15: 'Pre-alarm delay',
                    16: 'Report confirmation',
                    99: 'Any partition status event'
                    }

_bellStatus = {-1: 'Bell',
               0: ' Bell OFF',
               1: ' Bell ON',
               2: ' Bell squawk arm',
               3: ' Bell squawk disarm',
               99: 'Any bell status event'}


_nonReportableEvents = {-1: 'NonReportable',
                        0: 'Telephone line trouble',
                        1: '[ENTER]/[CLEAR]/[POWER] key was pressed (Partition 1 only)',
                        2: 'N/A',
                        3: 'Arm in stay mode',
                        4: 'Arm in sleep mode',
                        5: 'Arm in force mode',
                        6: 'Full arm when armed in stay mode',
                        7: 'PC fail to communicate (Partition 1)',
                        8: 'Utility Key 1 pressed (keys [1] and [2]) (Partition 1)',
                        9: 'Utility Key 2 pressed (keys [4] and [5]) (Partition 1)',
                        10: 'Utility Key 3 pressed (keys [7] and [8]) (Partition 1)',
                        11: 'Utility Key 4 pressed (keys [2] and [3]) (Partition 1)',
                        12: 'Utility Key 5 pressed (keys [5] and [6]) (Partition 1)',
                        13: 'Utility Key 6 pressed (keys [8] and [9]) (Partition 1)',
                        14: 'Tamper generated alarm',
                        15: 'Supervision loss generated alarm',
                        16: 'N/A',
                        17: 'N/Ad',
                        18: 'N/A',
                        19: 'N/A',
                        20: 'Full arm when armed in sleep mode',
                        21: 'Firmware upgrade -Partition 1 only (non-PGM event)',
                        22: 'N/A',
                        23: 'StayD mode activated',
                        24: 'StayD mode deactivated',
                        25: 'IP Registration status change',
                        26: 'GPRS Registration status change',
                        99: 'Any non-reportable event'}

_userLabel = {-1: 'User',
               1: 'User Number 1',
               2: 'User Number 2',
               3: 'User Number 3',
               4: 'User Number 4',
               5: 'User Number 5',
               6: 'User Number 6',
               7: 'User Number 7',
               8: 'User Number 8',
               9: 'User Number 9',
               10: 'User Number 10',
               11: 'User Number 11',
               12: 'User Number 12',
               13: 'User Number 13',
               14: 'User Number 14',
               15: 'User Number 15',
               16: 'User Number 16',
               17: 'User Number 17',
               18: 'User Number 18',
               19: 'User Number 19',
               20: 'User Number 20',
               21: 'User Number 21',
               22: 'User Number 22',
               23: 'User Number 23',
               24: 'User Number 24',
               25: 'User Number 25',
               26: 'User Number 26',
               27: 'User Number 27',
               28: 'User Number 28',
               29: 'User Number 29',
               30: 'User Number 30',
               31: 'User Number 31',
               32: 'User Number 32'
               }

_remoteLabel = {-1: 'Remote',
                 1: 'Remote control number 1',
                 2: 'Remote control number 2',
                 3: 'Remote control number 3',
                 4: 'Remote control number 4',
                 5: 'Remote control number 5',
                 6: 'Remote control number 6',
                 7: 'Remote control number 7',
                 8: 'Remote control number 8',
                 9: 'Remote control number 9',
                 10: 'Remote control number 10',
                 11: 'Remote control number 11',
                 12: 'Remote control number 12',
                 13: 'Remote control number 13',
                 14: 'Remote control number 14',
                 15: 'Remote control number 15',
                 16: 'Remote control number 16',
                 17: 'Remote control number 17',
                 18: 'Remote control number 18',
                 19: 'Remote control number 19',
                 20: 'Remote control number 20',
                 21: 'Remote control number 21',
                 22: 'Remote control number 22',
                 23: 'Remote control number 23',
                 24: 'Remote control number 24',
                 25: 'Remote control number 25',
                 26: 'Remote control number 26',
                 27: 'Remote control number 27',
                 28: 'Remote control number 28',
                 29: 'Remote control number 29',
                 30: 'Remote control number 30',
                 31: 'Remote control number 31',
                 32: 'Remote control number 32',
                 99: 'Any remote control number'
                 }

_specialArming = {-1: 'Special',
                  0: 'Auto-arming (on time/no movement)',
                  1: 'Late to close',
                  2: 'No movement arming',
                  3: 'Partial arming',
                  4: 'Quick arming',
                  5: 'Arming through WinLoad',
                  6: 'Arming with keyswitch',
                  99: 'Any special arming'
                  }

_specialDisarming = {-1: 'Special',
                     0: 'Auto-arm cancelled (on time/no movement)',
                     1: 'Disarming through WinLoad',
                     2: 'Disarming through WinLoad after alarm',
                     3: 'Alarm cancelled through WinLoad',
                     4: 'Paramedical alarm cancelled',
                     5: 'Disarm with keyswitch',
                     6: 'Disarm with keyswitch after an alarm',
                     7: 'Alarm cancelled with keyswitch',
                     99: 'Any special disarming'
                     }

_specialAlarm = {
                -1: 'Special',
                 0: 'Panic non-medical emergency',
                 1: 'Panic medical',
                 2: 'Panic fire',
                 3: 'Recent closing',
                 4: 'Global shutdown',
                 5: 'Duress alarm',
                 6: 'Keypad lockout (Partition 1)',
                 99: 'Any special alarm event'
                 }

_newTrouble = {-1: 'Trouble',
               0: 'N/A',
               1: 'AC failure',
               2: 'Battery failure',
               3: 'Auxiliary current overload',
               4: 'Bell current overload',
               5: 'Bell disconnected',
               6: 'Clock loss',
               7: 'Fire loop trouble',
               8: 'Fail to communicate to monitoring station telephone #1',
               9:  'Fail to communicate to monitoring station telephone #2',
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
               99: 'Any new trouble event'
               }

_troubleRestored = {-1: 'Trouble',
                    0: 'Telephone line restore',
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

_softwareAccess = {-1: 'Software',
                   0: 'Non-valid source ID',
                   1: 'WinLoad direct',
                   2: 'WinLoad through IP module',
                   3: 'WinLoad through GSM module',
                   4: 'WinLoad through modem',
                   9: 'IP100 direct',
                   10: 'VDMP3 direct',
                   11: 'Voice through GSM module',
                   12: 'Remote access',
                   13: 'SMS through GSM module',
                   99: 'Any software access'
                   }

_outputLabel = {
              -1: 'Output',
              1: 'PGM Number 1',
              2: 'PGM Number 2',
              3: 'PGM Number 3',
              4: 'PGM Number 4',
              5: 'PGM Number 5',
              6: 'PGM Number 6',
              7: 'PGM Number 7',
              8: 'PGM Number 8',
              9: 'PGM Number 9',
              10: 'PGM Number 10',
              11: 'PGM Number 11',
              12: 'PGM Number 12',
              13: 'PGM Number 13',
              14: 'PGM Number 14',
              15: 'PGM Number 15',
              16: 'PGM Number 16'
              }

_wirelessRepeater = {-1: 'Wireless',
                     1: 'Wireless repeater 1',
                     2: 'Wireless repeater 2'}

_wirelessKeypad = {-1: 'Wireless',
                   1: 'Wireless keypad 1',
                   2: 'Wireless keypad 2',
                   3: 'Wireless keypad 3',
                   4: 'Wireless keypad 4',
                   5: 'Wireless keypad 5',
                   6: 'Wireless keypad 6',
                   7: 'Wireless keypad 7',
                   8: 'Wireless keypad 8'
                   }

_wirelessSiren = {-1: 'Wireless',
                  1: 'Wireless siren 1',
                  2: 'Wireless siren 2',
                  3: 'Wireless siren 3',
                  4: 'Wireless siren 4'}

_busModuleEvent = {-1: 'Bus Module',
                   0: 'A bus module was added',
                   1: 'A bus module was removed',
                   2: '2-way RF Module Communication Failure',
                   3: '2-way RF Module Communication Restored'
                   }

_moduleTrouble = {-1: 'Bus Module',
                  0: 'Bus / EBus / Wireless module communication fault',
                  1: 'Tamper trouble',
                  2: 'Power fail',
                  3: 'Battery failure',
                  99: 'Any bus module new trouble event'
                  }

_moduleTroubleRestore = {1: 'Bus Module',
                         0: 'Bus / EBus / Wireless module communication fault restore',
                         1: 'Tamper trouble restore',
                         2: 'Power fail restore',
                         3: 'Battery failure restore',
                         99: 'Any bus module trouble restored event'
                         }

_special = {-1: 'Special', 
            0: 'System power up',
            1: 'Reporting test',
            2: 'Software log on',
            3: 'Software log off',
            4: 'Installer in programming mode',
            5: 'Installer exited programming mode',
            6: 'Maintenance in programming mode',
            7: 'Maintenance exited programming mode',
            8: 'Closing delinquency delay elapsed',
            99: 'Any special event'
            }

_systemStatus = {-1: 'System', 
                 0: 'Follow Arm LED status',
                 1: 'PGM pulse fast in alarm',
                 2: 'PGM pulse fast in exit delay below 10 sec.',
                 3: 'PGM pulse slow in exit delay over 10 sec.',
                 4: 'PGM steady ON if armed',
                 5: 'PGM OFF if disarmed',
                 }

_zoneLabel = {-1:  'Zone',
               1: 'Zone 1',
               2: 'Zone 2',
               3: 'Zone 3',
               4: 'Zone 4',
               5: 'Zone 5',
               6: 'Zone 6',
               7: 'Zone 7',
               8: 'Zone 8',
               9: 'Zone 9',
               10: 'Zone 10',
               11: 'Zone 11',
               12: 'Zone 12',
               13: 'Zone 13',
               14: 'Zone 14',
               15: 'Zone 15',
               16: 'Zone 16',
               17: 'Zone 17',
               18: 'Zone 18',
               19: 'Zone 19',
               20: 'Zone 20',
               21: 'Zone 21',
               22: 'Zone 22',
               23: 'Zone 23',
               24: 'Zone 24',
               25: 'Zone 25',
               26: 'Zone 26',
               27: 'Zone 27',
               28: 'Zone 28',
               29: 'Zone 29',
               30: 'Zone 30',
               31: 'Zone 31',
               32: 'Zone 32',
               99: 'Any zone'}


_eventOpt1 = {1: _outputLabel[1],
              2: _outputLabel[2],
              3: _outputLabel[3],
              4: _outputLabel[4],
              5: _outputLabel[5],
              6: _outputLabel[6],
              7: _outputLabel[7],
              8: _outputLabel[8],
              9: _outputLabel[9],
              10: _outputLabel[10],
              11: _outputLabel[11],
              12: _outputLabel[12],
              13: _outputLabel[13],
              14: _outputLabel[14],
              15: _outputLabel[15],
              16: _outputLabel[16],
              17: _wirelessRepeater[1],
              18: _wirelessRepeater[2],
              19: _wirelessKeypad[1],
              20: _wirelessKeypad[2],
              21: _wirelessKeypad[3],
              22: _wirelessKeypad[4],
              27: _wirelessSiren[1],
              28: _wirelessSiren[2],
              29: _wirelessSiren[3],
              30: _wirelessSiren[4],
              99: 'Any output number'
              }

'''dictionary consisting of dictionary'''
subEventGroupMap = {0: _zoneLabel,
                    1: _zoneLabel,
                    2: _partitionStatus,
                    3: _bellStatus,
                    6: _nonReportableEvents,
                    8: _remoteLabel,
                    9: _remoteLabel,
                    10: _remoteLabel,
                    11: _remoteLabel,
                    12: _zoneLabel,
                    13: _eventOpt1,
                    14: _zoneLabel,
                    15: _zoneLabel,
                    16: _zoneLabel,
                    17: _zoneLabel,
                    18: _zoneLabel,
                    19: _zoneLabel,
                    20: _zoneLabel,
                    21: _zoneLabel,
                    22: _remoteLabel,
                    23: _remoteLabel,
                    24: _zoneLabel,
                    # 25 :_zoneLabel,
                    26: _softwareAccess,
                    27: _busModuleEvent,
                    28: _zoneLabel,
                    29: _userLabel,
                    30: _specialArming,
                    31: _userLabel,
                    32: _userLabel,
                    33: _userLabel,
                    34: _specialDisarming,
                    35: _zoneLabel,
                    36: _zoneLabel,
                    37: _zoneLabel,
                    38: _zoneLabel,
                    39: _zoneLabel,
                    40: _specialAlarm,
                    41: _zoneLabel,
                    42: _zoneLabel,
                    43: _zoneLabel,
                    44: _newTrouble,
                    45: _troubleRestored,
                    46: _moduleTrouble,
                    47: _moduleTroubleRestore,
                    48: _special,
                    49: _zoneLabel,
                    50: _zoneLabel,
                    51: _zoneLabel,
                    52: _zoneLabel,
                    53: _eventOpt1,
                    54: _eventOpt1,
                    55: _eventOpt1,
                    56: _eventOpt1,
                    57: _userLabel,
                    58: _zoneLabel,
                    59: _zoneLabel,
                    64: _systemStatus
                    }

partitionLabel = {1: 'Partition 1',
                    2: 'Partition 2'
                    }

busModuleLabel = {1: 'Bus Module 1',
                    2: 'Bus Module 2',
                    3: 'Bus Module 3',
                    4: 'Bus Module 4',
                    5: 'Bus Module 5',
                    6: 'Bus Module 6',
                    7: 'Bus Module 7',
                    8: 'Bus Module 8',
                    9: 'Bus Module 9',
                    10: 'Bus Module 10',
                    11: 'Bus Module 11',
                    12: 'Bus Module 12',
                    13: 'Bus Module 13',
                    14: 'Bus Module 14',
                    15: 'Bus Module 15'
                    }

siteNameLabel = {1: 'Site Name'}

'''mapping of Label Types'''
labelTypeMap = {0: 'Zone Label',
                1: 'User Label',
                2: 'Partition Label',
                3: 'PGM Label',
                4: 'Bus Module Label',
                5: 'Wireless Repeater Label',
                6: 'Wireless Keypad Label'}


class EventAdapter(Adapter):
    def _decode(self, obj, context, path):      
      return {'major': (obj[0], eventGroupMap[obj[0]]), 
                'minor': (obj[1], subEventGroupMap[obj[0]][obj[1]]), 
                'type': subEventGroupMap[obj[0]][-1]}

