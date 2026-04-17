"""
PRT3 ASCII line parser.

``parse_line(line: str) -> PRT3Message | None``

All incoming PRT3 messages are plain ASCII strings with the trailing ``\\r``
already stripped by ``PRT3Protocol.data_received()``.  This module converts
them into typed dataclasses; the rest of the stack never has to inspect raw
strings.

Message grammar (PRT3 ASCII Programming Guide, rev. 1.0):

  COMM&ok              panel ready (startup or combus restore)
  COMM&fail            panel / combus communication failure
  !                    reception buffer full — last command was dropped
  {5chars}&OK          action-command echo — success
  {5chars}&fail        action-command echo — failure; also: info-cmd not found
  RA{nnn}{7 flags}     area status reply (info command)
  RZ{nnn}{5 flags}     zone status reply (info command)
  ZL{nnn}{16 chars}    zone label reply  (info command)
  AL{nnn}{16 chars}    area label reply  (info command)
  UL{nnn}{16 chars}    user label reply  (info command)
  G{ggg}N{nnn}A{aaa}   asynchronous system event
  PGM{nn}ON            virtual PGM activated  (v1: parsed but not acted on)
  PGM{nn}OFF           virtual PGM deactivated (v1: parsed but not acted on)

Echo rules:
  - Action commands (AA/AQ/AD/PE/PM/PF/UK/SR/VO/VC): reply is first-5 + &OK/&fail
  - Info commands (RA/RZ/ZL/AL/UL): reply is first-5 + data (no separate &OK)
  - A failed info command still produces first-5 + &fail

Flag layout for RA{nnn}XPTNASMM (positions 5-11, zero-indexed from start):
  [5] arm state: D=disarmed A=armed_away F=armed_force S=armed_stay I=armed_instant
  [6] P=in_programming  / O=no
  [7] T=trouble         / O=no
  [8] N=not_ready       / O=ready
  [9] A=alarm           / O=no
  [10] S=strobe         / O=no
  [11] M=zone_in_memory / O=no

Flag layout for RZ{nnn}XAFSL (positions 5-9):
  [5] open state: C=closed  O=open  T=tampered  F=fire_loop_trouble
  [6] A=alarm             / O=no
  [7] F=fire_alarm        / O=no
  [8] S=supervision_fault / O=no
  [9] L=low_battery       / O=no
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Union

logger = logging.getLogger("PAI").getChild(__name__)


# ---------------------------------------------------------------------------
# Arm-state constants  (value of PRT3AreaStatus.arm_state)
# ---------------------------------------------------------------------------

ARM_DISARMED      = "disarmed"
ARM_AWAY          = "armed_away"
ARM_FORCE         = "armed_force"
ARM_STAY          = "armed_stay"
ARM_INSTANT       = "armed_instant"

_ARM_STATE_MAP: dict = {
    "D": ARM_DISARMED,
    "A": ARM_AWAY,
    "F": ARM_FORCE,
    "S": ARM_STAY,
    "I": ARM_INSTANT,
}

# ---------------------------------------------------------------------------
# Zone open-state constants  (value of PRT3ZoneStatus.open_state)
# ---------------------------------------------------------------------------

ZONE_CLOSED            = "closed"
ZONE_OPEN              = "open"
ZONE_TAMPERED          = "tampered"
ZONE_FIRE_LOOP_TROUBLE = "fire_loop_trouble"

_ZONE_OPEN_MAP: dict = {
    "C": ZONE_CLOSED,
    "O": ZONE_OPEN,
    "T": ZONE_TAMPERED,
    "F": ZONE_FIRE_LOOP_TROUBLE,
}

# ---------------------------------------------------------------------------
# Message dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PRT3CommStatus:
    """``COMM&ok`` or ``COMM&fail`` — combus/module communication status."""
    ok: bool  # True = panel ready


@dataclass
class PRT3BufferFull:
    """``!`` — module reception buffer full; the preceding command was dropped."""


@dataclass
class PRT3CommandEcho:
    """Echo of a command we sent: first 5 chars of the command + &OK / &fail.

    For action commands (arm, disarm, panic, utility key) this is the only
    reply.  For info commands that fail (e.g. unknown area), this is also
    returned.
    """
    cmd: str   # exactly the first 5 ASCII chars of the command that was sent
    ok: bool


@dataclass
class PRT3AreaStatus:
    """Reply to ``RA{nnn}`` — area status flags.

    ``not_ready`` mirrors the wire protocol: ``True`` means the area is NOT
    ready to arm (open zone, active trouble, etc.).  The adapter layer should
    negate this to produce a ``ready`` property.
    """
    area: int
    arm_state: str       # one of the ARM_* constants above
    in_programming: bool
    trouble: bool
    not_ready: bool      # True → area is NOT ready
    alarm: bool
    strobe: bool
    zone_in_memory: bool


@dataclass
class PRT3ZoneStatus:
    """Reply to ``RZ{nnn}`` — zone status flags."""
    zone: int
    open_state: str          # one of the ZONE_* constants above
    alarm: bool
    fire_alarm: bool
    supervision_trouble: bool
    low_battery: bool


@dataclass
class PRT3LabelReply:
    """Reply to ``ZL/AL/UL{nnn}`` — 16-character ASCII label (spaces preserved)."""
    element_type: str  # "zone", "area", or "user"
    index: int
    label: str         # exactly 16 chars; trailing spaces not stripped


@dataclass
class PRT3SystemEvent:
    """Async system event from the panel: ``G{ggg}N{nnn}A{aaa}``.

    ``area == 0`` means the event occurred in all enabled areas (global).
    ``area == 255`` means at least one enabled area (per spec Note 1).
    """
    group: int    # 3-digit event-group code (000-066)
    number: int   # event-specific identifier: zone, user, door, key, …
    area: int     # 0 = global / all, 1-8 = specific area, 255 = any


@dataclass
class PRT3PgmEvent:
    """Virtual PGM activation/deactivation event (v1 scope: parsed, not acted on)."""
    pgm: int   # 1-30
    on: bool   # True if PGMxxON (activated), False if PGMxxOFF (deactivated)


# Union type exported for type annotations in callers
PRT3Message = Union[
    PRT3CommStatus,
    PRT3BufferFull,
    PRT3CommandEcho,
    PRT3AreaStatus,
    PRT3ZoneStatus,
    PRT3LabelReply,
    PRT3SystemEvent,
    PRT3PgmEvent,
]

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_RE_SYSTEM_EVENT = re.compile(r"^G(\d{3})N(\d{3})A(\d{3})$")
_RE_PGM_ON       = re.compile(r"^PGM(\d{2})ON$")
_RE_PGM_OFF      = re.compile(r"^PGM(\d{2})OFF$")

# Lengths of fully-formed info replies (after \r stripped)
_AREA_STATUS_LEN  = 12   # RA + 3-digit area + 7 flags
_ZONE_STATUS_LEN  = 10   # RZ + 3-digit zone + 5 flags
_LABEL_LEN        = 21   # 2-char type + 3-digit index + 16-char label

# Lengths of command echoes (after \r stripped)
_ECHO_OK_LEN      = 8    # 5-char prefix + "&OK"
_ECHO_FAIL_LEN    = 10   # 5-char prefix + "&fail"

_LABEL_PREFIXES   = {"ZL": "zone", "AL": "area", "UL": "user"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_line(line: str) -> Optional[PRT3Message]:
    """Parse a single ``\\r``-stripped ASCII line from the PRT3 module.

    Returns a typed ``PRT3Message`` dataclass, or ``None`` when the line is
    empty, unrecognised, or malformed.

    Malformed lines with a recognised prefix (e.g. ``RA`` with wrong length)
    emit a ``WARNING`` log and return ``None`` rather than raising.

    Ordering rationale:
      1. Empties and single-char sentinels first (cheap, unambiguous).
      2. COMM status before generic ``&fail`` / ``&ok`` because ``COMM&``
         is five chars and lowercase ``ok`` would collide with the echo
         pattern if we checked echoes first.
      3. Structured info replies before echo check: the echo check catches
         failed info commands (e.g. ``RA001&fail``) that fall through.
      4. Unknown lines → WARNING + None.
    """
    if not line:
        return None

    # 1. Buffer-full sentinel
    if line == "!":
        return PRT3BufferFull()

    # 2. COMM status (distinct from echo: COMM&ok uses lowercase, COMM&fail
    #    is 9 chars — neither matches the 8-/10-char echo patterns)
    if line == "COMM&ok":
        return PRT3CommStatus(ok=True)
    if line == "COMM&fail":
        return PRT3CommStatus(ok=False)

    # 3. System events: G001N005A006
    m = _RE_SYSTEM_EVENT.match(line)
    if m:
        return PRT3SystemEvent(
            group=int(m.group(1)),
            number=int(m.group(2)),
            area=int(m.group(3)),
        )

    # 4. Virtual PGM events (v1: parse but do not act on)
    m = _RE_PGM_ON.match(line)
    if m:
        return PRT3PgmEvent(pgm=int(m.group(1)), on=True)
    m = _RE_PGM_OFF.match(line)
    if m:
        return PRT3PgmEvent(pgm=int(m.group(1)), on=False)

    # 5–7. Structured info replies (RA/RZ/ZL/AL/UL).
    # Short echoes like RA001&fail fall through when _parse_info_reply returns None.
    msg = _parse_info_reply(line)
    if msg is not None:
        return msg

    # 8. Command echoes: {5 chars}&OK (8) or {5 chars}&fail (10)
    # Note: some panel firmware sends lowercase "&ok"; accept both.
    if len(line) == _ECHO_OK_LEN and line.upper().endswith("&OK"):
        return PRT3CommandEcho(cmd=line[:5], ok=True)
    if len(line) == _ECHO_FAIL_LEN and line.endswith("&fail"):
        return PRT3CommandEcho(cmd=line[:5], ok=False)

    logger.warning("PRT3 parser: unrecognised line %r", line)
    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_info_reply(line: str) -> Optional[PRT3Message]:
    """Dispatch structured info replies: RA/RZ/ZL/AL/UL{nnn}{data}.

    Returns None for lines that don't match (e.g. short &fail echoes),
    allowing parse_line to fall through to the echo check.
    """
    if not (len(line) >= 5 and line[2:5].isdigit()):
        return None
    prefix2 = line[:2]
    if prefix2 == "RA" and len(line) == _AREA_STATUS_LEN:
        return _parse_area_status(line)
    if prefix2 == "RZ" and len(line) == _ZONE_STATUS_LEN:
        return _parse_zone_status(line)
    if prefix2 in _LABEL_PREFIXES and len(line) == _LABEL_LEN:
        return _parse_label(line)
    return None


def _parse_area_status(line: str) -> Optional[PRT3AreaStatus]:
    """Parse ``RA{nnn}{7 flags}`` → ``PRT3AreaStatus`` or ``None`` on bad flags."""
    area      = int(line[2:5])
    arm_char  = line[5]
    arm_state = _ARM_STATE_MAP.get(arm_char)
    if arm_state is None:
        logger.warning(
            "PRT3 parser: unknown arm-state char %r in area-status line %r",
            arm_char, line,
        )
        return None
    return PRT3AreaStatus(
        area=area,
        arm_state=arm_state,
        in_programming=(line[6] == "P"),
        trouble=(line[7] == "T"),
        not_ready=(line[8] == "N"),
        alarm=(line[9] == "A"),
        strobe=(line[10] == "S"),
        zone_in_memory=(line[11] == "M"),
    )


def _parse_zone_status(line: str) -> Optional[PRT3ZoneStatus]:
    """Parse ``RZ{nnn}{5 flags}`` → ``PRT3ZoneStatus`` or ``None`` on bad flags."""
    zone       = int(line[2:5])
    open_char  = line[5]
    open_state = _ZONE_OPEN_MAP.get(open_char)
    if open_state is None:
        logger.warning(
            "PRT3 parser: unknown zone-open char %r in zone-status line %r",
            open_char, line,
        )
        return None
    return PRT3ZoneStatus(
        zone=zone,
        open_state=open_state,
        alarm=(line[6] == "A"),
        fire_alarm=(line[7] == "F"),
        supervision_trouble=(line[8] == "S"),
        low_battery=(line[9] == "L"),
    )


def _parse_label(line: str) -> PRT3LabelReply:
    """Parse ``ZL/AL/UL{nnn}{16-char label}`` → ``PRT3LabelReply``."""
    element_type = _LABEL_PREFIXES[line[:2]]
    index        = int(line[2:5])
    label        = line[5:]   # always 16 chars (spec-mandated, spaces padded)
    return PRT3LabelReply(element_type=element_type, index=index, label=label)
