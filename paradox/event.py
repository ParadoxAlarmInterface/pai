import datetime
import logging
import time
import typing
from copy import copy
from enum import Enum
from collections import namedtuple

from construct import Container

from paradox.config import config as cfg
from paradox.lib.format import EventMessageFormatter

logger = logging.getLogger('PAI').getChild(__name__)

class EventLevel(Enum):
    NOTSET = logging.NOTSET
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARN
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    @staticmethod
    def from_name(level="NOTSET"):
        if isinstance(level, EventLevel):
            return level

        level = level.upper()
        if level in EventLevel.__members__:
            return EventLevel.__members__[level]

        raise (Exception("Invalid log level {}. Valid levels: {}".format(level, list(EventLevel.__members__))))

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value

        if other.__class__ is int:
            return self.value < other

        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value

        if other.__class__ is int:
            return self.value > other

        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value

        if other.__class__ is int:
            return self.value <= other

        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value

        if other.__class__ is int:
            return self.value >= other

        return NotImplemented

    def __str__(self):
        return self.name


class Change:
    def __init__(self, type: str, key: str, property: str, new_value, old_value=None, initial=None):
        self.type = type
        self.key = key
        self.property = property
        self.new_value = new_value
        self.old_value = old_value
        self.initial = initial
        if self.initial is None:
            self.initial = old_value is None
        self.timestamp = int(time.time())

    def __eq__(self, other: "Change"):
        return self.type == other.type \
            and self.key == other.key \
            and self.property == other.property \
            and self.new_value == other.new_value

    def __repr__(self):
        return "Change {}/{}/{} from {}{} to {}".format(
            self.type, self.key,
            self.property,
            self.old_value,
            ("(initial)" if self.initial else ""),
            self.new_value
        )


class Event:
    def __init__(self, label_provider=None):
        self.timestamp = 0
        self.level = EventLevel.NOTSET
        self.type = None
        self._message_tpl = ''
        self.change = {}
        self.tags = []
        self.additional_data = {}
        self.hook_fn = None

        self._key = None

        if label_provider is not None:
            self.label_provider = label_provider
        else:
            self.label_provider = lambda type, value: "[{}:{}]".format(type, value)

    def __repr__(self):
        lvars = {}
        lvars.update(self.__dict__)
        lvars['message'] = self.message

        return str(self.__class__) + '\n' + '\n'.join(
            ('{} = {}'.format(item, lvars[item]) for item in lvars if not item.startswith('_')))

    @property
    def key(self) -> str:
        if not self._key:
            self._key = "{},{},{}".format(self.type, self.label,
                                          ','.join("=".join([key, str(val)]) for key, val in self.change.items()))

        return self._key

    @property
    def message(self) -> str:
        return EventMessageFormatter().format(self._message_tpl, self)

    @property
    def props(self) -> dict:
        dp = {}
        for key in dir(self):
            if key in ['props', 'raw', 'hook_fn']:
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

    def call_hook(self, *args, **kwargs):
        if isinstance(self.hook_fn, typing.Callable):
            kwargs["event"] = self
            try:
                self.hook_fn(*args, **kwargs)
            except Exception:
                logger.exception("Failed to call event hook")


class LiveEvent(Event):
    def __init__(self, event: Container, event_map: dict, label_provider=None):
        raw = event.fields.value
        if raw.po.command != 0x0e:
            raise AssertionError("Message is not an event")

        # parse event map
        if raw.event.major not in event_map:
            raise AssertionError("Unknown event major: {}".format(raw))

        super(LiveEvent, self).__init__(label_provider=label_provider)

        self.major = raw.event.major  # Event major code
        self.minor = raw.event.minor  # Event minor code
        if hasattr(raw.event, 'minor2'):  # For EVO panels
            self.minor2 = raw.event.minor2

        # default
        self.id = None  # Element ID (if available in the event)
        self.additional_data = {}

        self.timestamp = raw.time  # Event timestamp
        self.partition = raw.partition  # Event Partition. if Type is system, partition may not be relevant
        self.module = raw.module_serial  # Event Module Serial
        self.label_type = raw.get('label_type', None)  # Type of element triggering the event
        self.label = raw.label.replace(b'\0', b' ').strip(b' ').decode(
            encoding=cfg.LABEL_ENCODING, errors='ignore')  # Event Element Label. May be overridden locally

        event_map = copy(event_map[self.major])  # for inplace modifications

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
                        event_map[k] = event_map.get(k, []) + sub[k]
                    else:
                        event_map[k] = sub[k]
            del event_map['sub']
        # If key is not present, minor code contains the element ID
        else:
            self.id = self.minor

        callables = (k for k in event_map if isinstance(event_map[k], typing.Callable) and k != 'hook_fn')
        for k in callables:
            event_map[k] = event_map[k](self, self.label_provider)

        self.level = event_map.get('level', self.level)
        self.type = event_map.get('type', self.type)
        self._message_tpl = event_map.get('message', self._message_tpl)
        self.change = event_map.get('change', self.change)

        # ## Support parsing change values as messages
        # for k in self.change:
        #     if isinstance(self.change[k], str):
        #         self.change[k] = EventMessageFormatter().format(self.change[k], self)

        self.tags = event_map.get('tags', [])
        self.hook_fn = event_map.get('hook_fn')

        self.additional_data = {k: v for k, v in event_map.items() if k not in ['message'] and not hasattr(self, k)}

        # Set partition label
        if self.type == 'partition':
            self.label = self.label_provider(self.type, self.partition)
            self.id = self.partition

    @property
    def name(self) -> str:
        key = self.partition if self.type == 'partition' else self.minor

        name = self.label_provider(self.type, key)
        if name:
            return name

        return '-'


class ChangeEvent(Event):
    def __init__(self, change_object: Change, property_map, label_provider=None):
        if change_object.property not in property_map:
            raise AssertionError('property %s not in property_map', change_object.property)

        super().__init__(label_provider=label_provider)

        self.timestamp = change_object.timestamp
        if change_object.type == 'partition':
            self.partition = change_object.key
        else:
            self.partition = ""
        self.property = change_object.property

        self.value = change_object.new_value
        self.type = change_object.type
        self.label = change_object.key
        self.change = {self.property: self.value}

        property_map = copy(property_map[self.property])  # for inplace modifications
        callables = (k for k in property_map if isinstance(property_map[k], typing.Callable))
        for k in callables:
            property_map[k] = property_map[k](self, self.label_provider)

        self.level = property_map.get('level', self.level)
        tpl = property_map.get('message', self._message_tpl)
        if isinstance(tpl, dict):
            if str(self.value) in tpl:
                self._message_tpl = tpl[str(self.value)]
        else:
            self._message_tpl = tpl

        self.tags = property_map.get('tags', [])


Notification = namedtuple('Notification', ['sender', 'message', 'level'])