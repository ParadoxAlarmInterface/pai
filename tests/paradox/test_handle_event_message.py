import asyncio
import binascii
import logging

import pytest

from paradox.hardware.spectra_magellan.event import event_map
from paradox.hardware.spectra_magellan.parsers import LiveEvent
from paradox.paradox import Paradox

# Spectra/Magellan "Zone Garage open" (major 1, minor = zone 2)
ZONE_2_OPEN = binascii.unhexlify(
    "e2141301040b080102000000000000476172616765202020202020202020200000000000ab"
)


@pytest.mark.asyncio
async def test_zone_event_before_labels_are_loaded(mocker, caplog):
    """A zone can exist in storage before it has a ``key``.

    ``load_definitions`` creates zone objects without ``key``/``label``; the
    label loader adds them later. A live event arriving in between used to pass
    the ``element`` check in ``handle_event_message`` and then raise
    ``KeyError: 'key'`` in ``update_container_object``. The exception was
    logged and ``ps.sendEvent`` was skipped, so the event was lost.
    """
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_running_loop())
    sendEvent = mocker.patch("paradox.paradox.ps.sendEvent")

    alarm = Paradox(None)
    alarm.panel = mocker.MagicMock(event_map=event_map)
    mocker.spy(alarm.storage, "update_container_object")

    # Definitions loaded, labels not yet.
    alarm._on_definitions_load(data=dict(zone={2: dict(id=2, definition="follow")}))

    with caplog.at_level(logging.ERROR, logger="PAI"):
        alarm.handle_event_message(LiveEvent.parse(ZONE_2_OPEN))

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    alarm.storage.update_container_object.assert_not_called()
    sendEvent.assert_called_once()

    # Once labelled, the same event updates the zone as before.
    alarm._on_labels_load(
        data=dict(zone={2: dict(id=2, label="Garage", key="Garage")})
    )

    alarm.handle_event_message(LiveEvent.parse(ZONE_2_OPEN))

    alarm.storage.update_container_object.assert_called_once_with(
        "zone", 2, {"open": True}
    )
    assert alarm.storage.get_container_object("zone", 2)["open"] is True
    assert sendEvent.call_count == 2
