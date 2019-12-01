import binascii

from paradox.hardware.evo.parsers import LiveEvent, RequestedEvent
from paradox.hardware.evo.event import event_map
from paradox import event

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

    def label_provider(type, id):
        assert type == 'partition'
        assert id == 1
        return 'First floor'

    # monkey patch
    event_map[0]['message'] = 'Zone {label} OK in partition {@partition}'

    event_ = event.LiveEvent(raw, event_map, label_provider=label_provider)

    assert event_.change == {'open': False}

    assert "Zone Living room OK in partition First floor" == event_.message
    print(event_)

def test_door_user():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x06\x01\x05\x01\x00\x00\x00\x00\x02Living room     \x00\xd3'

    raw = LiveEvent.parse(payload)

    # monkey patch
    event_map[6]['message'] = 'User {@user} access on door {@door}'

    event_ = event.LiveEvent(raw, event_map, label_provider=label_provider)

    assert "User Test access on door Door 1" == event_.message
    print(event_)

def test_door_user2():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x06\x01\x05\x01\x00\x00\x00\x00\x02Living room     \x00\xd3'

    raw = LiveEvent.parse(payload)

    def label_provider(type, id):
        if type == 'user':
            assert id == 5
            return 'Test'
        elif type == 'partition':
            assert id == 5
            return 'First floor'
        elif type == 'door':
            assert id == 5
            return 'Door 1'
        else:
            assert False

    # monkey patch
    event_map[6]['message'] = 'User {@user#minor} access on door {@door}'

    event_ = event.LiveEvent(raw, event_map, label_provider=label_provider)

    assert "User Test access on door Door 1" == event_.message
    print(event_)

def test_zone_open():
    payload = b'\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x01\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcd'

    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map, label_provider=label_provider)

    assert event_.change == {'open': True}
    assert "Zone Living room open" == event_.message
    print(event_)

def test_event_winload_connected():
    payload = b'\xe2\xff\xaa\xb0\x14\x13\x01\x04\x0b$-\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc7'

    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)
    assert "Special events: WinLoad in (connected)" == event_.message
    print(event_)

def test_event_clock_restore():
    payload = b'\xe2\xff\xaa\xb1\x14\x13\x01\x04\x0b$%\x00\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc2'

    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)
    print(event_)

    assert "Trouble restore: Clock loss restore" == event_.message
    assert all(t in event_.tags for t in ['trouble', 'clock'])

def test_disconnect_event():
    payload = b'\xe0\xff\xe1\xe8\x14\x13\x02\x11\x0f%-\x00\x05\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00H'

    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)
    assert "Special events: WinLoad out (disconnected)" == event_.message
    print(event_)

def test_requested_event():
    payload = binascii.unhexlify('e243000009fa79942713a500060000000000819426000400090000000000819426ab8500010000000000819426ab8920010000000000819426ab8910010000000000de')
    raw = RequestedEvent.parse(payload)
    values = raw.fields.value
    assert values.po.command == 0xe and (not hasattr(values, "event_source") or values.event_source == 0xff)
    print(raw)

def test_zone_generated_alarm():
    payload = binascii.unhexlify('e2ff1cc414130b010f2c1801030000000000024f66666963652020202020202020202000d9')
    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)
    assert "Zone Office in alarm" == event_.message
    print(event_)

def test_zone_alarm_restored():
    payload = binascii.unhexlify('e2ff1cd914130b010f2f1a0102000000000002456e7472616e636520202020202020200096')
    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)
    assert "Zone Entrance alarm restore" == event_.message
    print(event_)

def test_partition_armed_by_pai():
    payload = binascii.unhexlify('e2ff187914130b0e0e3b0c0101000000000000000000000000000000000000000000000009')
    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)
    assert "Special arming: [partition:1] arming with Winload by [user:0]" == event_.message
    print(event_)



def test_c2():
    payload = binascii.unhexlify('c2001903000b00000001a96c7106152c00200132010000000b')

def test_8207000005fa88():
    payload = binascii.unhexlify('8207000005fa88')