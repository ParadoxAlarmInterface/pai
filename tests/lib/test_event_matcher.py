import binascii

from paradox.event import Event, LiveEvent
from paradox.hardware.evo.event import event_map
from paradox.hardware.evo.parsers import LiveEvent as LiveEventMessage
from paradox.lib.event_matcher import tag_match


def test_tag_match():
    event = Event()
    event.tags = ['arm', 'restore']
    event.type = 'partition'

    assert tag_match(event, ['partition+arm']) is True
    assert tag_match(event, ['partition+arm+restore']) is True
    assert tag_match(event, ['partition']) is True
    assert tag_match(event, ['arm']) is True
    assert tag_match(event, ['arm-zone']) is True
    assert tag_match(event, ['arm-partition']) is False
    assert tag_match(event, ['arm-zone+restore+partition']) is True
    assert tag_match(event, ['zone']) is False
    assert tag_match(event, ['zone','arm']) is True

    assert tag_match(event, ['partition,arm']) is True
    assert tag_match(event, ['partition, arm']) is True
    assert tag_match(event, ['partition, -arm']) is False


def test_zone_generated_alarm_match(mocker):
    label_provider = mocker.MagicMock(return_value="Beer")

    payload = binascii.unhexlify('e2ff1cc414130b010f2c1801030000000000024f66666963652020202020202020202000d9')
    raw = LiveEventMessage.parse(payload)
    event_ = LiveEvent(raw, event_map, label_provider=label_provider)
    assert "Zone Office in alarm" == event_.message

    assert tag_match(event_, ['zone+alarm']) is True
    label_provider.assert_called_once_with("zone", 3)

    assert tag_match(event_, ['zone-alarm']) is False

    # Live event label
    assert tag_match(event_, ['zone,alarm,"Office"']) is True
    assert tag_match(event_, ['zone,alarm,Office']) is True
    assert tag_match(event_, ['zone,alarm,-Office']) is False
    assert tag_match(event_, ['zone,alarm,Offic']) is False

    # returned from label_provider
    assert tag_match(event_, ['zone,alarm,Beer']) is True
    assert tag_match(event_, ['zone,alarm,-Beer']) is False