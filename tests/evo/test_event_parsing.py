import binascii
from paradox.hardware.evo.parsers import LiveEvent
from paradox.hardware.evo.event import event_map
from paradox.event import Event

def label_provider(type, id):
    if type == 'user':
        assert id == 1
        return 'Test'
    elif type == 'partition':
        assert id == 5
        return 'First floor'
    elif type == 'door':
        assert id == 5
        return 'Door 1'
    else:
        assert False

def test_zone_ok():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc'

    raw = LiveEvent.parse(payload)

    # monkey patch
    event_map[0]['message'] = 'Zone {label} OK in partition {@partition}'

    event = Event(event_map, raw, label_provider=label_provider)

    assert event.change == {'open': False}

    assert "Zone Living room OK in partition First floor" == event.message
    print(event)

def test_door_user():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x06\x01\x05\x01\x00\x00\x00\x00\x02Living room     \x00\xd3'

    raw = LiveEvent.parse(payload)

    # monkey patch
    event_map[6]['message'] = 'User {@user} access on door {@door}'

    event = Event(event_map, raw, label_provider=label_provider)

    assert "User Test access on door Door 1" == event.message
    print(event)

def test_zone_open():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x01\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcd'

    raw = LiveEvent.parse(payload)
    event = Event(event_map, raw, label_provider=label_provider)

    assert event.change == {'open': True}
    assert "Zone Living room open" == event.message
    print(event)

def test_event_winload_connected():
    payload = b'\xe2\xff\xaa\xb0\x14\x13\x01\x04\x0b$-\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc7'

    raw = LiveEvent.parse(payload)
    event = Event(event_map, raw)
    assert "Special events: WinLoad in (connected)" == event.message
    print(event)

def test_event_clock_restore():
    payload = b'\xe2\xff\xaa\xb1\x14\x13\x01\x04\x0b$%\x00\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc2'

    raw = LiveEvent.parse(payload)
    event = Event(event_map, raw)
    assert "Trouble restore: Clock loss restore" == event.message
    print(event)