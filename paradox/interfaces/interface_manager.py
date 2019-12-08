import logging

logger = logging.getLogger('PAI').getChild(__name__)


class InterfaceManager:

    def __init__(self, config=None):
        self.conf = config
        self.interfaces = []

    def start(self):

        if self.conf.GSM_ENABLE:
            try:
                logger.info("Using GSM Interface")
                from paradox.interfaces.text.gsm import GSMTextInterface
                self.register(GSMTextInterface())
            except Exception:
                logger.exception("Unable to start GSM Interface")

        # Load Signal service
        if self.conf.SIGNAL_ENABLE:
            try:
                logger.info("Using Signal Interface")
                from paradox.interfaces.text.signal import SignalTextInterface
                self.register(SignalTextInterface())
            except Exception:
                logger.exception("Unable to start Signal Interface")

        # Load an interface for exposing data and accepting commands
        if self.conf.MQTT_ENABLE:
            try:
                logger.info("Using MQTT Interface")
                from paradox.interfaces.mqtt.basic import BasicMQTTInterface
                self.register(BasicMQTTInterface())
            except Exception:
                logger.exception("Unable to start MQTT Interface")

        if self.conf.MQTT_HOMEASSISTANT_AUTODISCOVERY_ENABLE:
            try:
                logger.info("Using HomeAssistant MQTT Interface")
                from paradox.interfaces.mqtt.homeassistant import HomeAssistantMQTTInterface
                self.register(HomeAssistantMQTTInterface())
            except Exception:
                logger.exception("Unable to start HomeAssistant MQTT Interface")

        # Load Pushbullet service
        if self.conf.PUSHBULLET_ENABLE:
            try:
                logger.info("Using Pushbullet Interface")
                from paradox.interfaces.text.pushbullet import PushbulletTextInterface
                self.register(PushbulletTextInterface())
            except Exception:
                logger.exception("Unable to start Pushbullet Interface")

        # Load Pushover service
        if self.conf.PUSHOVER_ENABLE:
            try:
                logger.info("Using Pushover Interface")
                from paradox.interfaces.text.pushover import PushoverTextInterface
                self.register(PushoverTextInterface())
            except Exception:
                logger.exception("Unable to start Pushover Interface")

        # Load IP Interface
        if self.conf.IP_INTERFACE_ENABLE:
            try:
                logger.info("Using IP Interface")
                from paradox.interfaces.ip_interface import IPInterface
                self.register(IPInterface())
            except Exception:
                logger.exception("Unable to start IP Interface")

        # Load Dummy Interface
        if self.conf.DUMMY_INTERFACE_ENABLE:
            try:
                logger.info("Using Dummy Interface")
                from paradox.interfaces.text.dummy import DummyInterface
                self.register(DummyInterface())
            except Exception:
                logger.exception("Unable to start Dummy Interface")

    def register(self, interface):
        logger.debug("Registering Interface {}".format(interface.name))
        interface.start()  # Starts interface thread

        self.interfaces.append(interface)

    def stop(self):
        logger.debug("Stopping all interfaces")
        for interface in self.interfaces:
            try:
                logger.debug("Stopping {}".format(interface.name))
                interface.stop()
            except Exception:
                logger.exception(
                    "Error stopping interface {}".format(interface.name))
        logger.debug("All Interfaces stopped")

    def set_alarm(self, alarm):
        for interface in self.interfaces:
            try:
                interface.set_alarm(alarm)
            except Exception:
                logger.exception(
                    "Error adding alarm to interface {}".format(interface.name))
