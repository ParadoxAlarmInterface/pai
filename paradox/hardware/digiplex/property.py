"""Digiplex RAM block parsers and property -> event mapping.

``RAMDataParserMap`` is keyed by the RAM address (``address | 0x8000``) and
returns the flat status dict consumed by ``convert_raw_status()``:

    {"zone_open": {1: bool, ...}, "partition_status": {1: {...}}, "system": {...}}

Memory map (verified live on a DGP-848, firmware build A095):
    0x0153..0x0158  zone status 1-48 (bit0=LSB=zone 1, 1=open)
    0x0159..0x015E  tamper status 1-48
    0x0195..        partition status, 5-byte blocks (see adapters.py)
    0x000C          PSU voltage
    0x000D          battery voltage
"""

from construct import Bytes, Padding, Struct

from paradox.event import EventLevel

from .adapters import (
    BATTERY_V_PER_STEP,
    PSU_V_PER_STEP,
    PartitionStatusAdapter,
    StatusAdapter,
    VoltageAdapter,
)

RAMDataParserMap = {
    0x8153: Struct(
        "zone_open" / StatusAdapter(Bytes(6)),
        "zone_tamper" / StatusAdapter(Bytes(6)),
        Padding(20),
    ),
    0x8185: Struct(
        # 0x0185..0x01A4: partition status blocks start at 0x0195
        "partition_status"
        / PartitionStatusAdapter(Bytes(32)),
    ),
    0x800B: Struct(
        Padding(1),  # 0x000B: unfiltered AC sample - intentionally unpublished
        "system"
        / Struct(
            "power"
            / Struct(
                "psu" / VoltageAdapter(Bytes(1), PSU_V_PER_STEP),  # 0x000C
                "battery" / VoltageAdapter(Bytes(1), BATTERY_V_PER_STEP),  # 0x000D
            )
        ),
        Padding(29),
    ),
}

# Property changes -> synthesized events (see paradox.event.ChangeEvent).
property_map = {
    "open": dict(
        level=EventLevel.INFO,
        message={
            "True": "{Type} {label} is open",
            "False": "{Type} {label} is closed",
        },
    ),
    "tamper": dict(
        level=EventLevel.CRITICAL,
        tags=["trouble"],
        message={
            "True": "{Type} {label} tamper",
            "False": "{Type} {label} tamper restored",
        },
    ),
    "arm": dict(
        level=EventLevel.CRITICAL,
        message={
            "True": "{Type} {label} is armed",
            "False": "{Type} {label} is disarmed",
        },
    ),
    "audible_alarm": dict(
        level=EventLevel.CRITICAL,
        message={
            "True": "{Type} {label} in alarm",
            "False": "{Type} {label} alarm stopped",
        },
    ),
}
