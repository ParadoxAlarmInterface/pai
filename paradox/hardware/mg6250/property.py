from paradox.event import EventLevel

from ..spectra_magellan.property import property_map as spectra_magellan_property_map


def _trouble(text, level=EventLevel.WARN, tags=()):
    return {
        "level": level,
        "tags": ["trouble", *tags],
        "message": {"True": text, "False": f"{text} restored"},
    }


def _quiet(prop):
    """The SP/MG property, at debug level."""
    return {**spectra_magellan_property_map[prop], "level": EventLevel.DEBUG}


# Troubles the event log already reports with a notified event (55 and its
# sub-events, 57-62 zone tamper, low battery and supervision, the device
# troubles 63-86): the status
# change stays at debug level, or one trouble would notify twice. The others
# have no event and notify from the status.
_LOGGED = EventLevel.DEBUG
_FTC = "Fail to communicate"

# The same property names as SP/MG, plus what only this panel publishes. The
# alarm properties stay at debug level: event 47 "Zone in alarm" from the log is
# the critical one, and both would notify for one alarm.
property_map = {
    **spectra_magellan_property_map,
    "ac": {"level": EventLevel.DEBUG, "message": "AC voltage is {value}V"},
    "arm_away": {
        "level": EventLevel.DEBUG,
        "message": {
            "True": "{Type} {label} full arm is active",
            "False": "{Type} {label} full arm is inactive",
        },
    },
    "generated_alarm": {
        "level": EventLevel.DEBUG,
        "message": {
            "True": "Zone {label} has an alarm in memory",
            "False": "Zone {label} alarm memory cleared",
        },
    },
    "presently_in_alarm": {
        "level": EventLevel.DEBUG,
        "message": {
            "True": "Zone {label} presently in alarm",
            "False": "Zone {label} no longer in alarm",
        },
    },
    "tamper": _quiet("tamper"),
    "low_battery": {
        "level": EventLevel.DEBUG,
        "tags": ["trouble", "battery"],
        "message": {
            "True": "{Type} {label} low battery",
            "False": "{Type} {label} battery OK",
        },
    },
    # any trouble: each one notifies on its own (or from the log)
    "trouble": _quiet("trouble"),
    **{
        prop: _quiet(prop)
        for prop in (
            "telephone_line",
            "timer_loss_trouble",
            "battery_failure_trouble",
            "low_battery_trouble",
            "ac_failure_trouble",
            "zone_tamper_trouble",
            "rf_low_battery_trouble",
            "zone_supervision_trouble",
            "rf_interference_trouble",
        )
    },
    **{
        f"personal_channel_{n}_ftc_trouble": _trouble(
            f"{_FTC} to personal channel {n}", _LOGGED, ["communication"]
        )
        for n in range(1, 9)
    },
    **{
        f"central_path_{n}_ftc_trouble": _trouble(
            f"{_FTC} to central station path {n}", _LOGGED, ["communication"]
        )
        for n in range(1, 4)
    },
    **{
        f"central_{channel.lower()}_{n}_ftc_trouble": _trouble(
            f"{_FTC} to central station channel {channel} {n}",
            _LOGGED,
            ["communication"],
        )
        for channel in ("GPRS", "IP", "Land", "GSM")
        for n in (1, 2)
    },
    "panel_tamper_trouble": _trouble("Console tamper", _LOGGED, ["tamper"]),
    "ac_overload_trouble": _trouble("Console AC overload", tags=["power"]),
    "rf_power_failure_trouble": _trouble(
        "Wireless device power failure", _LOGGED, ["power"]
    ),
    "gsm_module_missing_trouble": _trouble("GSM module missing", tags=["gsm"]),
    "gsm_sim_1_missing_trouble": _trouble("SIM card 1 missing", tags=["gsm"]),
    "gsm_sim_2_missing_trouble": _trouble("SIM card 2 missing", tags=["gsm"]),
    "gprs_no_service_trouble": _trouble("GPRS no service", tags=["gsm"]),
    "ip_module_missing_trouble": _trouble("IP module missing", tags=["ip"]),
    "landline_no_service_trouble": _trouble(
        "Internal landline no service", _LOGGED, ["telephone"]
    ),
    "gsm_no_service_trouble": _trouble("GSM no service", _LOGGED, ["gsm"]),
    "internal_gprs_no_service_trouble": _trouble(
        "Internal GPRS no service", tags=["gsm"]
    ),
    "ip_no_service_trouble": _trouble("IP no service", _LOGGED, ["ip"]),
    "target_state": {
        "level": EventLevel.DEBUG,
        "message": "{Type} {label} target state is {value}",
    },
}
