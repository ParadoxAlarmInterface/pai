"""Adapters that turn Digiplex RAM bytes into ``convert_raw_status()`` values."""

import logging

from construct import Adapter

logger = logging.getLogger("PAI").getChild(__name__)


def _as_int(obj) -> int:
    """Bytes(1) delivers b"\\x..", Byte delivers int - accept both."""
    return obj[0] if isinstance(obj, (bytes, bytearray)) else int(obj)


class StatusAdapter(Adapter):
    """N bytes -> {index: bool}. Bit 0 (LSB) of the first byte is index 1."""

    def _decode(self, obj, context, path):
        r = dict()
        for i in range(0, len(obj)):
            status = obj[i]
            for j in range(0, 8):
                r[i * 8 + j + 1] = ((status >> j) & 0x01) == 0x01

        return r


# Calibrated 2026-10-25 against a multimeter (see VoltageAdapter docstring):
#   battery 13.68 V   -> raw 0x53 (83)   => 0.16482 V/step
#   PSU     13.66 V   -> raw 0xF2 (242)  => 0.05645 V/step
AC_V_PER_STEP = 0.16482
PSU_V_PER_STEP = 0.05645
BATTERY_V_PER_STEP = 0.16482


class VoltageAdapter(Adapter):
    """Raw byte -> volts, using a per-register scale.

    Calibrated 2026-10-25 against a multimeter on this installation:

        battery terminals 13.68 V -> raw 83   => 0.16482 V/step
        PSU / AUX output  13.66 V -> raw 242  => 0.05645 V/step
        AC input          17.5 VAC (rectified ~23 V) -> same ADC scale as
                          the battery (0.16482 V/step), averaged in panel.py

    Before calibration a flat 0.1 V/step was used, which produced the
    impossible pair "PSU 24.2 V / battery 8.3 V".
    """

    def __init__(self, subcon, step: float):
        super().__init__(subcon)
        self.step = step

    def _decode(self, obj, context, path):
        return round(_as_int(obj) * self.step, 2)

    def _encode(self, obj, context, path):
        return int(round(obj / self.step))


# Home Assistant binary_sensor device classes accepted in ZONE_DEVICE_CLASS.
ZONE_DEVICE_CLASSES = (
    "motion",
    "door",
    "window",
    "garage_door",
    "smoke",
    "vibration",
    "tamper",
    "gas",
    "moisture",
    "occupancy",
    "opening",
    "safety",
    "problem",
)
DEFAULT_ZONE_DEVICE_CLASS = "motion"


def zone_device_class(zone_key: str, mapping: dict | None = None) -> str:
    """Zone key -> Home Assistant binary_sensor device_class.

    The panel does not expose the physical sensor type: zone definitions only
    describe behaviour (instant, entry delay, 24h fire, ...), not whether a
    zone is a PIR, a contact or a glass-break detector. The mapping therefore
    comes from the ``ZONE_DEVICE_CLASS`` configuration option (zone key ->
    device_class) and never from the label text, so it works the same for a
    panel programmed in any language. Unlisted zones default to "motion".
    """
    device_class = (mapping or {}).get(zone_key, DEFAULT_ZONE_DEVICE_CLASS)
    if device_class not in ZONE_DEVICE_CLASSES:
        logger.warning(
            "Ignoring unknown device_class %r for zone %r, using %r",
            device_class,
            zone_key,
            DEFAULT_ZONE_DEVICE_CLASS,
        )
        return DEFAULT_ZONE_DEVICE_CLASS

    return device_class


# Only these zone types physically have a tamper switch on this installation:
# motion (PIR) and glass-break detectors, plus the siren/cabinet tamper zone.
# Window/door contacts, garage-door contacts and the fire detector do not,
# so publishing tamper entities for them would only add noise.
TAMPER_DEVICE_CLASSES = ("motion", "vibration", "tamper")


def publishes_tamper(device_class: str) -> bool:
    """Should this zone type expose a tamper binary sensor?"""
    return device_class in TAMPER_DEVICE_CLASSES


# Partition status: four partitions in 5-byte blocks starting at RAM 0x0195.
# Layout cross-checked against adumat/paradox-dgp-mqtt (2026-08) and against
# our own captures:
#
#   block +0 (arm/alarm flags):
#       bit0 armed, bit1 force arm, bit2 stay arm, bit3 no entry,
#       bit4 strobe alarm, bit5 silent alarm, bit6 audible alarm
#   block +1 (status flags):
#       bit0 ready, bit1 exit delay, bit2 entry delay,
#       bit3 partition enabled, bit4 alarm in memory
#
# Measured on our panel:
#   armed full    0x0195 = 0x01   (armed)
#   armed partial 0x0195 = 0x05   (armed + stay)  -> partial arm (stay)
#   garage armed  0x019A = 0x01   (armed)
#   0x0196 goes 1 -> 3 -> 1 during the 20 s exit delay (bit1).
#
# Only two partitions are used here: 1 = house, 2 = garage.
BLOCK_BASE = 0x0185
PARTITION_BASE = 0x0195
PARTITION_OFFSET = PARTITION_BASE - BLOCK_BASE  # 16
PARTITION_STRIDE = 5
PARTITION_COUNT = 2


class PartitionStatusAdapter(Adapter):
    """32 byte block starting at 0x0185 -> partition properties."""

    def _decode(self, obj, context, path):
        def partition(index: int) -> dict:
            offset = PARTITION_OFFSET + index * PARTITION_STRIDE
            arm = _as_int(obj[offset : offset + 1])
            status = _as_int(obj[offset + 1 : offset + 2])
            return dict(
                arm=bool(arm & 0x01),
                arm_stay=bool(arm & 0x04),
                audible_alarm=bool(arm & 0x40),
                silent_alarm=bool(arm & 0x20),
                exit_delay=bool(status & 0x02),
                entry_delay=bool(status & 0x04),
            )

        return {index + 1: partition(index) for index in range(PARTITION_COUNT)}
