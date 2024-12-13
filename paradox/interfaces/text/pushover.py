import http.client
import logging
import re
import urllib

from paradox.config import config as cfg
from paradox.event import EventLevel
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface

logger = logging.getLogger("PAI").getChild(__name__)

_level_2_priority = {
    EventLevel.NOTSET: -2,
    EventLevel.DEBUG: -2,
    EventLevel.INFO: -1,
    EventLevel.WARN: 0,
    EventLevel.ERROR: 1,
    EventLevel.CRITICAL: 2,
}


class PushoverTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using Pushover"""

    def __init__(self, alarm):
        super().__init__(
            alarm,
            cfg.PUSHOVER_EVENT_FILTERS,
            cfg.PUSHOVER_ALLOW_EVENTS,
            cfg.PUSHOVER_IGNORE_EVENTS,
            cfg.PUSHOVER_MIN_EVENT_LEVEL,
        )

        self.users = {}

    def send_message(self, message: str, level: EventLevel):
        for settings in cfg.PUSHOVER_BROADCAST_KEYS:
            user_key = settings["user_key"]
            devices_raw = settings["devices"]

            if devices_raw == "*" or devices_raw is None:
                self._send_pushover_message(user_key, message, level)
            else:
                devices = list(filter(bool, re.split(r"[\s]*,[\s]*", devices_raw)))

                for device in devices:
                    self._send_pushover_message(user_key, message, level, device)

    def _send_pushover_message(self, user_key, message, level, device=None):
        conn = http.client.HTTPSConnection("api.pushover.net:443")
        params = {
            "token": cfg.PUSHOVER_KEY,
            "user": user_key,
            "message": message,
            "priority": _level_2_priority.get(level, 0),
            "title": "Alarm",
        }
        if device:
            params["device"] = device

        if params["priority"] == 2:
            params["retry"] = 30
            params["expire"] = 10800

        conn.request(
            "POST",
            "/1/messages.json",
            urllib.parse.urlencode(params),
            {"Content-type": "application/x-www-form-urlencoded"},
        )

        response = conn.getresponse()
        if response.status != 200:
            logger.error(f"Failed to send message: {response.reason}")
        else:
            logger.info(
                f"Notification sent: {message}, level={level}, device={device if device else 'all'}"
            )
        conn.close()
