from paradox.hardware.spectra_magellan.parsers import SendPanicAction

def test_panic_action():
    assert SendPanicAction.sizeof() == 37

    raw = SendPanicAction.build({"fields":{"value":{"user_id":1, "partition":1, "panic_type": "medical"}}})

    print(raw)

    assert raw[0] == 64
    assert raw[1] == 37
    assert raw[2] == 26
    assert raw[3] == 1
    assert raw[4] == 1
    assert raw[5] == 1
    assert raw[32] == 6
    assert raw[34] == 1
    assert raw[35] == 0