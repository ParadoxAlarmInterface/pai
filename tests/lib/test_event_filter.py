import binascii

from paradox.event import Event, LiveEvent, EventLevel
from paradox.hardware.evo.event import event_map
from paradox.hardware.evo.parsers import LiveEvent as LiveEventMessage
from paradox.lib.event_filter import EventTagFilter


def test_tag_match():
    event = Event()
    event.level = EventLevel.INFO
    event.tags = ['arm', 'restore']
    event.type = 'partition'

    assert EventTagFilter(['partition+arm']).match(event) is True
    assert EventTagFilter(['partition+arm+restore']).match(event) is True
    assert EventTagFilter(['partition']).match(event) is True
    assert EventTagFilter(['arm']).match(event) is True
    assert EventTagFilter(['arm-zone']).match(event) is True
    assert EventTagFilter(['arm-partition']).match(event) is False
    assert EventTagFilter(['arm-zone+restore+partition']).match(event) is True
    assert EventTagFilter(['zone']).match(event) is False
    assert EventTagFilter(['zone', 'arm']).match(event) is True

    assert EventTagFilter(['partition,arm']).match(event) is True
    assert EventTagFilter(['partition, arm']).match(event) is True
    assert EventTagFilter(['partition, -arm']).match(event) is False

    event.level = EventLevel.DEBUG
    assert EventTagFilter(['partition+arm']).match(event) is False


def test_zone_generated_alarm_match(mocker):
    label_provider = mocker.MagicMock(return_value="Beer")

    payload = binascii.unhexlify('e2ff1cc414130b010f2c1801030000000000024f66666963652020202020202020202000d9')
    raw = LiveEventMessage.parse(payload)
    event_ = LiveEvent(raw, event_map, label_provider=label_provider)
    assert "Zone Office in alarm" == event_.message

    assert EventTagFilter(['zone+alarm']).match(event_) is True
    label_provider.assert_called_once_with("zone", 3)

    assert EventTagFilter(['zone-alarm']).match(event_) is False

    # Live event label
    assert EventTagFilter(['zone,alarm,"Office"']).match(event_) is True
    assert EventTagFilter(['zone,alarm,-"Office"']).match(event_) is False
    assert EventTagFilter(['zone,alarm,Office']).match(event_) is True
    assert EventTagFilter(['zone,alarm,-Office']).match(event_) is False
    assert EventTagFilter(['zone,alarm,Offic']).match(event_) is False

    # returned from label_provider
    assert EventTagFilter(['zone,alarm,Beer']).match(event_) is True
    assert EventTagFilter(['zone,alarm,-Beer']).match(event_) is False