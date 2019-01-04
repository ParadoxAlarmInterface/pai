import string
import typing
from copy import copy
from enum import Enum


class Formatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        return getattr(args[0], key)


class EventLevel(Enum):
    NOTSET = 0
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    CRITICAL = 50


class Event:

    def __init__(self, eventMap, event=None, names=None):
        self.timestamp = 0
        self.eventMap = eventMap

        # default
        self.level = EventLevel.NOTSET
        self.tags = []
        self.type = 'system'
        self.message_tpl = ''
        self.change = {}
        self.additional_data = {}

        if event is not None:
            self.parse(event, names)

    def __repr__(self):
        vars = {}
        vars.update(self.__dict__)
        vars['message']=self.message

        return str(self.__class__) + '\n' + '\n'.join(
            ('{} = {}'.format(item, vars[item]) for item in vars))

    def parse(self, event, names=None):
        if event.fields.value.po.command != 0x0e:
            raise(Exception("Invalid Event"))

        self.raw = copy(event.fields.value)
        self.timestamp = self.raw.time
        self.partition = self.raw.partition
        self.module = self.raw.module_serial
        self.label_type = self.raw.label_type
        self.label = self.raw.label.strip(b'\0 ').decode('utf-8')

        self.major = self.raw.event.major
        self.minor = self.raw.event.minor
        self.names = names or {}

        self._parseMap(names)

    def _parseMap(self, names):
        if self.major not in self.eventMap:
            return

        event_map = copy(self.eventMap[self.major])  # for inplace modifications

        if 'sub' in event_map and self.minor in event_map['sub']:
            sub = event_map['sub'][self.minor]

            for k in sub:
                if k == 'message':
                    event_map[k] = '{}: {}'.format(event_map[k], sub[k]) if event_map[k] else sub[k]
                elif isinstance(sub[k], typing.List):  # for tags or other lists
                    event_map[k] = event_map.get(k, []).extend(sub[k])
                else:
                    event_map[k] = sub[k]
            del event_map['sub']

        callables = (k for k in event_map if isinstance(event_map[k], typing.Callable))
        for k in callables:
            event_map[k] = event_map[k](self, names)

        self.level = event_map.get('level', self.level)
        self.type = event_map.get('type', self.type)
        self.message_tpl = event_map.get('message', self.message_tpl)
        self.change = event_map.get('change', self.change)
        self.tags = event_map.get('tags', [])

        self.additional_data = {k: v for k, v in event_map.items() if k not in ['message'] and not hasattr(self, k)}

    @property
    def message(self):
        return Formatter().format(self.message_tpl, self)

    @property
    def name(self):
        key = self.partition if self.type == 'partition' else self.minor

        if self.type in self.names and key in self.names[self.type]:
            return self.names[self.type][key]

        return '-'
