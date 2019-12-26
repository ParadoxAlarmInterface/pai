import asyncio
import logging
import os
import socket
import time
import typing
from enum import Enum

from paho.mqtt.client import Client, MQTT_ERR_SUCCESS

from paradox.config import config as cfg
from paradox.interfaces import AsyncInterface

logger = logging.getLogger('PAI').getChild(__name__)

ELEMENT_TOPIC_MAP = dict(partition=cfg.MQTT_PARTITION_TOPIC, zone=cfg.MQTT_ZONE_TOPIC,
                         output=cfg.MQTT_OUTPUT_TOPIC, repeater=cfg.MQTT_REPEATER_TOPIC,
                         bus=cfg.MQTT_BUS_TOPIC, keypad=cfg.MQTT_KEYPAD_TOPIC,
                         system=cfg.MQTT_SYSTEM_TOPIC, user=cfg.MQTT_USER_TOPIC)


class ConnectionState(Enum):
    NEW = 0
    CONNECTING = 1
    CONNECTED = 2
    DISCONNECTING = 3


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
        self.state = ConnectionState.NEW
        # self.on_subscribe = lambda client, userdata, mid, granted_qos: logger.debug("Subscribed: %s" %(mid))
        # self.on_message = lambda client, userdata, message: logger.debug("Message received: %s" % str(message))
        # self.on_publish = lambda client, userdata, mid: logger.debug("Message published: %s" % str(mid))

        self.registrars = []

        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.username_pw_set(username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

        self.will_set(self._status_topic, 'offline', 0, retain=True)

    def start(self):
        if self.state == ConnectionState.NEW:
            self.loop_start()

            # TODO: Some initial connection retry mechanism required
            try:
                self.connect_async(host=cfg.MQTT_HOST, port=cfg.MQTT_PORT, keepalive=cfg.MQTT_KEEPALIVE,
                    bind_address=cfg.MQTT_BIND_ADDRESS, bind_port=cfg.MQTT_BIND_PORT)

                self.state = ConnectionState.CONNECTING

                logger.info("MQTT loop started")
            except socket.gaierror:
                logger.exception("Failed to connect to MQTT (%s:%d)", cfg.MQTT_HOST, cfg.MQTT_PORT)

    def stop(self):
        if self.state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]:
            self.disconnect()
            self.loop_stop()
            logger.info("MQTT loop stopped")

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
        return self.state == ConnectionState.CONNECTED

    def _report_status(self, status):
        self.publish(self._status_topic, status, 0, retain=True)

    def _on_connect_cb(self, client, userdata, flags, result):
        if result == MQTT_ERR_SUCCESS:
            logger.info("MQTT Broker Connected")
            self.state = ConnectionState.CONNECTED
            self._report_status('online')
            self._call_registars("on_connect", client, userdata, flags, result)
        else:
            logger.error("Failed to connect to MQTT. Code: %d" % result)

    def _on_disconnect_cb(self, client, userdata, rc):
        if rc == MQTT_ERR_SUCCESS:
            logger.info("MQTT Broker Disconnected")
        else:
            logger.error("MQTT Broker unexpectedly disconnected. Code: %d", rc)

        self.state = ConnectionState.NEW
        self._call_registars("on_disconnect", client, userdata, rc)

    def disconnect(self, reasoncode=None, properties=None):
        self.state = ConnectionState.DISCONNECTING
        self._report_status('offline')
        super(MQTTConnection, self).disconnect()


class AbstractMQTTInterface(AsyncInterface):
    """Interface Class using MQTT"""
    name = 'abstract_mqtt'

    def __init__(self):
        super().__init__()

        self.mqtt = MQTTConnection.get_instance()
        self.mqtt.register(self)
        logger.debug("Registars: %d", len(self.mqtt.registrars))

        self.republish_cache = {}

    def start(self):
        super().start()
        self.mqtt.start()

    def stop(self):
        """ Stops the MQTT Interface Thread"""
        logger.debug("Stopping MQTT Interface")
        self.mqtt.stop()
        super().stop()

    async def run(self):
        while True:
            await asyncio.sleep(cfg.MQTT_REPUBLISH_INTERVAL)

            trigger = time.time() - cfg.MQTT_REPUBLISH_INTERVAL

            for k, v in filter(lambda f: f[1].get("last_publish") <= trigger, self.republish_cache.items()):
                self.publish(k, v['value'], v['qos'], v['retain'])

    def publish(self, topic, value, qos, retain):
        self.republish_cache[topic] = {'value': value, 'qos': qos, 'retain': retain, 'last_publish': time.time()}
        self.mqtt.publish(topic, value, qos, retain)
        logger.debug("MQTT: {}={}".format(topic, value))

    def subscribe_callback(self, sub, callback: typing.Callable):
        self.mqtt.message_callback_add(sub, callback)
        self.mqtt.subscribe(sub)

    def on_disconnect(self, client, userdata, rc):
        """ Called from MQTT connection """
        pass

    def on_connect(self, client, userdata, flags, result):
        """ Called from MQTT connection """
        pass