import datetime
import json

import pytest

from paradox.event import Event
from paradox.interfaces.mqtt.basic import BasicMQTTInterface


@pytest.mark.asyncio
async def test_handle_panel_event(mocker):
    interface = BasicMQTTInterface()
    interface.mqtt = mocker.MagicMock()

    event = Event()
    event.label = "Test"
    event.minor = 0
    event.major = 0
    event.time = datetime.datetime(2019, 10, 18, 17, 15)

    interface._handle_panel_event(event)
    interface.mqtt.publish.assert_called_once_with('paradox/events',
                                                   json.dumps({"additional_data": {}, "change": {},
                                                               "key": "None,Test,", "label": "Test",
                                                               "level": "NOTSET", "major": 0, "message": "",
                                                               "minor": 0, "tags": [],
                                                               "time": "2019-10-18T17:15:00", "timestamp": 0,
                                                               "type": None}, sort_keys=True),
                                                   0, True)
