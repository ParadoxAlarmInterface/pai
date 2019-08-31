import functools
import logging
import os
import typing

from paho.mqtt.client import Client, mqtt_cs_connected

from paradox.config import config as cfg
from paradox.interfaces import ThreadQueueInterface

logger = logging.getLogger('PAI').getChild(__name__)


class MQTTConnection(Client):
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(MQTTConnection, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        super(MQTTConnection, self).__init__("paradox_mqtt/{}".format(os.urandom(8).hex()))
        # self.on_message = functools.partial(self._call_registars, "on_message")
        self.on_connect = self._on_connect_cb
        self.on_disconnect = functools.partial(self._call_registars, "on_disconnect")

        self.registrars = []

        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.username_pw_set(username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

        self.will_set(
            '{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_INTERFACE_TOPIC, 'MQTTInterface'),
            'offline', 0, retain=True
        )

    def _call_registars(self, method, *args, **kwargs):
        for r in self.registrars:
            if hasattr(r, method) and isinstance(r["method"], typing.Callable):
                r["method"](*args, **kwargs)

    def register(self, cls):
        self.registrars.append(cls)

    @property
    def connected(self):
        return self._state == mqtt_cs_connected

    def _report_status(self, status):
        self.publish('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                       cfg.MQTT_INTERFACE_TOPIC,
                                       'MQTTInterface'),
                     status, 0, retain=True)

    def connect(self, host=cfg.MQTT_HOST, port=cfg.MQTT_PORT, keepalive=cfg.MQTT_KEEPALIVE,
                bind_address=cfg.MQTT_BIND_ADDRESS):
        super(MQTTConnection, self).connect(host=host, port=port, keepalive=keepalive, bind_address=bind_address)

    def _on_connect_cb(self, *args, **kwargs):
        self._report_status('online')
        self._call_registars("on_connect", *args, **kwargs)

    def disconnect(self):
        self._report_status('offline')
        super(MQTTConnection, self).disconnect()


class AbstractMQTTInterface(ThreadQueueInterface):
    """Interface Class using MQTT"""
    name = 'abstract_mqtt'

    def __init__(self):
        super().__init__()

        self.mqtt = MQTTConnection()
        self.mqtt.register(self)

    def run(self):
        if not self.mqtt.connected:
            self.mqtt.connect()
            self.mqtt.loop_start()

        super().run()

        if self.mqtt.connected:
            # Need to set as disconnect will delete the last will
            self.publish('{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC,
                                           cfg.MQTT_INTERFACE_TOPIC,
                                           self.__class__.__name__),
                         'offline', 0, retain=True)

            self.mqtt.disconnect()

        self.mqtt.loop_stop()

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        logger.debug("Stopping MQTT Interface")
        super().stop()

    def on_disconnect(self, mqttc, userdata, rc):
        logger.info("MQTT Broker Disconnected")

    def on_connect(self, mqttc, userdata, flags, result):
        logger.info("MQTT Broker Connected")

    def publish(self, topic, value, qos, retain):
        self.mqtt.publish(topic, value, qos, retain)
