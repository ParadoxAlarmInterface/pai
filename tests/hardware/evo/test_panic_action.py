from paradox.hardware.evo.parsers import SendPanicAction


def test_send_panic_size():
    assert SendPanicAction.sizeof() == 11
