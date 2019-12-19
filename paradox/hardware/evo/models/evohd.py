import logging
from ..panel import Panel_EVOBase

logger = logging.getLogger('PAI').getChild(__name__)


class Panel_EVOHD(Panel_EVOBase):
    mem_map = {
        "labels": {
            "zone": {
                "label_offset": 0, "addresses": [
                    range(0x00430, 0x00730, 0x10),  # EVO48
                    range(0x00730, 0x00a30, 0x10),  # EVO96 = EVO48 + 48 zones
                    range(0x062f7, 0x068f7, 0x10)  # EVO192 = EVO96 + 96 zones
                ]},
            "pgm": {
                "label_offset": 0, "addresses": [range(0x070a6, 0x7486, 0x20)], "template": {  # A bit off from EVO 192
                    "on": False,
                    "pulse": False}
            },
            "partition": {
                "label_offset": 0, "addresses": [
                    range(0x03a6b, 0x03c17, 0x6b),  # EVO48
                    range(0x03c17, 0x03dc3, 0x6b)  # EVO96 & EVO192 = EVO48 + 4 partitions
                ]},
            "user": {
                "label_offset": 0, "addresses": [range(0x03e47, 0x04e47, 0x10)]
            },
            "bus-module": {  # modules
                "label_offset": 0, "addresses": [
                    range(0x04e47, 0x05637, 0x10),  # EVO48
                    range(0x05637, 0x05e27, 0x10)  # EVO96 & EVO192 = EVO48 + 127 modules
                ]
            },
            "door": {
                "label_offset": 0, "addresses": [range(0x0345c, 0x365c, 0x10)]
            }
        }
    }