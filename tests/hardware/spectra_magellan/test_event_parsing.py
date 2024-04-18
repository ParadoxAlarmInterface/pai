import binascii
import typing

import pytest

from paradox import event
from paradox.hardware.spectra_magellan.event import event_map
from paradox.hardware.spectra_magellan.parsers import LiveEvent

events = [
    (
        b"e2141301040b08300200000000000000000000000000000000000000000000020000000055"
    ),  # Software Log on
    (
        b"e2141301040b042d0600000000000000000000000000000000000000000000010000000051"
    ),  # Clock loss restore
    (b"e2141301040b09030300000000000000000000000000000000000000000000000000000028"),
    # {'type': 'Bell', 'minor': (3, ' Bell squawk disarm'), 'major': (3, 'Bell status (Partition 1)')}
    (b"e2141301040b09220100000000000000000000000000000000000000000000010000000046"),
    # {'type': 'Special', 'minor': (1, 'Disarming through WinLoad'), 'major': (34, 'Special disarming')}
    (b"e2141301040b09030300000000000000000000000000000000000000000000000000000028"),
    # {'type': 'Bell', 'minor': (3, ' Bell squawk disarm'), 'major': (3, 'Bell status (Partition 1)')}
    (b"e2141301040b09220101000000000000000000000000000000000000000000010000000047"),
    # {'type': 'Special', 'minor': (1, 'Disarming through WinLoad'), 'major': (34, 'Special disarming')}
    (b"e2141301040b09030200000000000000000000000000000000000000000000010000000028"),
    # {'type': 'Bell', 'minor': (2, ' Bell squawk arm'), 'major': (3, 'Bell status (Partition 1)')}
    (b"e2141301040b0a1e0500000000000000000000000000000000000000000000010000000047"),
    # {'type': 'Special', 'minor': (5, 'Arming through WinLoad'), 'major': (30, 'Special arming')}
    (b"e2141301040b0b1e0501000000000000000000000000000000000000000000010000000049"),
    # {'type': 'Special', 'minor': (5, 'Arming through WinLoad'), 'major': (30, 'Special arming')}
    (b"e214120b15110e061b00000000000000000000000000000000000000000000000000000068"),
    (b"e2141301040b09020b0100000000025858585858585858585858202020202001000000009b"),
    # {'type': 'Partition', 'minor': (11, 'Disarm partition'), 'major': (2, 'Partition status')}
    (b"e2141301040b09020800000000000258585858585858585858582020202020000000000096"),
    # {'type': 'Partition', 'minor': (8, 'Squawk ON (Partition 1)'), 'major': (2, 'Partition status')}
    (b"e2141301040b09020900000000000258585858585858585858582020202020000000000097"),
    # {'type': 'Partition', 'minor': (9, 'Squawk OFF (Partition 1)'), 'major': (2, 'Partition status')}
    (b"e2141301040b09020800000000000258585858585858585858582020202020000000000096"),
    # {'type': 'Partition', 'minor': (8, 'Squawk ON (Partition 1)'), 'major': (2, 'Partition status')}
    (b"e2141301040b09020e0000000000025858585858585858585858202020202001000000009d"),
    # {'type': 'Partition', 'minor': (14, 'Exit delay started'), 'major': (2, 'Partition status')}
    (b"e2141301040b0b020c0100000000025858585858585858585858202020202001000000009e"),
    # { 'type': 'Partition', 'minor': (12, 'Arm partition'), 'major': (2, 'Partition status')}
    (b"e2141301040b09020e0100000000025858585858585858585858202020202001000000009e"),
    # {'type': 'Partition', 'minor': (8, 'Squawk ON (Partition 1)'), 'major': (2, 'Partition status')}
    (b"e2141301040b09020900000000000258585858585858585858582020202020010000000098"),
    # {'type': 'Partition', 'minor': (9, 'Squawk OFF (Partition 1)'), 'major': (2, 'Partition status')}
    (b"e2141301040b0a020c0000000000025858585858585858585858202020202001000000009c"),
    # {'type': 'Partition', 'minor': (12, 'Arm partition'), 'major': (2, 'Partition status')}
    (b"e2141301040b09020b0000000000025858585858585858585858202020202001000000009a"),
    # {'type': 'Partition', 'minor': (11, 'Disarm partition'), 'major': (2, 'Partition status')}
]


@pytest.mark.parametrize("hex", events)
def test_event_parsing(hex):
    payload = binascii.unhexlify(hex)

    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)

    print(event_)


def test_disarm_partition0():
    hex = b"e2141301040b09020b0100000000025858585858585858585858202020202001000000009b"  # {'type': 'Partition', 'minor': (11, 'Disarm partition'), 'major': (2, 'Partition status')}
    payload = binascii.unhexlify(hex)

    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map)

    assert event_.message == "Partition [partition:2] disarmed"
    print(event_)


def test_disarm_partition1(mocker):
    hex = b"e2141301040b09020b0100000000025858585858585858585858202020202001000000009b"  # {'type': 'Partition', 'minor': (11, 'Disarm partition'), 'major': (2, 'Partition status')}
    payload = binascii.unhexlify(hex)

    mocker.patch.dict(event_map[2]["sub"][11], {"message": "Disarm partition {name}"})

    def label_provider(type, id):
        assert type == "partition"
        assert id == 2
        return "Partition 2"

    raw = LiveEvent.parse(payload)
    event_ = event.LiveEvent(raw, event_map, label_provider)

    print(event_)

    assert event_.message == "Disarm partition Partition 2"


def test_button_pressed():
    event_ = (
        b"e214130a14103708040000000000000000000000000000000000000000000000000000007a"
    )
    payload = binascii.unhexlify(event_)

    raw = LiveEvent.parse(payload)

    def label_provider(type, id):
        print(type, id)
        if type == "user":
            assert id == 4
            return "UserA"

    event_ = event.LiveEvent(raw, event_map, label_provider=label_provider)

    print(event_)
    assert isinstance(event_.change.get("button_b", None), typing.Callable)

    assert "Button B pressed on remote of UserA" == event_.message
