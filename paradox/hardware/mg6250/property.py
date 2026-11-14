from paradox.event import EventLevel

from ..spectra_magellan.property import property_map as spectra_magellan_property_map

# The same property names as SP/MG, plus what only this panel publishes. The
# alarm properties stay at debug level: event 47 "Zone in alarm" from the log is
# the critical one, and both would notify for one alarm.
property_map = {
    **spectra_magellan_property_map,
    "ac": dict(level=EventLevel.DEBUG, message="AC voltage is {value}V"),
    "arm_away": dict(
        level=EventLevel.DEBUG,
        message={
            "True": "{Type} {label} full arm is active",
            "False": "{Type} {label} full arm is inactive",
        },
    ),
    "generated_alarm": dict(
        level=EventLevel.DEBUG,
        message={
            "True": "Zone {label} has an alarm in memory",
            "False": "Zone {label} alarm memory cleared",
        },
    ),
    "presently_in_alarm": dict(
        level=EventLevel.DEBUG,
        message={
            "True": "Zone {label} presently in alarm",
            "False": "Zone {label} no longer in alarm",
        },
    ),
    "target_state": dict(
        level=EventLevel.DEBUG, message="{Type} {label} target state is {value}"
    ),
}
