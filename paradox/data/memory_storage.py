import logging
from collections import defaultdict
from enum import Enum
from typing import Callable

from paradox.config import config as cfg
from paradox.event import Change
from paradox.lib import ps
from .element_type_container import ElementTypeContainer

logger = logging.getLogger('PAI').getChild(__name__)


class PublishPropertyChange(Enum):
    NO = 0
    DEFAULT = 1
    YES = 2


class MemoryStorage:
    def __init__(self):
        self.data = defaultdict(ElementTypeContainer)

    def get_container(self, container_name) -> ElementTypeContainer:
        return self.data[container_name]

    def get_container_object(self, container_name, key, create_if_missing=False):
        c = self.get_container(container_name)
        el = c.get(key)
        if create_if_missing and el is None:
            el = c[key] = {'key': key}

        return el

    def update_container_object(self, container_name: str, key: str, changes: dict):
        assert container_name is not None
        assert key is not None
        assert isinstance(changes, dict)
        if not changes:  # Has at least one element
            return

        # logger.debug('update_properties %s/%s=%s', container_name, key, change)
        element = self.get_container_object(container_name, key, create_if_missing=True)
        object_key = element['key']

        # Publish changes and update state
        for property_name, property_value in changes.items():

            if not isinstance(property_name, str):
                logger.debug('Invalid property name ({}/{}/{}) type: {}'.format(container_name, object_key, property_name,
                                                                                type(property_name)))
                continue
            if property_name.startswith('_'):  # skip private properties
                continue

            old = element.get(property_name)

            if isinstance(property_value, Callable):  # function to make new value from the old one
                try:
                    property_value = property_value(old)
                except Exception:
                    logger.exception('Exception caught during property "%s" convert. Ignoring', property_name)
                    continue

            # Standard processing of changes
            if property_name in element:
                if old == property_value and not cfg.PUSH_UPDATE_WITHOUT_CHANGE:
                    continue
                element[property_name] = property_value
            else:
                element[property_name] = property_value  # Initial value, do not notify
                # suppress = 'trouble' not in property_name

            change_object = Change(container_name, object_key, property_name, property_value, old)
            logger.debug(change_object)
            ps.sendChange(change_object)
