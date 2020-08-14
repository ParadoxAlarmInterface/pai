import logging
import os

import requests

from paradox.config import config as cfg
from paradox.event import EventLevel
from paradox.interfaces.text.core import ConfiguredAbstractTextInterface

logger = logging.getLogger("PAI").getChild(__name__)


class HomeAssistantNotificationsTextInterface(ConfiguredAbstractTextInterface):
    """Interface Class using Home Assistant"""

    def __init__(self, alarm):
        super().__init__(
            alarm,
            cfg.HOMEASSISTANT_NOTIFICATIONS_EVENT_FILTERS,
            cfg.HOMEASSISTANT_NOTIFICATIONS_ALLOW_EVENTS,
            cfg.HOMEASSISTANT_NOTIFICATIONS_IGNORE_EVENTS,
            cfg.HOMEASSISTANT_NOTIFICATIONS_MIN_EVENT_LEVEL,
        )

        self.token = os.environ.get("SUPERVISOR_TOKEN")
        if not self.token:
            logger.error(
                f'"SUPERVISOR_TOKEN" environment variable must be set to use {__class__.__name__}'
            )

    def send_message(self, message: str, level: EventLevel):
        if not self.token:
            logger.warning(
                'Unable to send a notification to Home Assistant. "SUPERVISOR_TOKEN" environment variable is not set'
            )
            return

        notifier_name = cfg.HOMEASSISTANT_NOTIFICATIONS_NOTIFIER_NAME
        url = f"http://supervisor/core/api/services/notify/{notifier_name}"

        payload = {"message": message, "title": "Paradox", "data": {"level": level}}

        headers = {"Authorization": f"Bearer {self.token}"}

        res = requests.post(url, json=payload, headers=headers)
        if res.status_code == 200:
            logger.debug(f"Notification sent: {message}, level={level}")
        else:
            logger.error(
                f"Failed to send notification: code={res.status_code}, text: {res.text}"
            )
