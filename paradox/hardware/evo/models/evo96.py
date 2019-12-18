from ..panel import Panel_EVOBase


class Panel_EVO96(Panel_EVOBase):
    mem_map = {
        "labels": {
            "zone": {
                "label_offset": 0,
                "addresses": [
                    range(0x00430, 0x00730, 0x10),  # EVO48
                    range(0x00730, 0x00a30, 0x10)  # EVO96 = EVO48 + 48 zones
                ]
            },
            "pgm": {
                "label_offset": 0,
                "addresses": [range(0x07082, 0x7482, 0x20)],
                "template": {
                    "on": False,
                    "pulse": False
                }
            },
            "partition": {
                "label_offset": 0,
                "addresses": [
                    range(0x03a6b, 0x03c17, 0x6b),  # EVO48
                    range(0x03c17, 0x03dc3,
                          0x6b)  # EVO96 & EVO192 = EVO48 + 4 partitions
                ]
            },
            "user": {
                "label_offset": 0,
                "addresses": [range(0x03e47, 0x04e47, 0x10)]
            },
            "bus-module": {  # modules
                "label_offset": 0,
                "addresses": [
                    range(0x04e47, 0x05637, 0x10),  # EVO48
                    range(0x05637, 0x05e27,
                          0x10)  # EVO96 & EVO192 = EVO48 + 127 modules
                ]
            },
            "door": {
                "label_offset": 0,
                "addresses": [range(0x0345c, 0x365c, 0x10)]
            }
        },
        "definitions": {
            "zone": {
                "addresses": [
                    range(0x01f0, 0x02ae + 2, 2)  # EVO96
                ]
            },
            "partition": {
                "bit_encoded": True,
                "addresses": [
                    [0x39d8]  # All 8 partitions as bits
                ]
            }
        }
    }
