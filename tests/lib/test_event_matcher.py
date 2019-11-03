from paradox.lib.event_matcher import tag_match
from paradox.event import Event


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