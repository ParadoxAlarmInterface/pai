import typing
import logging
from copy import copy
from enum import Enum
import datetime

from construct import Container
from paradox.lib.format import EventMessageFormatter

logger = logging.getLogger('PAI').getChild(__name__)

from paradox.config import config as cfg

class EventLevel(Enum):
    NOTSET = 0
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    CRITICAL = 50

class Event:
    def __init__(self):
        self.timestamp = 0
        # default
        self.level = EventLevel.NOTSET
        self.tags = []
        self.type = 'system'
        self.id = None  # Element ID (if available in the event)
        self._message_tpl = ''
        self.change = {}
        self.additional_data = {}
        self.partition = None
        self._key = None
        self._event_map = None
        self._property_map = None
        self.label_provider = lambda type, id: "[{}:{}]".format(type, id)

    def __repr__(self):
        lvars = {}
        lvars.update(self.__dict__)
        lvars['message'] = self.message

        return str(self.__class__) + '\n' + '\n'.join(
            ('{} = {}'.format(item, lvars[item]) for item in lvars if not item.startswith('_')))

    def from_live_event(self, event_map: dict, event: Container, label_provider=None):
        if isinstance(label_provider, typing.Callable):
            self.label_provider = label_provider
        
        self._event_map = event_map
        self.parse_event(event)
        
        self._parse_event_map()

        return True

    def from_change(self, property_map, change, label_provider=None):
        if isinstance(label_provider, typing.Callable):
            self.label_provider = label_provider
        
        self._property_map = property_map
        self.raw = copy(change)

        self.timestamp = self.raw['time']
        self.partition = self.raw['partition']
        self.property = self.raw['property']
        self.value = self.raw['value']
        self.module = None
        self.type = self.raw['type']
        self.label = self.raw['label']
        self.major = None
        self.minor = None

        return self._parse_property_map()

    def _parse_property_map(self):
        if (self.raw['property']) not in self._property_map:
            return False
        
        property_map = copy(self._property_map[self.property])  # for inplace modifications
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
        
        self.change = {self.raw['property'] : self.raw['value']}
        self.tags = property_map.get('tags', [])

        return True

    def parse_event(self, message: Container):
        if message.fields.value.po.command != 0x0e:
            return False

        self.raw = copy(message.fields.value)  # Event raw data
        self.timestamp = self.raw.time  # Event timestamp
        self.partition = self.raw.partition  # Event Partition. if Type is system, partition may not be relevant
        self.module = self.raw.module_serial  # Event Module Serial
        self.label_type = self.raw.get('label_type', None)  # Type of element triggering the event
        self.label = self.raw.label.replace(b'\0', b' ').strip(b' ').decode(
            encoding=cfg.LABEL_ENCODING, errors='ignore')  # Event Element Label. May be overridden localy
        self.major = self.raw.event.major  # Event major code
        self.minor = self.raw.event.minor  # Event minor code

        self._parse_event_map()
    
        return True

    def _parse_event_map(self):
        if self.major not in self._event_map:
            raise (Exception("Unknown event major: {}".format(self.raw)))

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
    def key(self):
        if not self._key:
            self._key = "{},{},{}".format(self.type, self.label, ','.join("=".join([key, str(val)]) for key, val in self.change.items()))

        return self._key

    @property
    def message(self) -> str:
        return EventMessageFormatter().format(self._message_tpl, self)

    @property
    def name(self) -> str:
        key = self.partition if self.type == 'partition' else self.minor

        name = self.label_provider(self.type, key)
        if name:
            return name

        return '-'

    @property
    def props(self) -> dict:
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
