from binascii import unhexlify, hexlify

from paradox.hardware.evo.parsers import PerformPGMAction


def test_pgm3_activate():
    expected_out = unhexlify('40130600000004000000000000000300000060')

    pgms = [3]

    a = PerformPGMAction.build({
        "fields": {
            "value": {
                "pgms": pgms,
                "command": "activate"
            }
        }
    })

    assert a == expected_out

def test_pgm3_deactivate():
    expected_out = unhexlify('4013060000000400000000000000010000005e')

    pgms = [3]

    a = PerformPGMAction.build({
        "fields": {
            "value": {
                "pgms": pgms,
                "command": "deactivate"
            }
        }
    })

    assert a == expected_out

def test_pgm4_activate():
    expected_out = unhexlify('40130600000008000000000000000300000064')

    pgms = [4]

    a = PerformPGMAction.build({
        "fields": {
            "value": {
                "pgms": pgms,
                "command": "activate"
            }
        }
    })

    assert a == expected_out

def test_pgm4_deactivate():
    expected_out = unhexlify('40130600000008000000000000000100000062')

    pgms = [4]

    a = PerformPGMAction.build({
        "fields": {
            "value": {
                "pgms": pgms,
                "command": "deactivate"
            }
        }
    })

    assert a == expected_out

def test_pgm_confirmation():
    payload = unhexlify('42070000000049')