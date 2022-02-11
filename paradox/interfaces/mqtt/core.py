import asyncio
import logging
import os
import socket
import ssl
import sys
import time
import typing
from enum import Enum

from paho.mqtt.client import LOGGING_LEVEL, MQTT_ERR_SUCCESS, Client, connack_string, MQTTv311, MQTTv31, MQTTv5

from paradox.config import config as cfg
from paradox.data.enums import RunState
from paradox.interfaces import ThreadQueueInterface
from paradox.lib import ps

logger = logging.getLogger("PAI").getChild(__name__)


class ConnectionState(Enum):
    NEW = 0
    CONNECTING = 1
    CONNECTED = 2
    DISCONNECTING = 3


RUN_STATE_2_PAYLOAD = {
    RunState.ERROR: "error",
    RunState.INIT: "initializing",
    RunState.PAUSE: "paused",
    RunState.CONNECTED: "connected",
    RunState.RUN: "online",
    RunState.STOP: "stopped",
}

protocol_map = {
    "3.1": MQTTv31,
    "3.1.1": MQTTv311,
    "5": MQTTv5
}

class MQTTConnection():
    client: Client
    _instance = None

    @classmethod
    def get_instance(cls) -> "MQTTConnection":
        if cls._instance is None:
            cls._instance = MQTTConnection()

        return cls._instance

    def __init__(self):
        self.client = Client(
            "pai"+os.urandom(8).hex(),
            protocol=protocol_map.get(str(cfg.MQTT_PROTOCOL), MQTTv311),
            transport=cfg.MQTT_TRANSPORT,
        )
        self._last_pai_status = "unknown"
        self.pai_status_topic = "{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC, cfg.MQTT_INTERFACE_TOPIC, "pai_status"
        )
        self.availability_topic = "{}/{}/{}".format(
            cfg.MQTT_BASE_TOPIC, cfg.MQTT_INTERFACE_TOPIC, "availability"
        )
        self.client.on_connect = self._on_connect_cb
        self.client.on_disconnect = self._on_disconnect_cb
        self.state = ConnectionState.NEW
        # self.client.enable_logger(logger)

        # self.client.on_subscribe = lambda client, userdata, mid, granted_qos: logger.debug("Subscribed: %s" %(mid))
        # self.client.on_message = lambda client, userdata, message: logger.debug("Message received: %s" % str(message))
        # self.client.on_publish = lambda client, userdata, mid: logger.debug("Message published: %s" % str(mid))

        ps.subscribe(self.on_run_state_change, "run-state")

        self.registrars = []

        if cfg.MQTT_USERNAME is not None and cfg.MQTT_PASSWORD is not None:
            self.client.username_pw_set(username=cfg.MQTT_USERNAME, password=cfg.MQTT_PASSWORD)

        if cfg.MQTT_TLS_CERT_PATH is not None:
            self.client.tls_set(
                ca_certs=cfg.MQTT_TLS_CERT_PATH,
                certfile=None,
                keyfile=None,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLSv1_2,
                ciphers=None,
            )
            self.client.tls_insecure_set(False)

        self.client.will_set(self.availability_topic, "offline", 0, retain=True)

        self.client.on_log = self.on_client_log

    def on_client_log(self, client, userdata, level, buf):
        level_std = LOGGING_LEVEL[level]
        exc_info = None

        type_, exc, trace = sys.exc_info()
        if exc:  # Can be (socket.error, OSError, WebsocketConnectionError, ...)
            if hasattr(exc, "errno"):
                exc_msg = f"{os.strerror(exc.errno)}({exc.errno})"
                if exc.errno in [22, 49]:
                    level_std = logging.ERROR
                    buf = f"{buf}: Please check MQTT connection settings. Especially MQTT_BIND_ADDRESS and MQTT_BIND_PORT"
            else:
                exc_msg = str(exc)

            buf = f"{buf}: {exc_msg}"
            if "Connection failed" in buf:
                level_std = logging.WARNING

        if level_std > logging.DEBUG:
            logger.log(level_std, buf, exc_info=exc_info)

    def on_run_state_change(self, state: RunState):
        v = RUN_STATE_2_PAYLOAD.get(state, "unknown")
        self._report_pai_status(v)

    def start(self):
        if self.state == ConnectionState.NEW:
            self.client.loop_start()

            # TODO: Some initial connection retry mechanism required
            try:
                self.client.connect_async(
                    host=cfg.MQTT_HOST,
                    port=cfg.MQTT_PORT,
                    keepalive=cfg.MQTT_KEEPALIVE,
                    bind_address=cfg.MQTT_BIND_ADDRESS,
                    bind_port=cfg.MQTT_BIND_PORT,
                )

                self.state = ConnectionState.CONNECTING

                logger.info("MQTT loop started")
            except socket.gaierror:
                logger.exception(
                    "Failed to connect to MQTT (%s:%d)", cfg.MQTT_HOST, cfg.MQTT_PORT
                )

    def stop(self):
        if self.state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]:
            self.disconnect()
            self.client.loop_stop()
            logger.info("MQTT loop stopped")

    def publish(self, topic, payload=None, *args, **kwargs):
        logger.debug("MQTT: {}={}".format(topic, payload))

        self.client.publish(topic, payload, *args, **kwargs)

    def _call_registars(self, method, *args, **kwargs):
        for r in self.registrars:
            try:
                if hasattr(r, method) and isinstance(
                    getattr(r, method), typing.Callable
                ):
                    getattr(r, method)(*args, **kwargs)
            except:
                logger.exception(
                    'Failed to call "%s" on "%s"', method, r.__class__.__name__
                )

    def register(self, cls):
        self.registrars.append(cls)

        self.start()

    def unregister(self, cls):
        self.registrars.remove(cls)

        if len(self.registrars) == 0:
            self.stop()

    @property
    def connected(self):
        return self.state == ConnectionState.CONNECTED

    def _report_pai_status(self, status):
        self._last_pai_status = status
        self.publish(self.pai_status_topic, status, qos=cfg.MQTT_QOS, retain=True)
        self.publish(
            self.availability_topic,
            "online" if status in ["online", "paused"] else "offline",
            qos=cfg.MQTT_QOS,
            retain=True,
        )

    def _on_connect_cb(self, client, userdata, flags, result, properties=None):
        # called on Thread-6
        if result == MQTT_ERR_SUCCESS:
            logger.info("MQTT Broker Connected")
            self.state = ConnectionState.CONNECTED
            self._report_pai_status(self._last_pai_status)
            self._call_registars("on_connect", client, userdata, flags, result)
        else:
            logger.error(f"Failed to connect to MQTT: {connack_string(result)} ({result})")

    def _on_disconnect_cb(self, userdata, rc, properties=None):
        # called on Thread-6
        if rc == MQTT_ERR_SUCCESS:
            logger.info("MQTT Broker Disconnected")
        else:
            logger.error(f"MQTT Broker unexpectedly disconnected. Code: {rc}")

        self.state = ConnectionState.NEW
        self._call_registars("on_disconnect", self.client, userdata, rc)

    def disconnect(self, reasoncode=None, properties=None):
        self.state = ConnectionState.DISCONNECTING
        self._report_pai_status("offline")
        self.client.disconnect()

    def message_callback_add(self, *args, **kwargs):
        self.client.message_callback_add(*args, **kwargs)

    def subscribe(self, *args, **kwargs):
        self.client.subscribe(*args, **kwargs)


class AbstractMQTTInterface(ThreadQueueInterface):
    """Interface Class using MQTT"""

    def __init__(self, alarm):
        super().__init__(alarm)

        self.mqtt = MQTTConnection.get_instance()
        self.republish_cache = {}

    def start(self):
        super().start()
        self.mqtt.register(self)
        logger.debug("Registars: %d", len(self.mqtt.registrars))

    def stop(self):
        """ Stops the MQTT Interface Thread"""

        def stop_loop():
            self.republish_task.cancel()
            self.loop.stop()

        self.loop.call_soon_threadsafe(stop_loop)

        self.mqtt.unregister(self)

        super().stop()

    async def republish_loop(self):
        while True:
            await asyncio.sleep(cfg.MQTT_REPUBLISH_INTERVAL)
            trigger = time.time() - cfg.MQTT_REPUBLISH_INTERVAL

            for k, v in filter(
                lambda f: f[1].get("last_publish") <= trigger,
                self.republish_cache.items(),
            ):
                self.publish(k, v["value"], v["qos"], v["retain"])

    def _run(self):
        super(AbstractMQTTInterface, self)._run()

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.republish_task = self.loop.create_task(self.republish_loop())

        self.loop.run_forever()
        self.loop.close()

    def publish(self, topic, value, qos, retain):
        self.republish_cache[topic] = {
            "value": value,
            "qos": qos,
            "retain": retain,
            "last_publish": time.time(),
        }
        self.loop.call_soon_threadsafe(self.mqtt.publish, topic, value, qos, retain)

    def _publish_command_status(self, message):
        if cfg.MQTT_PUBLISH_COMMAND_STATUS:
            self.publish(
                f"{cfg.MQTT_BASE_TOPIC}/{cfg.MQTT_INTERFACE_TOPIC}/{cfg.MQTT_COMMAND_STATUS_TOPIC}",
                message,
                qos=2,
                retain=True,
            )

    def subscribe_callback(self, sub, callback: typing.Callable):
        self.mqtt.message_callback_add(sub, callback)
        self.mqtt.subscribe(sub)

    def on_disconnect(self, client, userdata, rc):
        """ Called from MQTT connection """
        pass

    def on_connect(self, client, userdata, flags, result):
        """ Called from MQTT connection """
        pass
