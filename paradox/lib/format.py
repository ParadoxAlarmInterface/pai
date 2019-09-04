import string
import re
import logging

logger = logging.getLogger('PAI').getChild(__name__)

re_magick_placeholder = re.compile('@(?P<type>[a-z]+)(:?#(?P<source>[a-z0-9_]+))?')

class EventMessageFormatter(string.Formatter):

    @staticmethod
    def _hasattr(event, key):
        if key in event.additional_data:
            return True
        return hasattr(event, key)

    @staticmethod
    def _getattr(event, key):
        if key in event.additional_data:
            return event.additional_data[key]
        return getattr(event, key)

    def get_value(self, key, args, kwargs):
        event = args[0]

        if isinstance(key, int) or isinstance(key, float):
            return key
        elif key.startswith('@'):  # pure magic is happening here
            label_provider = event.label_provider
            m = re_magick_placeholder.match(key)
            if m:
                element_type = m.group('type')
                source = m.group('source') or (element_type if self._hasattr(event, element_type) else 'minor')
                key = self._getattr(event, source)

                return label_provider(element_type, key)
            else:
                logger.error('Magic placeholder "{}" has wrong format'.format(key))
                return "{error}"

        r = self._getattr(event, key.lower())
        if key[0].isupper():
            r = r.title()

        return r