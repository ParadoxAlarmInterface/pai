import logging
import re

from paradox.lib import ps
from paradox.event import EventLevel
from paradox.config import config as cfg
from paradox.interfaces import ThreadQueueInterface

logger = logging.getLogger('PAI').getChild(__name__)

class AbstractTextInterface(ThreadQueueInterface):
    """Interface Class using any Text interface"""
    name = 'abstract_text'

    def __init__(self, events_allow, events_ignore, min_level=EventLevel.INFO):
        super().__init__()

        self.filter_events_allow = events_allow
        self.filter_events_ignore = events_ignore
        self.filter_events_level = min_level
        self.alarm = None

    def stop(self):
        super().stop()
        if self.alarm is not None:
            self.alarm.disconnect()

    def run(self):
        logger.info("Starting Interface")

        ps.subscribe(self._handle_panel_event, "events")
        ps.subscribe(self._handle_notify, "notifications")

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

    def _send_message(self, message):
        pass

    def _handle_notify(self, message):

        if message['level'] < self.filter_events_level:
            return

        if message['source'] != self.name:
            self._send_message(message['payload'])

    def _handle_panel_event(self, event):

        if event.level < self.filter_events_level:
            return

        major_code = event.major
        minor_code = event.minor

        # Only let some elements pass
        allow = False
        for ev in self.filter_events_allow:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = True
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = True
                    break

        # Ignore some events
        for ev in self.filter_events_ignore:
            if isinstance(ev, tuple):
                if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                    allow = False
                    break
            elif isinstance(ev, str):
                if re.match(ev, event.key):
                    allow = False
                    break

        if allow:
            self._send_message(event.message)

    def _handle_command(self, message):
        message = cfg.COMMAND_ALIAS.get(message, message)

        tokens = message.split(" ")

        if len(tokens) != 3:
            m = "Invalid command"
            logger.warning(m)
            return m

        if self.alarm is None:
            m = "No alarm registered"
            logger.error(m)
            return m

        element_type = tokens[0].lower()
        element = tokens[1]
        command = self._normalize_payload(tokens[2].lower())

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

        logger.info("OK")
        return "OK"

    #TODO: Remove this (to panels?)
    @staticmethod
    def _normalize_payload(message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None
