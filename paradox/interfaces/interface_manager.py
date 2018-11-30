
import logging

FORMAT = '%(asctime)s - %(levelname)-8s - %(name)s - %(message)s'

logger = logging.getLogger('PAI').getChild(__name__)


class InterfaceManager():

    def __init__(self, config=None):
        self.conf = config
        self.interfaces = []

    def start(self):

        if self.conf.GSM_ENABLE:
            try:
                logger.info("Using GSM Interface")
                from paradox.interfaces.gsm_interface import GSMInterface
                self.register(GSMInterface())
            except Exception:
                logger.exception("Unable to start GSM Interface")

        # Load Signal service
        if self.conf.SIGNAL_ENABLE:
            try:
                logger.info("Using Signal Interface")
                from paradox.interfaces.signal_interface import SignalInterface
                self.register(SignalInterface())
            except Exception:
                logger.exception("Unable to start Signal Interface")

        # Load an interface for exposing data and accepting commands
        if self.conf.MQTT_ENABLE:
            try:
                logger.info("Using MQTT Interface")
                from paradox.interfaces.mqtt_interface import MQTTInterface
                self.register(MQTTInterface(), initial=True)
            except Exception:
                logger.exception("Unable to start MQTT Interface")

        # Load Pushbullet service
        if self.conf.PUSHBULLET_ENABLE:
            try:
                logger.info("Using Pushbullet Interface")
                from paradox.interfaces.pushbullet_interface import PushBulletInterface
                self.register(PushBulletInterface())
            except Exception:
                logger.exception("Unable to start Pushbullet Interface")

        # Load IP Interface
        if self.conf.IP_INTERFACE_ENABLE:
            try:
                logger.info("Using IP Interface")
                from paradox.interfaces.ip_interface import IPInterface
                self.register(IPInterface())
            except Exception:
                logger.exception("Unable to start IP Interface")

    def register(self, interface, initial=False):
        logger.debug("Registering Interface {}".format(interface.name))
        interface.start()

        self.interfaces.append(dict(name=interface.name, object=interface, initial=initial))
        try:
            object.set_notify(self)
        except Exception:
            logger("Error registering interface {}".format(interface.name))

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
