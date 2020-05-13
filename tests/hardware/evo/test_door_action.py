from paradox.hardware.evo.parsers import PerformDoorAction

def test_send_door_action():
    assert PerformDoorAction.sizeof() == 17

    raw = PerformDoorAction.build({"fields":{"value":{"doors":[1], "user_id": 3, "command": "unlock"}}})

    assert raw[0] == 64
    assert raw[1] == 17
    assert raw[2] == 2
    assert raw[6] == 1
    assert raw[10] == 2
    assert raw[13] == 85
    assert raw[14] == 3
    assert raw[15] == 0