from paradox.hardware.evo.parsers import SendPanicAction


def test_send_panic_size():
    assert SendPanicAction.sizeof() == 11

    partition = 5

    args = {
        "partitions": [partition],
        "panic_type": "fire",
        "user_id": 2
    }

    raw = SendPanicAction.build({"fields":{"value": args}})
    print(list(bytearray(raw)))

    assert raw[0] == 64
    assert raw[1] == 11  # packet length
    assert raw[2] == 9
    assert raw[6] == 0  # user id >> 8
    assert raw[7] == 2  # user id & 255
    assert raw[8] == 2  # panic type fire
    assert raw[9] == 1 << (partition-1)  # partition

