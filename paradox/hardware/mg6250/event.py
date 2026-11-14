"""MG6250 events: "Description of MG6250 Events" in the programming guide
(MG6250-EP04, tables 10 to 12). The major code is the guide's event number.

Tables 11 and 12 are saved in the event log (service 0x22); PAI reads them
after the fact, so they carry no state change: polling stays the source of
state. Table 10 is never saved: it is only sent as live events, [2008] options
5-8, which PAI does not read yet.
"""

from paradox.event import EventLevel


def _numbered(level, element_type, message, tags=None):
    """An event whose minor code is the number of the element."""
    return dict(level=level, type=element_type, tags=tags or [], message=message)


def _troubles(level, tags, suffix=""):
    return dict(
        level=level,
        type="system",
        tags=tags,
        sub={
            0: f"Telephone line trouble{suffix}",
            1: f"AC failure{suffix}",
            2: f"Battery failure{suffix}",
            3: f"Timer loss trouble{suffix}",
            4: f"Console tamper{suffix}",
            5: f"RF jamming{suffix}",
            6: f"GSM no service{suffix}",
            7: f"GSM supervision loss{suffix}",
            8: f"IP no service{suffix}",
            9: f"IP supervision loss{suffix}",
            10: f"IP receiver lost{suffix}",
            11: f"Fail to communicate to central{suffix}",
            12: f"Fail to communicate personal reporting{suffix}",
        },
    )


def _partition_status(level, change, tags, message):
    return dict(level=level, change=change, tags=tags, message=message)


event_map = {
    # Table 10: non reportable, non saved (live events only)
    0: dict(
        level=EventLevel.DEBUG,
        change=dict(open=False),
        type="zone",
        message="Zone {label} OK",
    ),
    1: dict(
        level=EventLevel.DEBUG,
        change=dict(open=True),
        type="zone",
        message="Zone {label} open",
    ),
    2: dict(
        level=EventLevel.CRITICAL,
        type="partition",
        sub={
            2: _partition_status(
                EventLevel.CRITICAL,
                dict(silent_alarm=True, alarm=True),
                ["alarm", "silent_alarm"],
                "Partition {label} silent alarm",
            ),
            3: _partition_status(
                EventLevel.CRITICAL,
                dict(audible_alarm=True, alarm=True),
                ["alarm", "buzzer_alarm"],
                "Partition {label} buzzer alarm",
            ),
            4: _partition_status(
                EventLevel.CRITICAL,
                dict(audible_alarm=True, alarm=True),
                ["alarm", "steady_alarm"],
                "Partition {label} steady alarm",
            ),
            5: _partition_status(
                EventLevel.CRITICAL,
                dict(audible_alarm=True, alarm=True),
                ["alarm", "pulse_alarm"],
                "Partition {label} pulse alarm",
            ),
            6: _partition_status(
                EventLevel.CRITICAL,
                dict(strobe_alarm=True, alarm=True),
                ["alarm", "strobe"],
                "Partition {label} strobe",
            ),
            7: _partition_status(
                EventLevel.INFO,
                dict(alarm=False),
                [],
                "Partition {label} alarm stopped",
            ),
            8: dict(level=EventLevel.DEBUG, message="Squawk ON"),
            9: dict(level=EventLevel.DEBUG, message="Squawk OFF"),
            10: dict(level=EventLevel.DEBUG, message="Ground start"),
            11: _partition_status(
                EventLevel.INFO,
                dict(arm=False, arm_sleep=False, arm_stay=False, alarm=False),
                ["disarm"],
                "Partition {label} disarmed",
            ),
            12: _partition_status(
                EventLevel.INFO, dict(arm=True), ["arm"], "Partition {label} armed"
            ),
            13: _partition_status(
                EventLevel.INFO,
                dict(entry_delay=True),
                [],
                "Partition {label} in entry delay",
            ),
            14: _partition_status(
                EventLevel.INFO,
                dict(exit_delay=True),
                [],
                "Partition {label} in exit delay",
            ),
            15: dict(level=EventLevel.DEBUG, message="Pre-alarm delay"),
        },
    ),
    3: dict(
        level=EventLevel.DEBUG,
        type="system",
        sub={
            0: "Bell off",
            1: "Bell on",
            2: "Bell squawk (once)",
            3: "Bell squawk (twice)",
        },
    ),
    # Table 11: non reportable, saved
    6: dict(
        level=EventLevel.DEBUG,
        type="system",
        sub={
            1: "CLEAR + ENTER pressed",
            3: dict(
                level=EventLevel.INFO,
                type="partition",
                tags=["arm"],
                message="Partition {label} armed in stay mode",
            ),
            4: dict(
                level=EventLevel.INFO,
                type="partition",
                tags=["arm"],
                message="Partition {label} armed in sleep mode",
            ),
            5: dict(
                level=EventLevel.INFO,
                type="partition",
                tags=["arm"],
                message="Partition {label} armed in force mode",
            ),
            6: dict(
                level=EventLevel.INFO,
                type="partition",
                tags=["arm"],
                message="Partition {label} full arm from stay mode",
            ),
            7: dict(level=EventLevel.WARN, message="PC fail to communicate"),
            8: "Utility key 1 pressed",
            9: "Utility key 2 pressed",
            10: "Utility key 3 pressed",
            11: "Utility key 4 pressed",
            12: "Utility key 5 pressed",
            13: "Utility key 6 pressed",
            14: dict(
                level=EventLevel.CRITICAL,
                type="partition",
                tags=["alarm", "tamper"],
                message="Partition {label}: tamper generated alarm",
            ),
            15: dict(
                level=EventLevel.CRITICAL,
                type="partition",
                tags=["alarm", "supervision"],
                message="Partition {label}: supervision loss generated alarm",
            ),
            16: dict(level=EventLevel.WARN, message="Doorbell 1 battery trouble"),
            17: "Doorbell 1 battery trouble restore",
            18: dict(level=EventLevel.WARN, message="Doorbell 2 battery trouble"),
            19: "Doorbell 2 battery trouble restore",
            20: dict(
                level=EventLevel.INFO,
                type="partition",
                tags=["arm"],
                message="Partition {label} sleep to full arm",
            ),
            21: dict(level=EventLevel.INFO, message="Firmware upgrade"),
            22: dict(level=EventLevel.WARN, message="Missing SIM card"),
            23: dict(
                level=EventLevel.INFO,
                type="partition",
                message="Partition {label} StayD mode activated",
            ),
            24: dict(
                level=EventLevel.INFO,
                type="partition",
                message="Partition {label} StayD mode deactivated",
            ),
            25: "IP registration status change",
            26: "GPRS registration status change",
            27: dict(level=EventLevel.WARN, message="Remote access denied"),
            28: dict(
                level=EventLevel.WARN,
                tags=["trouble"],
                message="Fail to communicate to central station channel(s)",
            ),
            29: dict(
                tags=["trouble", "restore"],
                message="Fail to communicate to central station channel(s) restore",
            ),
            30: "User call ended due to central polling",
        },
    ),
    7: _numbered(EventLevel.INFO, "user", "Remote access by {label}"),
    8: _numbered(EventLevel.INFO, "user", "Remote PGM1 by {label}"),
    9: _numbered(EventLevel.INFO, "user", "Remote PGM2 by {label}"),
    10: _numbered(EventLevel.INFO, "user", "Remote PGM3 by {label}"),
    11: _numbered(EventLevel.INFO, "user", "Remote PGM4 by {label}"),
    12: _numbered(EventLevel.INFO, "user", "Remote PGM5 by {label}"),
    13: _numbered(EventLevel.INFO, "user", "Remote PGM6 by {label}"),
    14: _numbered(EventLevel.INFO, "user", "Remote access granted to {label}"),
    15: _numbered(EventLevel.INFO, "pgm", "PGM {label} activated via phone"),
    16: _numbered(EventLevel.DEBUG, "zone", "Smoke beep acknowledged on {label}"),
    17: _numbered(EventLevel.DEBUG, "zone", "TX delay on zone {label}"),
    18: _numbered(EventLevel.WARN, "zone", "Zone {label} signal strength weak 1"),
    19: _numbered(EventLevel.WARN, "zone", "Zone {label} signal strength weak 2"),
    20: _numbered(EventLevel.WARN, "zone", "Zone {label} signal strength weak 3"),
    21: _numbered(EventLevel.WARN, "zone", "Zone {label} signal strength weak 4"),
    # the minor code is the voltage, not an element: an empty sub keeps it out of id
    22: dict(
        level=EventLevel.DEBUG, type="system", sub={}, message="Battery voltage level"
    ),
    23: dict(level=EventLevel.DEBUG, type="system", sub={}, message="DC voltage level"),
    24: _numbered(EventLevel.WARN, "zone", "Fire delay started on zone {label}"),
    25: _numbered(EventLevel.INFO, "zone", "Fire delay cancelled on zone {label}"),
    26: _numbered(EventLevel.DEBUG, "user", "User code of {label} entered"),
    28: _numbered(EventLevel.DEBUG, "zone", "StayD pass acknowledged for {label}"),
    29: _numbered(EventLevel.INFO, "zone", "Cold start of wireless zone {label}"),
    30: _numbered(EventLevel.INFO, "pgm", "Cold start of wireless PGM {label}"),
    31: _numbered(EventLevel.INFO, "keypad", "Cold start of keypad {label}"),
    32: _numbered(EventLevel.INFO, "repeater", "Cold start of repeater {label}"),
    33: _numbered(EventLevel.INFO, "siren", "Cold start of siren {label}"),
    # Table 12: reportable, saved
    40: _numbered(EventLevel.INFO, "user", "Arming by user {label}", ["arm"]),
    41: dict(
        level=EventLevel.INFO,
        type="partition",
        tags=["arm"],
        sub={
            0: "Partition {label} auto-arming",
            1: "Partition {label} late to close",
            2: "Partition {label} no movement arming",
            3: "Partition {label} partial arming",
            4: "Partition {label} quick arming",
            5: "Partition {label} armed via BabyWare",
            6: "Partition {label} armed with keyswitch",
        },
    ),
    42: _numbered(EventLevel.INFO, "user", "Disarming by user {label}", ["disarm"]),
    43: _numbered(
        EventLevel.INFO, "user", "Disarming after alarm by user {label}", ["disarm"]
    ),
    44: _numbered(EventLevel.INFO, "user", "Alarm cancelled by user {label}"),
    45: dict(
        level=EventLevel.INFO,
        type="partition",
        tags=["disarm"],
        sub={
            0: "Partition {label} auto-arm cancelled",
            1: "Partition {label} disarmed via BabyWare",
            2: "Partition {label} disarmed via BabyWare after alarm",
            3: "Partition {label} alarm cancelled via BabyWare",
            4: "Partition {label} paramedic alarm cancelled",
            5: "Partition {label} disarmed with keyswitch",
            6: "Partition {label} disarmed with keyswitch after alarm",
            7: "Partition {label} alarm cancelled with keyswitch",
        },
    ),
    46: _numbered(EventLevel.INFO, "zone", "Zone {label} bypassed", ["bypass"]),
    47: _numbered(
        EventLevel.CRITICAL, "zone", "Zone {label} in alarm", ["alarm", "trigger"]
    ),
    48: _numbered(
        EventLevel.CRITICAL,
        "zone",
        "Zone {label} in fire alarm",
        ["alarm", "fire", "trigger"],
    ),
    49: _numbered(
        EventLevel.INFO, "zone", "Zone {label} alarm restore", ["alarm", "restore"]
    ),
    50: _numbered(
        EventLevel.INFO,
        "zone",
        "Zone {label} fire alarm restore",
        ["alarm", "fire", "restore"],
    ),
    51: _numbered(EventLevel.WARN, "zone", "Zone {label} shutdown"),
    52: dict(
        level=EventLevel.CRITICAL,
        type="partition",
        tags=["alarm", "trigger"],
        sub={
            0: "Partition {label} panic emergency",
            1: "Partition {label} panic medical",
            2: "Partition {label} panic fire",
            3: "Partition {label} recent closing",
            4: "Partition {label} global shutdown",
            5: "Partition {label} duress alarm",
            6: "Partition {label} keypad lockout",
        },
    ),
    53: _numbered(
        EventLevel.CRITICAL,
        "user",
        "Paramedic alarm by {label}",
        ["alarm", "medic", "trigger"],
    ),
    54: dict(
        level=EventLevel.INFO,
        type="system",
        sub={
            0: "System power up",
            1: "Reporting test",
            2: "Software log on",
            3: "Software log out",
            4: "Installer in programming mode",
            5: "Installer exited programming mode",
            6: dict(level=EventLevel.WARN, message="Closing delinquency delay elapsed"),
            7: dict(level=EventLevel.WARN, message="Fail to arm"),
        },
    ),
    55: _troubles(EventLevel.WARN, ["trouble"]),
    56: _troubles(EventLevel.INFO, ["trouble", "restore"], " restore"),
    57: _numbered(EventLevel.WARN, "zone", "Zone {label} tampered", ["tamper"]),
    58: _numbered(
        EventLevel.INFO, "zone", "Zone {label} tamper restore", ["tamper", "restore"]
    ),
    59: _numbered(EventLevel.WARN, "zone", "Low battery on zone {label}", ["trouble"]),
    60: _numbered(
        EventLevel.INFO,
        "zone",
        "Low battery on zone {label} restore",
        ["trouble", "restore"],
    ),
    61: _numbered(
        EventLevel.WARN,
        "zone",
        "Zone {label} supervision trouble",
        ["trouble", "supervision"],
    ),
    62: _numbered(
        EventLevel.INFO,
        "zone",
        "Zone {label} supervision restore",
        ["trouble", "supervision", "restore"],
    ),
    63: _numbered(EventLevel.WARN, "pgm", "PGM {label} tamper trouble", ["tamper"]),
    64: _numbered(
        EventLevel.INFO, "pgm", "PGM {label} tamper restore", ["tamper", "restore"]
    ),
    65: _numbered(
        EventLevel.WARN, "pgm", "PGM {label} supervision loss", ["supervision"]
    ),
    66: _numbered(
        EventLevel.INFO,
        "pgm",
        "PGM {label} supervision restore",
        ["supervision", "restore"],
    ),
    67: _numbered(
        EventLevel.WARN, "keypad", "Keypad {label} supervision loss", ["supervision"]
    ),
    68: _numbered(
        EventLevel.INFO,
        "keypad",
        "Keypad {label} supervision restore",
        ["supervision", "restore"],
    ),
    69: _numbered(EventLevel.WARN, "keypad", "Keypad {label} low battery", ["trouble"]),
    70: _numbered(
        EventLevel.INFO,
        "keypad",
        "Keypad {label} low battery restore",
        ["trouble", "restore"],
    ),
    71: _numbered(EventLevel.WARN, "keypad", "Keypad {label} AC trouble", ["trouble"]),
    72: _numbered(
        EventLevel.INFO,
        "keypad",
        "Keypad {label} AC trouble restore",
        ["trouble", "restore"],
    ),
    73: _numbered(
        EventLevel.WARN,
        "repeater",
        "Repeater {label} supervision loss",
        ["supervision"],
    ),
    74: _numbered(
        EventLevel.INFO,
        "repeater",
        "Repeater {label} supervision restore",
        ["supervision", "restore"],
    ),
    75: _numbered(
        EventLevel.WARN, "repeater", "Repeater {label} low battery", ["trouble"]
    ),
    76: _numbered(
        EventLevel.INFO,
        "repeater",
        "Repeater {label} low battery restore",
        ["trouble", "restore"],
    ),
    77: _numbered(
        EventLevel.WARN, "repeater", "Repeater {label} AC trouble", ["trouble"]
    ),
    78: _numbered(
        EventLevel.INFO,
        "repeater",
        "Repeater {label} AC trouble restore",
        ["trouble", "restore"],
    ),
    79: _numbered(EventLevel.WARN, "siren", "Siren {label} tamper trouble", ["tamper"]),
    80: _numbered(
        EventLevel.INFO, "siren", "Siren {label} tamper restore", ["tamper", "restore"]
    ),
    81: _numbered(
        EventLevel.WARN, "siren", "Siren {label} supervision loss", ["supervision"]
    ),
    82: _numbered(
        EventLevel.INFO,
        "siren",
        "Siren {label} supervision restore",
        ["supervision", "restore"],
    ),
    83: _numbered(EventLevel.WARN, "siren", "Siren {label} low battery", ["trouble"]),
    84: _numbered(
        EventLevel.INFO,
        "siren",
        "Siren {label} low battery restore",
        ["trouble", "restore"],
    ),
    85: _numbered(EventLevel.WARN, "siren", "Siren {label} AC trouble", ["trouble"]),
    86: _numbered(
        EventLevel.INFO,
        "siren",
        "Siren {label} AC trouble restore",
        ["trouble", "restore"],
    ),
}
