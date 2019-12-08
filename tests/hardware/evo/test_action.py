from binascii import hexlify, unhexlify
from paradox.hardware.evo.parsers import PerformPartitionAction, PerformZoneAction, PerformZoneActionResponse

def test_partition_action():
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

def test_zone_bypass_zone_5():
    expected = b'd01f080800001000000000000000000000000000000000000000000000000f'

    a = PerformZoneAction.build({
        "fields": {
            "value": {
                "flags": {
                    "bypassed": True
                },
                "operation": "set",
                "zones": [5]
            }
        }
    })

    assert hexlify(a) == expected

def test_zone_bypass_zone_3():
    expected = b'd01f0808000004000000000000000000000000000000000000000000000003'

    a = PerformZoneAction.build({
        "fields": {
            "value": {
                "flags": {
                    "bypassed": True
                },
                "operation": "set",
                "zones": [3]
            }
        }
    })

    assert hexlify(a) == expected

def test_zone_bypass_response():
    payload = unhexlify('d20708080000e9')

    a = PerformZoneActionResponse.parse(payload)

    assert a["fields"]["value"]["flags"]["bypassed"] == True
    assert a["fields"]["value"]["operation"] == "set"

def test_zone_clear_alarm_memory_zone_5():
    expected = b'd01f800000001000000000000000000000000000000000000000000000007f'

    a = PerformZoneAction.build({
        "fields": {
            "value": {
                "flags": {
                    "generated_alarm": True
                },
                "operation": "clear",
                "zones": [5]
            }
        }
    })

    assert hexlify(a) == expected

def test_zone_clear_alarm_memory_response():
    payload = unhexlify('d2078000000059')

    a = PerformZoneActionResponse.parse(payload)

    assert a["fields"]["value"]["flags"]["generated_alarm"] == True
    assert a["fields"]["value"]["operation"] == "clear"

def test_zone_bypass_clear_zone_5():
    expected = b'd01f0800000010000000000000000000000000000000000000000000000007'

    a = PerformZoneAction.build({
        "fields": {
            "value": {
                "flags": {
                    "bypassed": True
                },
                "operation": "clear",
                "zones": [5]
            }
        }
    })

    assert hexlify(a) == expected

def test_zone_bypass_clear_response():
    payload = unhexlify(b'd20708000000e1')

    a = PerformZoneActionResponse.parse(payload)

    assert a["fields"]["value"]["flags"]["bypassed"] == True
    assert a["fields"]["value"]["operation"] == "clear"