import string
import typing
from copy import copy
from enum import Enum
import datetime

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

    def __init__(self, event_map, event=None, label_provider=None):
        self.timestamp = 0
        self._event_map = event_map

        # default
        self.level = EventLevel.NOTSET
        self.tags = []
        self.type = 'system'
        self.id = None  # Element ID (if available in the event)
        self._message_tpl = ''
        self.change = {}
        self.additional_data = {}
        self.partition = None
        assert isinstance(label_provider, typing.Callable)
        self.label_provider = label_provider

        if event is not None:
            self.parse(event)

    def __repr__(self):
        vars = {}
        vars.update(self.__dict__)
        vars['message'] = self.message

        return str(self.__class__) + '\n' + '\n'.join(
            ('{} = {}'.format(item, vars[item]) for item in vars if not item.startswith('_')))

    def parse(self, event):
        if event.fields.value.po.command != 0x0e:
            raise(Exception("Invalid Event"))

        self.raw = copy(event.fields.value)  # Event raw data
        self.timestamp = self.raw.time  # Event timestamp
        self.partition = self.raw.partition  # Event Partition. if Type is system, partition may not be relevant
        self.module = self.raw.module_serial  # Event Module Serial
        self.label_type = self.raw.get('label_type', None)  # Type of element triggering the event
        self.label = self.raw.label.strip(b'\0 ').decode('utf-8')  # Event Element Label. May be overwride localy
        self.major = self.raw.event.major  # Event major code
        self.minor = self.raw.event.minor  # Event minor code

        self._parse_map()

    def _parse_map(self):
        if self.major not in self._event_map:
            raise(Exception("Unknown event major: {}".format(self.raw)))

        event_map = copy(self._event_map[self.major])  # for inplace modifications

        # If 'sub' key is present, minor code will be used to obtain detailed information
        if 'sub' in event_map:
            if self.minor in event_map['sub']:
                sub = event_map['sub'][self.minor]
                if isinstance(sub, str):
                    sub = dict(message=sub)

                for k in sub:
                    if k == 'message':
                        event_map[k] = '{}: {}'.format(event_map[k], sub[k]) if k in event_map else sub[k]
                    elif isinstance(sub[k], typing.List):  # for tags or other lists
                        event_map[k] = event_map.get(k, []).extend(sub[k])
                    else:
                        event_map[k] = sub[k]
                del event_map['sub']
        # If key is not present, minor code contains the element ID
        else:
            self.id = self.minor

        callables = (k for k in event_map if isinstance(event_map[k], typing.Callable))
        for k in callables:
            event_map[k] = event_map[k](self, self.label_provider)

        self.level = event_map.get('level', self.level)
        self.type = event_map.get('type', self.type)
        self._message_tpl = event_map.get('message', self._message_tpl)
        self.change = event_map.get('change', self.change)
        self.tags = event_map.get('tags', [])

        self.additional_data = {k: v for k, v in event_map.items() if k not in ['message'] and not hasattr(self, k)}

        # Set partition label
        if self.type == 'partition':
            self.label = self.label_provider(self.type, self.partition)
            self.id = self.partition

    @property
    def message(self):
        return Formatter().format(self._message_tpl, self)

    @property
    def name(self):
        key = self.partition if self.type == 'partition' else self.minor

        name = self.label_provider(self.type, key)
        if name:
            return name

        return '-'

    @property
    def props(self):
        dp = {}
        for key in dir(self):
            if key in ['props', 'raw']:
                continue

            value = getattr(self, key)
            if not key.startswith('_') and not isinstance(value, typing.Callable):
                if isinstance(value, datetime.datetime):
                    dp[key] = str(value.isoformat())
                elif isinstance(value, Enum):
                    dp[key] = value.name
                else:
                    dp[key] = value
        return dp
