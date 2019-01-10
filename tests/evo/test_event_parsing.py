import binascii
from paradox.hardware.evo.parsers import LiveEvent
from paradox.hardware.evo.event import event_map
from paradox.event import Event

def test_zone_ok():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc'

    raw = LiveEvent.parse(payload)
    event = Event(event_map, raw, {
        'zone': {
            5: 'Zone 5'
        }
    })

    assert event.change == {'open': False}
    print(event)

def test_zone_open():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x01\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcd'

    raw = LiveEvent.parse(payload)
    event = Event(event_map, raw, {
        'zone': {
            5: 'Zone 5'
        }
    })

    assert event.change == {'open': True}
    print(event)

def test_event_winload_connected():
    payload = b'\xe2\xff\xaa\xb0\x14\x13\x01\x04\x0b$-\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc7'

    raw = LiveEvent.parse(payload)
    event = Event(event_map, raw, {})
    print(event)

def test_event_clock_restore():
    payload = b'\xe2\xff\xaa\xb1\x14\x13\x01\x04\x0b$%\x00\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc2'

    raw = LiveEvent.parse(payload)
    event = Event(event_map, raw, {})
    print(event)