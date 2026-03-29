"""
PRT3 event map and PRT3Event type.

EVENT_MAP maps G-group codes (int) to PAI event descriptor dicts.
It will be populated in Phase 3 by consulting the PRT3 ASCII Programming
Guide section "System Event Group Codes".

PRT3Event subclasses Event (not LiveEvent) because LiveEvent asserts
``raw.fields.value.po.command == 0xE``, which is meaningless for ASCII events.
PRT3 events are constructed directly from parsed PRT3SystemEvent dataclasses.

TODO (Phase 3): Populate EVENT_MAP with all G-group codes.
TODO (Phase 3): Implement PRT3Event.from_prt3(event: PRT3SystemEvent, ...).
"""

from paradox.event import Event

# ---------------------------------------------------------------------------
# Event map (empty until Phase 3)
# ---------------------------------------------------------------------------

# Maps G-group code (int) -> dict with keys:
#   'type'     : str   PAI event type tag, e.g. 'zone', 'partition', 'system'
#   'subtype'  : str   PAI event subtype / message template
#   'level'    : EventLevel
#
# Example entry (to be added in Phase 3):
#   1: {'type': 'zone', 'subtype': 'alarm', 'level': EventLevel.CRITICAL},
EVENT_MAP: dict = {}  # TODO (Phase 3): populate from PRT3 spec


# ---------------------------------------------------------------------------
# PRT3Event
# ---------------------------------------------------------------------------

class PRT3Event(Event):
    """
    PAI Event subclass for PRT3 system events.

    Does NOT inherit LiveEvent because LiveEvent.``__init__`` asserts
    ``raw.fields.value.po.command == 0xE``, which is a binary-protocol
    concept that does not exist in PRT3 ASCII messages.

    TODO (Phase 3): Implement from_prt3() factory method.
    """

    @classmethod
    def from_prt3(cls, prt3_event, label_provider=None) -> "PRT3Event":
        """
        Construct a PRT3Event from a parsed PRT3SystemEvent dataclass.

        :param prt3_event: PRT3SystemEvent(group, number, area)
        :param label_provider: callable(type, value) -> label string

        TODO (Phase 3): Look up group in EVENT_MAP, populate fields.
        """
        raise NotImplementedError(
            "PRT3Event.from_prt3() not yet implemented — see Phase 3"
        )
