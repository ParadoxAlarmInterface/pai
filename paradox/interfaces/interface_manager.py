import logging

from paradox.interfaces import Interface

logger = logging.getLogger("PAI").getChild(__name__)


class InterfaceManager:
    def __init__(self, alarm, config=None):
        self.alarm = alarm
        self.conf = config
        self.interfaces = []

    def start(self):
        if self.conf.GSM_ENABLE:
            try:
                from paradox.interfaces.text.gsm import GSMTextInterface

                self.register(GSMTextInterface(self.alarm))
            except:
                logger.exception("Unable to start GSM Interface")

        # Load Signal service
        if self.conf.SIGNAL_ENABLE:
            try:
                from paradox.interfaces.text.signal import SignalTextInterface

                self.register(SignalTextInterface(self.alarm))
            except:
                logger.exception("Unable to start Signal Interface")

        # Load an interface for exposing data and accepting commands
        if self.conf.MQTT_ENABLE:
            try:
                from paradox.interfaces.mqtt.basic import BasicMQTTInterface

                self.register(BasicMQTTInterface(self.alarm))
            except:
                logger.exception("Unable to start MQTT Interface")

        if self.conf.MQTT_HOMEASSISTANT_AUTODISCOVERY_ENABLE:
            try:
                from paradox.interfaces.mqtt.homeassistant import (
                    HomeAssistantMQTTInterface,
                )

                self.register(HomeAssistantMQTTInterface(self.alarm))
            except:
                logger.exception("Unable to start HomeAssistant MQTT Interface")

        if self.conf.HOMEASSISTANT_NOTIFICATIONS_ENABLE:
            try:
                from paradox.interfaces.text.homeassistant_notifications import (
                    HomeAssistantNotificationsTextInterface,
                )

                self.register(HomeAssistantNotificationsTextInterface(self.alarm))
            except:
                logger.exception("Unable to start HomeAssistant MQTT Interface")

        # Load Pushbullet service
        if self.conf.PUSHBULLET_ENABLE:
            try:
                from paradox.interfaces.text.pushbullet import PushbulletTextInterface

                self.register(PushbulletTextInterface(self.alarm))
            except:
                logger.exception("Unable to start Pushbullet Interface")

        # Load Pushover service
        if self.conf.PUSHOVER_ENABLE:
            try:
                from paradox.interfaces.text.pushover import PushoverTextInterface

                self.register(PushoverTextInterface(self.alarm))
            except:
                logger.exception("Unable to start Pushover Interface")

        # Load IP Interface
        if self.conf.IP_INTERFACE_ENABLE:
            try:
                from paradox.interfaces.ip_interface.interface import IPInterface

                self.register(IPInterface(self.alarm))
            except:
                logger.exception("Unable to start IP Interface")

        # Load Dummy Interface
        if self.conf.DUMMY_INTERFACE_ENABLE:
            try:
                from paradox.interfaces.text.dummy import DummyInterface

                self.register(DummyInterface(self.alarm))
            except:
                logger.exception("Unable to start Dummy Interface")

    def register(self, interface: Interface):
        logger.debug("Registering {}".format(interface.name))
        interface.start()  # Starts interface thread

        self.interfaces.append(interface)

    def stop(self):
        logger.info("Stopping all interfaces")
        for interface in self.interfaces:
            try:
                logger.info(f"Stopping {interface.name}")
                interface.stop()
                interface.alarm = None
            except:
                logger.exception("Error stopping interface {}".format(interface.name))
        logger.debug("All Interfaces stopped")
        self.interfaces = []
