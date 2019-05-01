from ..panel import Panel_EVOBase


class Panel_EVO48(Panel_EVOBase):
    mem_map = {
        "elements": {
            "zone": {
                "label_offset": 0,
                "addresses": [
                    range(0x00430, 0x00730, 0x10),  # EVO48
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
                ]
            },
            "user": {
                "label_offset": 0,
                "addresses": [range(0x03e47, 0x04447, 0x10)]
            },
            "bus-module": {  # modules
                "label_offset": 0,
                "addresses": [
                    range(0x04e47, 0x05637, 0x10),  # EVO48
                ]
            },
            "door": {
                "label_offset": 0,
                "addresses": [range(0x0345c, 0x365c, 0x10)]
            }
        }
    }
