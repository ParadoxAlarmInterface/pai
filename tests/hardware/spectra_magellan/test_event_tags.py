from pprint import pprint

from paradox.hardware.spectra_magellan.event import event_map
from paradox.lib.event_filter import EventTagFilter
from paradox.hardware.spectra_magellan import parsers
from paradox.event import LiveEvent

def event_iterator():
    for major, config in event_map.items():
        payload = b'\xe2\x14\x13\x01\x04\x0b\n\x02\x0c\x00\x00\x00\x00\x00\x02XXXXXXXXXXX     \x01\x00\x00\x00\x00\x9c'

        event = parsers.LiveEvent.parse(payload)
        raw = event.fields.value

        raw.event.major = major
        if 'sub' in config:
            for minor, minor_conf in config['sub'].items():
                raw.event.minor = minor
                yield LiveEvent(event, event_map)
        else:
            raw.event.minor = 0
            yield LiveEvent(event, event_map)

def test_alarm():
    event_filter = EventTagFilter(['alarm,-restore'])

    matches = []
    for event in event_iterator():
        if event_filter.match(event):
            print(event.message)
            matches.append(event.message)

    pprint(matches)

    assert 'Zone XXXXXXXXXXX in alarm' in matches
    assert 'Zone XXXXXXXXXXX in fire alarm' in matches

    assert 'Alarm cancelled by user XXXXXXXXXXX' in matches
    assert 'Alarm cancelled through WinLoad' in matches

    assert 'Special alarm: Panic medical' in matches

def test_arm():
    event_filter = EventTagFilter(['arm'])

    matches = []
    for event in event_iterator():
        if event_filter.match(event):
            matches.append(event.message)

    pprint(matches)

    assert 'Arming by user XXXXXXXXXXX' in matches

    assert 'Special arming: No movement arming' in matches

def test_disarm():
    event_filter = EventTagFilter(['disarm'])

    matches = []
    for event in event_iterator():
        if event_filter.match(event):
            matches.append(event.message)

    pprint(matches)

    assert 'Disarm partition [partition:1]' in matches
    assert 'Disarming by user XXXXXXXXXXX' in matches

    assert 'Disarming after alarm by user XXXXXXXXXXX' in matches
    assert 'Disarming through WinLoad' in matches
    assert 'Disarming through WinLoad after alarm' in matches

def test_disarm_after_alarm():
    event_filter = EventTagFilter(['disarm+after_alarm'])

    matches = []
    for event in event_iterator():
        if event_filter.match(event):
            matches.append(event.message)

    pprint(matches)

    assert 'Disarming after alarm by user XXXXXXXXXXX' in matches
    assert 'Disarming through WinLoad after alarm' in matches