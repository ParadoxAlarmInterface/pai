"""
PRT3 ASCII line parser.

parse_line(line: str) -> PRT3Message | None

All incoming PRT3 messages are plain ASCII strings (\\r already stripped).
This module turns them into typed dataclasses so the rest of the stack
never has to inspect raw strings.

Message grammar (from PRT3 ASCII Programming Guide):

  COMM&ok          — panel ready after power-on / reconnect
  COMM&fail        — panel not ready
  {cmd5}&OK        — command echo — success  (first 5 chars of sent command)
  {cmd5}&fail      — command echo — failure
  RA{nnn}...       — area status reply      (16 flag chars follow the index)
  RZ{nnn}...       — zone status reply      (9 flag chars follow the index)
  AL{nnn}{label}   — area label reply       (16-char padded label)
  ZL{nnn}{label}   — zone label reply
  UL{nnn}{label}   — user label reply
  G{ggg}N{nnn}A{aaa}  — async system event

TODO (Phase 2): Implement each branch of parse_line().
"""

from dataclasses import dataclass
from typing import Optional, Union


# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------

@dataclass
class PRT3CommStatus:
    """COMM&ok or COMM&fail received on startup."""
    ok: bool  # True = panel ready


@dataclass
class PRT3CommandEcho:
    """Echo of a command we sent, e.g. 'AA001A&OK' -> cmd='AA001A', ok=True."""
    cmd: str   # first 5 chars of the command that was echoed
    ok: bool


@dataclass
class PRT3AreaStatus:
    """Reply to RA{nnn} — parsed flag fields.

    Field order (chars 5-onward of the raw line after 'RA{nnn}'):
      D  — disarmed
      A  — armed away
      F  — armed in force
      S  — armed stay
      I  — armed instant
      N  — in alarm
      P  — partition in programming (stay arm)
      O  — fire alarm
      T  — trouble
      O  — ready for arming
      N  — exit delay active
      A  — entry delay active
    Raw example: RA001DAFSINPOTONa  (16 flag chars)

    TODO (Phase 2): Map exact flag positions from PRT3 spec table 1.
    """
    area: int
    raw_flags: str  # preserved verbatim until Phase 2 maps each field


@dataclass
class PRT3ZoneStatus:
    """Reply to RZ{nnn} — parsed flag fields.

    Flag chars (9 total) after 'RZ{nnn}':
      C — closed / O — open
      O — no tamper / T — tamper
      F — no fire / f — fire alarm
      A — no alarm / a — in alarm
      F — supervision OK / S — supervision trouble
      B — battery OK / b — low battery
      L — no low signal / l — low signal
    Raw example: RZ001COTFAFSOL

    TODO (Phase 2): Map exact flag positions from PRT3 spec table 2.
    """
    zone: int
    raw_flags: str


@dataclass
class PRT3LabelReply:
    """Reply to AL/ZL/UL{nnn} — 16-char ASCII label."""
    element_type: str  # 'area', 'zone', or 'user'
    index: int
    label: str         # raw 16-char label (spaces not stripped yet)


@dataclass
class PRT3SystemEvent:
    """Async event from the panel: G{ggg}N{nnn}A{aaa}."""
    group: int    # event group code
    number: int   # event-specific number (zone, user, …)
    area: int     # area involved


# Union type for callers
PRT3Message = Union[
    PRT3CommStatus,
    PRT3CommandEcho,
    PRT3AreaStatus,
    PRT3ZoneStatus,
    PRT3LabelReply,
    PRT3SystemEvent,
]


# ---------------------------------------------------------------------------
# Parser entry point
# ---------------------------------------------------------------------------

def parse_line(line: str) -> Optional[PRT3Message]:
    """
    Parse a single \\r-stripped ASCII line from the PRT3 module.

    Returns a typed PRT3Message dataclass, or None if the line is not
    recognised (e.g. an empty line or future extension).

    TODO (Phase 2): Implement each branch.
    """
    raise NotImplementedError(
        "PRT3 parse_line() not yet implemented — see Phase 2"
    )
