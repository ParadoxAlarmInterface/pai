from enum import Enum
from copy import copy


class EventLevel(Enum):
    NOTSET = 0
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    CRITICAL = 50


class Event:

    def __init__(self, eventMap, event=None, names=None):
        self.level = EventLevel.NOTSET
        self.timestamp = 0
        self.eventMap = eventMap
        self.data = {}
        if event is not None:
            self.parse(event, names)

    def __repr__(self):
        return str(self.data)

    def parse(self, event, names):
        if event.fields.value.po.command != 0x0e:
            raise(Exception("Invalid Event"))

        self.raw = copy(event.fields.value)
        self.timestamp = self.raw.time
        self.partition = self.raw.partition
        self.module = self.raw.module_serial
        self.label_type = self.raw.label_type
        self.label = self.raw.label

        self.major = self.raw.event[0]
        self.minor = self.raw.event[1]

        if self.major in self.eventMap:
            self.data = self.parseMap(self.major, self.minor, names)

    def parseMap(self, major, minor, names):
        event = self.eventMap[major]
        event['message'] = event.get('message', '')

        if names is not None and 'type' in event and event['type'] in names and \
                minor in names[event['type']]:
            event['label'] = names[event['type']][minor]

        if '{}' in event['message']:
            event['message'] = event['message'].format(event['label'])

        if 'sub' in event and minor in event['sub']:
            sub = event['sub'][minor]
            for k in sub:
                if k == 'message':
                    event[k] = '{} {}'.format(event[k], sub[k])
                elif isinstance(sub[k], list):
                    event[k] = event.get(k, []).extend(sub[k])
                else:
                    event[k] = sub[k]
            del event['sub']

    def level(self):
        return self.level
