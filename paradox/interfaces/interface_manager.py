
import logging

FORMAT = '%(asctime)s - %(levelname)-8s - %(name)s - %(message)s'

logger = logging.getLogger('PAI').getChild(__name__)


class InterfaceManager():

    def __init__(self, config=None):
        self.conf = config
        self.interfaces = []

    def register(self, name, object, initial=False):
        logger.debug("Registering Interface {}".format(name))

        self.interfaces.append(dict(name=name, object=object, initial=initial))
        try:
            object.set_notify(self)
        except Exception:
            logger("Error registering interface {}".format(name))

    def event(self, raw):
        for interface in self.interfaces:
            try:
                interface['object'].event(raw)
            except Exception:
                logger.exception(
                    "Error dispatching event to interface {}".format(interface['name']))

    def change(self, element, label, property, value, initial=False):
        for interface in self.interfaces:

            if not interface['initial'] and initial:
                continue

            try:
                interface['object'].change(element, label, property, value)
            except Exception:
                logger.exception(
                    "Error dispatching change to interface {}".format(interface['name']))

    def notify(self, sender, message, level=logging.INFO):
        for interface in self.interfaces:
            try:
                if sender != interface['name']:
                    interface['object'].notify(sender, message, level)
            except Exception:
                logger.exception(
                    "Error dispatching notification to interface {}".format(interface['name']))

    def stop(self):
        logger.debug("Stopping all interfaces")
        for interface in self.interfaces:
            try:
                logger.debug("\t{}".format(interface['name']))
                interface['object'].stop()
            except Exception:
                logger.exception(
                    "Error stoping interface {}".format(interface['name']))
        logger.debug("All Interfaces stopped")

    def set_alarm(self, alarm):
        for interface in self.interfaces:
            try:
                interface['object'].set_alarm(alarm)
            except Exception:
                logger.exception(
                    "Error adding alarm to interface {}".format(interface['name']))
