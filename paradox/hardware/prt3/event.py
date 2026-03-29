"""
PRT3 event map and PRT3Event.

EVENT_MAP maps G-group codes (int) to PAI event descriptor dicts.
PRT3Event subclasses Event (not LiveEvent) because LiveEvent.__init__
asserts ``raw.fields.value.po.command == 0xE``, which is a binary-protocol
concept that does not exist in PRT3 ASCII messages.

Event group source
------------------
G-group codes are taken from the PRT3 ASCII Programming Guide, table
"System Event Group Codes".  Only groups observable from v1 scope are
mapped here; unknown groups fall through to a generic "system" entry.

Event type / subtype conventions
---------------------------------
``type``    — the PAI element type: "zone", "partition", "user", or "system".
``subtype`` — a short lower-case descriptor matching property_map keys where
              possible (e.g. "alarm", "open", "arm").
``level``   — EventLevel severity.
``change``  — dict of property updates to apply to the element (may be empty).
``tags``    — list of string tags (forwarded to pub/sub consumers).
``message`` — human-readable template string (use {label} for element label).
"""

import logging

from paradox.event import Event, EventLevel

logger = logging.getLogger("PAI").getChild(__name__)


# ---------------------------------------------------------------------------
# Event group code table
# PRT3 ASCII Programming Guide §System Event Group Codes
# ---------------------------------------------------------------------------

EVENT_MAP: dict = {
    # Zone status events (number = zone ID, area = affected area)
    0:  dict(type="zone",      subtype="restored",           level=EventLevel.INFO,
             change={"alarm": False, "open": False},
             tags=["zone", "restore"],
             message="Zone {label} restored"),
    1:  dict(type="zone",      subtype="open",               level=EventLevel.DEBUG,
             change={"open": True},
             tags=["zone", "open"],
             message="Zone {label} open"),
    2:  dict(type="zone",      subtype="tampered",           level=EventLevel.CRITICAL,
             change={"tamper": True, "open": True},
             tags=["zone", "tamper", "trouble"],
             message="Zone {label} tampered"),
    3:  dict(type="zone",      subtype="fire_loop_trouble",  level=EventLevel.CRITICAL,
             change={"fire_loop_trouble": True},
             tags=["zone", "trouble", "fire"],
             message="Zone {label} fire loop trouble"),

    # Arm events (number = user ID, area = affected partition)
    10: dict(type="partition", subtype="arm",                level=EventLevel.INFO,
             change={"arm": True},
             tags=["arm", "user"],
             message="Partition {label} armed by user"),
    11: dict(type="partition", subtype="arm",                level=EventLevel.INFO,
             change={"arm": True},
             tags=["arm", "master"],
             message="Partition {label} armed by master"),
    12: dict(type="partition", subtype="arm",                level=EventLevel.INFO,
             change={"arm": True},
             tags=["arm", "keyswitch"],
             message="Partition {label} armed via keyswitch"),
    13: dict(type="partition", subtype="arm",                level=EventLevel.INFO,
             change={"arm": True},
             tags=["arm", "auto"],
             message="Partition {label} auto-armed"),

    # Disarm events (number = user ID, area = affected partition)
    14: dict(type="partition", subtype="disarm",             level=EventLevel.INFO,
             change={"arm": False},
             tags=["disarm", "user"],
             message="Partition {label} disarmed by user"),
    15: dict(type="partition", subtype="disarm",             level=EventLevel.INFO,
             change={"arm": False},
             tags=["disarm", "master"],
             message="Partition {label} disarmed by master"),
    16: dict(type="partition", subtype="disarm",             level=EventLevel.INFO,
             change={"arm": False},
             tags=["disarm", "keyswitch"],
             message="Partition {label} disarmed via keyswitch"),
    17: dict(type="partition", subtype="disarm",             level=EventLevel.INFO,
             change={"arm": False, "audible_alarm": False},
             tags=["disarm", "alarm_cancel"],
             message="Partition {label} disarmed after alarm"),
    18: dict(type="partition", subtype="alarm_cancelled",    level=EventLevel.INFO,
             change={"audible_alarm": False},
             tags=["alarm", "cancel"],
             message="Partition {label} alarm cancelled"),
    20: dict(type="partition", subtype="disarm",             level=EventLevel.INFO,
             change={"arm": False},
             tags=["disarm", "special"],
             message="Partition {label} special disarm"),

    # Zone bypass events (number = zone ID)
    21: dict(type="zone",      subtype="bypassed",           level=EventLevel.INFO,
             change={"bypassed": True},
             tags=["zone", "bypass"],
             message="Zone {label} bypassed"),
    23: dict(type="zone",      subtype="bypass_cancelled",   level=EventLevel.INFO,
             change={"bypassed": False},
             tags=["zone", "bypass"],
             message="Zone {label} bypass cancelled"),

    # Alarm events (number = zone ID, area = affected partition)
    24: dict(type="zone",      subtype="alarm",              level=EventLevel.CRITICAL,
             change={"alarm": True},
             tags=["zone", "alarm"],
             message="Zone {label} in alarm"),
    25: dict(type="zone",      subtype="fire_alarm",         level=EventLevel.CRITICAL,
             change={"fire": True},
             tags=["zone", "alarm", "fire"],
             message="Zone {label} fire alarm"),
    26: dict(type="zone",      subtype="alarm_restored",     level=EventLevel.INFO,
             change={"alarm": False},
             tags=["zone", "alarm", "restore"],
             message="Zone {label} alarm restored"),
    27: dict(type="zone",      subtype="fire_alarm_restored", level=EventLevel.INFO,
             change={"fire": False},
             tags=["zone", "alarm", "fire", "restore"],
             message="Zone {label} fire alarm restored"),

    # Panic alarms (number = user/zone, area = partition)
    29: dict(type="partition", subtype="panic_alarm",        level=EventLevel.CRITICAL,
             change={"panic_alarm": True},
             tags=["alarm", "panic"],
             message="Partition {label} panic alarm"),
    30: dict(type="partition", subtype="alarm",              level=EventLevel.CRITICAL,
             change={"audible_alarm": True},
             tags=["alarm"],
             message="Partition {label} alarm shutdown"),
    31: dict(type="zone",      subtype="tamper_alarm",       level=EventLevel.CRITICAL,
             change={"alarm": True, "tamper": True},
             tags=["zone", "alarm", "tamper"],
             message="Zone {label} tamper alarm"),
    32: dict(type="zone",      subtype="tamper_restored",    level=EventLevel.INFO,
             change={"tamper": False},
             tags=["zone", "tamper", "restore"],
             message="Zone {label} tamper restored"),

    # Trouble events (number = zone/module/user, area = affected)
    33: dict(type="system",    subtype="trouble",            level=EventLevel.CRITICAL,
             change={},
             tags=["trouble"],
             message="New trouble event"),
    34: dict(type="system",    subtype="trouble_restored",   level=EventLevel.INFO,
             change={},
             tags=["trouble", "restore"],
             message="Trouble restored"),
    36: dict(type="system",    subtype="ac_failure",         level=EventLevel.CRITICAL,
             change={"ac_failure_trouble": True},
             tags=["trouble", "power"],
             message="AC power failure"),
    38: dict(type="system",    subtype="battery_trouble",    level=EventLevel.CRITICAL,
             change={"battery_failure_trouble": True},
             tags=["trouble", "battery"],
             message="Battery trouble"),

    # Power / communication
    45: dict(type="system",    subtype="power_up",           level=EventLevel.INFO,
             change={},
             tags=["system", "power"],
             message="Panel power-up"),

    # Utility key (number = key number, area = 0 / global)
    48: dict(type="system",    subtype="utility_key",        level=EventLevel.INFO,
             change={},
             tags=["system", "utility"],
             message="Utility key {number} activated"),

    # Zone lifecycle
    56: dict(type="zone",      subtype="bypassed",           level=EventLevel.INFO,
             change={"bypassed": True},
             tags=["zone", "bypass"],
             message="Zone {label} bypassed"),
    59: dict(type="zone",      subtype="closed",             level=EventLevel.DEBUG,
             change={"open": False},
             tags=["zone"],
             message="Zone {label} closed"),
    60: dict(type="zone",      subtype="low_battery",        level=EventLevel.CRITICAL,
             change={"low_battery_trouble": True},
             tags=["zone", "trouble", "battery"],
             message="Zone {label} low battery"),
    61: dict(type="zone",      subtype="supervision_trouble", level=EventLevel.CRITICAL,
             change={"supervision_trouble": True},
             tags=["zone", "trouble", "supervision"],
             message="Zone {label} supervision failure"),
    62: dict(type="zone",      subtype="low_battery_restored", level=EventLevel.INFO,
             change={"low_battery_trouble": False},
             tags=["zone", "battery", "restore"],
             message="Zone {label} battery restored"),
    63: dict(type="zone",      subtype="supervision_restored", level=EventLevel.INFO,
             change={"supervision_trouble": False},
             tags=["zone", "supervision", "restore"],
             message="Zone {label} supervision restored"),

    # Status events — periodic armed/trouble state broadcasts
    # area = affected partition; number = 0 (not used)
    64: dict(type="partition", subtype="status_armed",       level=EventLevel.INFO,
             change={"arm": True},
             tags=["arm", "status"],
             message="Partition {label} armed (status event)"),
    65: dict(type="partition", subtype="status_armed",       level=EventLevel.INFO,
             change={"arm": True},
             tags=["arm", "status"],
             message="Partition {label} armed steady state"),
    66: dict(type="system",    subtype="status_tamper",      level=EventLevel.CRITICAL,
             change={},
             tags=["trouble", "tamper", "status"],
             message="Status: tamper or trouble detected"),
}


# ---------------------------------------------------------------------------
# PRT3Event
# ---------------------------------------------------------------------------

class PRT3Event(Event):
    """
    PAI Event subclass for PRT3 system events.

    Constructed from a PRT3SystemEvent dataclass via from_prt3().  Does NOT
    inherit LiveEvent because LiveEvent.__init__ asserts a binary command
    code that does not exist in PRT3 messages.
    """

    @classmethod
    def from_prt3(cls, prt3_event, label_provider=None) -> "PRT3Event":
        """
        Construct a PRT3Event from a parsed PRT3SystemEvent dataclass.

        :param prt3_event:     PRT3SystemEvent(group, number, area)
        :param label_provider: Optional callable(element_type, index) → str
                               for resolving element labels.  If None, a
                               numeric label is used.
        :returns:              PRT3Event with level, type, subtype, change,
                               tags, message, and additional_data populated.
        """
        descriptor = EVENT_MAP.get(prt3_event.group)
        if descriptor is None:
            logger.debug(
                "PRT3: unknown event group G%03d N%03d A%03d",
                prt3_event.group, prt3_event.number, prt3_event.area,
            )
            descriptor = dict(
                type="system",
                subtype="unknown",
                level=EventLevel.DEBUG,
                change={},
                tags=["unknown"],
                message=f"Unknown event G{prt3_event.group:03d}",
            )

        element_type = descriptor["type"]
        element_id   = prt3_event.number  # zone/user/key ID
        area         = prt3_event.area    # 0=global, 1-8=specific, 255=any

        # Resolve label
        if label_provider is not None:
            label = label_provider(element_type, element_id) or str(element_id)
        else:
            label = str(element_id)

        event = cls()
        event.level         = descriptor["level"]
        event.type          = element_type
        event.id            = element_id
        event.partition     = area
        event.label         = label
        event._message_tpl  = descriptor["message"]
        event.change        = dict(descriptor["change"])  # copy to avoid mutation
        event.tags          = list(descriptor.get("tags", []))
        event.additional_data = {
            "group":  prt3_event.group,
            "number": prt3_event.number,
            "area":   prt3_event.area,
        }

        return event
