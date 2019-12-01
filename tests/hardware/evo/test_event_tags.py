from pprint import pprint

from paradox.hardware.evo.event import event_map
from paradox.lib.event_filter import EventTagFilter
from paradox.hardware.evo import parsers
from paradox.event import LiveEvent

def event_iterator():
    for major, config in event_map.items():
        payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc'

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
            matches.append(event.message)

    pprint(matches)

    assert 'Zone Living room in alarm' in matches
    assert 'Zone Living room in fire alarm' in matches

    assert 'Alarm cancelled by Living room (master)' in matches
    assert 'Alarm cancelled by Living room (user code)' in matches

    assert 'Special alarm: Panic emergency' in matches
    assert 'Special alarm: Module tamper alarm' in matches

def test_arm():
    event_filter = EventTagFilter(['arm'])

    matches = []
    for event in event_iterator():
        if event_filter.match(event):
            matches.append(event.message)

    pprint(matches)

    assert 'Arming [partition:1] with master code' in matches

    assert 'Special arming [partition:1]: auto arming' in matches

def test_disarm():
    event_filter = EventTagFilter(['disarm'])

    matches = []
    for event in event_iterator():
        if event_filter.match(event):
            matches.append(event.message)

    pprint(matches)

    assert '[partition:1] disarmed with master' in matches
    assert '[partition:1] disarmed with user code' in matches
    assert '[partition:1] disarmed with keyswitch' in matches

    assert '[partition:1] disarmed after alarm with master' in matches
    assert '[partition:1] special disarming: Disarming with Winload after alarm by [user:0]' in matches

def test_disarm_after_alarm():
    event_filter = EventTagFilter(['disarm+after_alarm'])

    matches = []
    for event in event_iterator():
        if event_filter.match(event):
            matches.append(event.message)

    pprint(matches)

    assert '[partition:1] disarmed after alarm with master' in matches
    assert '[partition:1] special disarming: Disarming with Winload after alarm by [user:0]' in matches