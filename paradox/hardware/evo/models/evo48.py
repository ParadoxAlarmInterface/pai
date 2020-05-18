from ..panel import Panel_EVOBase


class Panel_EVO48(Panel_EVOBase):
    mem_map = {
        "labels": {
            "zone": {
                "label_offset": 0,
                "addresses": [range(0x00430, 0x00730, 0x10)],  # EVO48
            },
            "pgm": {
                "label_offset": 0,
                "addresses": [range(0x07082, 0x7482, 0x20)],
                "template": {"on": False, "pulse": False},
            },
            "partition": {
                "label_offset": 0,
                "addresses": [range(0x03A6B, 0x03C17, 0x6B)],  # EVO48
            },
            "user": {"label_offset": 0, "addresses": [range(0x03E47, 0x04447, 0x10)]},
            "module": {  # modules
                "label_offset": 0,
                "addresses": [range(0x04E47, 0x05637, 0x10)],  # EVO48
            },
            "door": {"label_offset": 0, "addresses": [range(0x0345C, 0x365C, 0x10)]},
        },
        "definitions": {
            "zone": {"addresses": [range(0x01F0, 0x024E + 2, 2)]},  # EVO48
            "partition": {
                "bit_encoded": True,
                "addresses": [[0x39D8]],  # All 8 partitions as bits
            },
            "user": {"addresses": [range(0x0BF0, 0x0FA6 + 10, 10),]},  # 96 users
        },
    }
