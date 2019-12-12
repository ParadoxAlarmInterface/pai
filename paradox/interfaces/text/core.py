import logging

from paradox.lib import ps
from paradox.lib.event_filter import LiveEventRegexpFilter, EventTagFilter, EventFilter
from paradox.event import EventLevel, Event, Notification
from paradox.config import config as cfg
from paradox.interfaces import ThreadQueueInterface

logger = logging.getLogger('PAI').getChild(__name__)



class AbstractTextInterface(ThreadQueueInterface):
    """Interface Class using any Text interface"""
    name = 'abstract_text'

    def __init__(self, event_filter: EventFilter, min_level=EventLevel.INFO):
        super().__init__()

        self.event_filter = event_filter

        self.min_level = min_level
        self.alarm = None

    def stop(self):
        super().stop()
        if self.alarm is not None:
            self.alarm.disconnect()

    def run(self):
        logger.info("Starting Interface")

        ps.subscribe(self.handle_panel_event, "events")
        ps.subscribe(self.handle_notify, "notifications")

        try:
            self._run()
        except (KeyboardInterrupt, SystemExit):
            logger.debug("Interface loop stopping")
            self.stop()
        except Exception:
            logger.exception("Interface loop")

        super().run()

    def _run(self):
        pass

    def set_alarm(self, alarm):
        self.alarm = alarm

    def send_message(self, message: str, level: EventLevel):
        pass

    def notification_filter(self, notification: Notification):
        return notification.level >= self.min_level and notification.sender != self.name

    def handle_notify(self, notification: Notification):
        if self.notification_filter(notification):
            self.send_message(notification.message, notification.level)

    def handle_panel_event(self, event: Event):
        if self.event_filter.match(event):
            self.send_message(event.message, event.level)

    def handle_command(self, message_raw):
        message = cfg.COMMAND_ALIAS.get(message_raw, message_raw)

        tokens = message.split(" ")

        if len(tokens) != 3:
            m = "Invalid: {}".format(message_raw)
            logger.warning(m)
            return m

        if self.alarm is None:
            m = "No alarm registered"
            logger.error(m)
            return m

        element_type = tokens[0].lower()
        element = tokens[1]
        command = self.normalize_payload(tokens[2].lower())

        # Process a Zone Command
        if element_type == 'zone':
            if not self.alarm.control_zone(element, command):
                m = "Zone command error: {}={}".format(element, command)
                logger.warning(m)
                return m

        # Process a Partition Command
        elif element_type == 'partition':
            if not self.alarm.control_partition(element, command):
                m = "Partition command error: {}={}".format(element, command)
                logger.warning(m)
                return m

        # Process an Output Command
        elif element_type == 'output':
            if not self.alarm.control_output(element, command):
                m = "Output command error: {}={}".format(element, command)
                logger.warning(m)
                return m
        else:
            m = "Invalid control element: {}".format(element)
            logger.error(m)
            return m

        logger.info("OK: {}".format(message_raw))
        return "OK"

    #TODO: Remove this (to panels?)
    @staticmethod
    def normalize_payload(message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None


class ConfiguredAbstractTextInterface(AbstractTextInterface):
    def __init__(self, EVENT_FILTERS, ALLOW_EVENTS, IGNORE_EVENTS, MIN_EVENT_LEVEL):
        if EVENT_FILTERS and (ALLOW_EVENTS or IGNORE_EVENTS):
            raise AssertionError('You can not use *_EVENT_FILTERS and *_ALLOW_EVENTS+*_IGNORE_EVENTS simultaneously')

        min_level = EventLevel.from_name(MIN_EVENT_LEVEL)
        if ALLOW_EVENTS or IGNORE_EVENTS: # Use if defined, else use TAGS as default
            logger.debug("Using REGEXP Filter")
            event_filter = LiveEventRegexpFilter(ALLOW_EVENTS, IGNORE_EVENTS, min_level)
        else:
            logger.debug("Using Tag Filter")
            event_filter = EventTagFilter(EVENT_FILTERS, min_level)

        super().__init__(event_filter=event_filter, min_level=min_level)
