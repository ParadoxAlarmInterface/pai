from binascii import hexlify, unhexlify
from paradox.hardware.evo.parsers import PerformPartitionAction

def test_create_action():
    commands = {
        8: "arm"
    }

    a = PerformPartitionAction.build({
        "fields": {
            "value": {
                "commands": commands
            }
        }
    })

    print(hexlify(a))

    assert a == unhexlify(b'400f00000000000000020000000051')

    assert len(a) == 15