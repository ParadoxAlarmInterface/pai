import functools
import logging
import os
import typing
import re

from paho.mqtt.client import Client, mqtt_cs_connected, MQTT_ERR_SUCCESS

from paradox.config import config as cfg
from paradox.interfaces import AsyncQueueInterface

logger = logging.getLogger('PAI').getChild(__name__)

ELEMENT_TOPIC_MAP = dict(partition=cfg.MQTT_PARTITION_TOPIC, zone=cfg.MQTT_ZONE_TOPIC,
                         output=cfg.MQTT_OUTPUT_TOPIC, repeater=cfg.MQTT_REPEATER_TOPIC,
                         bus=cfg.MQTT_BUS_TOPIC, keypad=cfg.MQTT_KEYPAD_TOPIC,
                         system=cfg.MQTT_SYSTEM_TOPIC, user=cfg.MQTT_USER_TOPIC)

# re_topic_dirty = re.compile(r'[+#/]')
re_topic_dirty = re.compile(r'\W')


def sanitize_topic_part(name):
    if isinstance(name, int):
        return str(name)
    else:
        return re_topic_dirty.sub('_', name).strip('_')


class MQTTConnection(Client):
    _instance = None
    @classmethod
    def get_instance(cls) -> 'MQTTConnection':
        if cls._instance is None:
            cls._instance = MQTTConnection()

        return cls._instance

    def __init__(self):
        super(MQTTConnection, self).__init__("paradox_mqtt/{}".format(os.urandom(8).hex()))
        self._status_topic = '{}/{}/{}'.format(cfg.MQTT_BASE_TOPIC, cfg.MQTT_INTERFACE_TOPIC, 'MQTTInterface')
        self.on_connect = self._on_connect_cb
        self.on_disconnect = self._on_disconnect_cb
        # self.on_subscribe = lambda client, userdata, mid, granted_qos: logger.debug("Subscribed: %s" %(mid))
        # self.on_message = lambda client, userdata, message: logger.debug("Message received: %s" % str(message))
        # self.on_publish = lambda client, userdata, mid: logger.debug("Message published: %s" % str(mid))

        self.registrars = []

        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.username_pw_set(username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

        self.will_set(self._status_topic, 'offline', 0, retain=True)

    def _call_registars(self, method, *args, **kwargs):
        for r in self.registrars:
            try:
                if hasattr(r, method) and isinstance(getattr(r, method), typing.Callable):
                    getattr(r, method)(*args, **kwargs)
            except Exception as e:
                logger.exception('Failed to call "%s" on "%s"', method, r.__class__.__name__)

    def register(self, cls):
        self.registrars.append(cls)

    @property
    def connected(self):
        return self._state == mqtt_cs_connected

    def _report_status(self, status):
        self.publish(self._status_topic, status, 0, retain=True)

    def connect(self, host=cfg.MQTT_HOST, port=cfg.MQTT_PORT, keepalive=cfg.MQTT_KEEPALIVE,
                bind_address=cfg.MQTT_BIND_ADDRESS):
        super(MQTTConnection, self).connect(host=host, port=port, keepalive=keepalive, bind_address=bind_address)

    def _on_connect_cb(self, client, userdata, flags, result):
        if result == MQTT_ERR_SUCCESS:
            logger.info("MQTT Broker Connected")
            self._report_status('online')
            self._call_registars("on_connect", client, userdata, flags, result)
        else:
            logger.error("Failed to connect to MQTT. Code: %d" % result)

    def _on_disconnect_cb(self, client, userdata, rc):
        if rc == MQTT_ERR_SUCCESS:
            logger.info("MQTT Broker Disconnected")
        else:
            logger.error("MQTT Broker unexpectedly disconnected. Code: %d", rc)

        self._call_registars("on_disconnect", client, userdata, rc)

    def disconnect(self):
        self._report_status('offline')
        super(MQTTConnection, self).disconnect()


class AbstractMQTTInterface(AsyncQueueInterface):
    """Interface Class using MQTT"""
    name = 'abstract_mqtt'

    def __init__(self):
        super().__init__()

        self.mqtt = MQTTConnection.get_instance()
        self.mqtt.register(self)
        logger.debug("Registars: %d", len(self.mqtt.registrars))

    async def run(self):
        if not self.mqtt.connected:
            self.mqtt.connect()
            self.mqtt.loop_start()

        await super().run()

        if self.mqtt.connected:
            self.mqtt.disconnect()

        self.mqtt.loop_stop()

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        logger.debug("Stopping MQTT Interface")
        super().stop()

    def on_disconnect(self, client, userdata, rc):
        pass

    def on_connect(self, client, userdata, flags, result):
        pass

    def publish(self, topic, value, qos, retain):
        self.mqtt.publish(topic, value, qos, retain)

    def subscribe_callback(self, sub, callback: typing.Callable):
        self.mqtt.message_callback_add(sub, callback)
        self.mqtt.subscribe(sub)