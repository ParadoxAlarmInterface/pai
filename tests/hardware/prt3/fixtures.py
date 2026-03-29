"""
PRT3 protocol fixture lines — verified against PRT3 ASCII Programming Guide.

These are representative raw ASCII lines as they arrive from the PRT3 module
with the trailing ``\\r`` already stripped.  They serve as documentation of
the wire format and as deterministic inputs for parametrized tests.

Layout reminder
---------------
Area status: ``RA{nnn}`` + 7 flag chars (total 12 chars)
  [5] D/A/F/S/I  arm state
  [6] P/O        in_programming
  [7] T/O        trouble
  [8] N/O        not_ready  (N = area is NOT ready)
  [9] A/O        alarm
  [10] S/O       strobe
  [11] M/O       zone_in_memory

Zone status: ``RZ{nnn}`` + 5 flag chars (total 10 chars)
  [5] C/O/T/F   open_state  (C closed, O open, T tampered, F fire-loop trouble)
  [6] A/O       alarm
  [7] F/O       fire_alarm
  [8] S/O       supervision_trouble
  [9] L/O       low_battery

Label: ``ZL|AL|UL{nnn}`` + 16-char label (total 21 chars, space-padded)

Command echo: ``{5chars}&OK``  (8 chars) or ``{5chars}&fail``  (10 chars)

System event: ``G{ggg}N{nnn}A{aaa}``  (12 chars)
"""

# ---------------------------------------------------------------------------
# COMM status
# ---------------------------------------------------------------------------

COMM_OK   = "COMM&ok"    # panel ready (startup or combus restore)
COMM_FAIL = "COMM&fail"  # combus / panel communication failure

# ---------------------------------------------------------------------------
# Buffer full
# ---------------------------------------------------------------------------

BUFFER_FULL = "!"

# ---------------------------------------------------------------------------
# Area status replies — RA{nnn}{7 flags}
# ---------------------------------------------------------------------------

# Disarmed, all flags clear (ready to arm)
AREA_DISARMED           = "RA001DOOOOOO"  # D=disarmed, 6×O

# Armed away, all flags clear
AREA_ARMED_AWAY         = "RA001AOOOOOO"

# Armed force, all flags clear
AREA_ARMED_FORCE        = "RA002FOOOOOO"

# Armed stay, all flags clear
AREA_ARMED_STAY         = "RA003SOOOOOO"

# Armed instant, all flags clear
AREA_ARMED_INSTANT      = "RA004IOOOOOO"

# Armed instant, zone in memory only
AREA_ARMED_MEMORY       = "RA008IOOOOOM"

# Armed away — alarm active, strobe active
AREA_ARMED_ALARM_STROBE = "RA001AOOOASO"

# Armed away — alarm active, no strobe
AREA_ARMED_ALARM        = "RA001AOOOAOO"

# Stay armed — trouble active, area not ready
AREA_STAY_TROUBLE       = "RA003SOTNOOO"

# Disarmed — in programming
AREA_IN_PROGRAMMING     = "RA001DPOOOOO"

# All flags active (armed away, prog, trouble, not-ready, alarm, strobe, memory)
AREA_ALL_FLAGS          = "RA001APTNASM"

# Max area number (8), disarmed, all clear
AREA_MAX_NUMBER         = "RA008DOOOOOO"

# ---------------------------------------------------------------------------
# Zone status replies — RZ{nnn}{5 flags}
# ---------------------------------------------------------------------------

ZONE_CLOSED_OK        = "RZ001COOOO"   # closed, all clear
ZONE_OPEN_OK          = "RZ002OOOOO"   # open, no alarms
ZONE_TAMPERED         = "RZ003TOOOO"   # tampered, no alarms
ZONE_FIRE_LOOP        = "RZ004FOOOO"   # fire-loop trouble
ZONE_ALARM            = "RZ005OAOOO"   # open, in alarm
ZONE_FIRE_ALARM       = "RZ006OOFOO"   # fire alarm (separate from fire-loop)
ZONE_SUPERVISION      = "RZ007OOOSO"   # supervision trouble
ZONE_LOW_BATTERY      = "RZ008OOOOL"   # low battery
ZONE_ALL_FLAGS        = "RZ009OAFSL"   # all flags active (open, alarm, fire, super, battery)
ZONE_MAX_NUMBER       = "RZ192COOOO"   # max zone (EVO192), closed, all clear

# ---------------------------------------------------------------------------
# Label replies — ZL/AL/UL{nnn}{16-char label}  (always exactly 21 chars)
# ---------------------------------------------------------------------------
# Labels are 16 chars, space-padded on the right.

ZONE_LABEL_FRONT_DOOR = "ZL001Front Door      "   # "Front Door" + 6 sp
ZONE_LABEL_BACK_DOOR  = "ZL002Back Door       "   # "Back Door"  + 7 sp
ZONE_LABEL_MAX_ZONE   = "ZL192Zone 192        "   # "Zone 192"   + 8 sp
AREA_LABEL_HOME       = "AL001Home            "   # "Home"       + 12 sp
AREA_LABEL_MAX_AREA   = "AL008Area 8          "   # "Area 8"     + 10 sp
USER_LABEL_MASTER     = "UL001Master          "   # "Master"     + 10 sp
USER_LABEL_MAX_USER   = "UL999User 999        "   # "User 999"   + 8 sp

# Guard: every label line must be exactly 21 chars
_labels = [
    ZONE_LABEL_FRONT_DOOR, ZONE_LABEL_BACK_DOOR, ZONE_LABEL_MAX_ZONE,
    AREA_LABEL_HOME, AREA_LABEL_MAX_AREA, USER_LABEL_MASTER, USER_LABEL_MAX_USER,
]
assert all(len(lbl) == 21 for lbl in _labels), \
    "All label fixtures must be exactly 21 chars (2-char prefix + 3-digit index + 16-char label)"

# ---------------------------------------------------------------------------
# Command echo replies
# ---------------------------------------------------------------------------

# Action command success
ECHO_ARM_OK         = "AA001&OK"    # arm area 1 succeeded
ECHO_QUICK_ARM_OK   = "AQ001&OK"
ECHO_DISARM_OK      = "AD001&OK"
ECHO_PANIC_EMERG_OK = "PE001&OK"
ECHO_PANIC_MED_OK   = "PM001&OK"
ECHO_PANIC_FIRE_OK  = "PF001&OK"
ECHO_UTILITY_KEY_OK = "UK001&OK"

# Action command failure (invalid code, wrong state, etc.)
ECHO_ARM_FAIL       = "AA001&fail"
ECHO_DISARM_FAIL    = "AD001&fail"

# Info command failure (area/zone/user not found, or out of range)
ECHO_STATUS_FAIL    = "RA001&fail"   # area status request failed
ECHO_LABEL_FAIL     = "ZL001&fail"   # zone label request failed

# ---------------------------------------------------------------------------
# Async system events — G{ggg}N{nnn}A{aaa}
# ---------------------------------------------------------------------------

EVENT_ZONE_OK           = "G000N005A006"  # G000=Zone OK,  zone 5,  area 6
EVENT_ZONE_OPEN         = "G001N005A006"  # G001=Zone Open, zone 5, area 6
EVENT_ZONE_TAMPER       = "G002N012A002"  # G002=Zone Tampered, zone 12, area 2
EVENT_ARM_USER          = "G010N001A001"  # G010=Arm w/user code, user 1, area 1
EVENT_DISARM_USER       = "G014N002A002"  # G014=Disarm w/user code, user 2, area 2
EVENT_ZONE_ALARM        = "G024N003A001"  # G024=Zone Alarm, zone 3, area 1
EVENT_FIRE_ALARM        = "G025N007A001"  # G025=Fire Alarm, zone 7, area 1
EVENT_TROUBLE_AC        = "G036N001A000"  # G036=Trouble, AC failure, global
EVENT_POWER_UP          = "G045N000A000"  # G045=Power-up (all areas), global
EVENT_UTILITY_KEY       = "G048N001A000"  # G048=Utility Key 1, global
EVENT_STATUS1_ARMED     = "G064N000A001"  # G064=Status 1: Armed, area 1
EVENT_STATUS3_TAMPER    = "G066N004A255"  # G066=Status 3: Tamper, any area

# Edge cases
EVENT_ALL_ZERO          = "G000N000A000"  # minimum — zone 0 / all areas
EVENT_MAX_VALUES        = "G066N999A255"  # max group, max number, "any area"

# ---------------------------------------------------------------------------
# Virtual PGM events  (v1 scope: parsed but not acted on)
# ---------------------------------------------------------------------------

PGM_01_ON  = "PGM01ON"
PGM_30_ON  = "PGM30ON"
PGM_01_OFF = "PGM01OFF"
PGM_30_OFF = "PGM30OFF"

# ---------------------------------------------------------------------------
# Convenience collections for replay / smoke tests
# ---------------------------------------------------------------------------

ALL_FIXTURES = [
    COMM_OK, COMM_FAIL,
    BUFFER_FULL,
    AREA_DISARMED, AREA_ARMED_AWAY, AREA_ARMED_FORCE, AREA_ARMED_STAY,
    AREA_ARMED_INSTANT, AREA_ARMED_MEMORY, AREA_ARMED_ALARM_STROBE,
    AREA_ARMED_ALARM, AREA_STAY_TROUBLE, AREA_IN_PROGRAMMING,
    AREA_ALL_FLAGS, AREA_MAX_NUMBER,
    ZONE_CLOSED_OK, ZONE_OPEN_OK, ZONE_TAMPERED, ZONE_FIRE_LOOP,
    ZONE_ALARM, ZONE_FIRE_ALARM, ZONE_SUPERVISION, ZONE_LOW_BATTERY,
    ZONE_ALL_FLAGS, ZONE_MAX_NUMBER,
    ZONE_LABEL_FRONT_DOOR, ZONE_LABEL_BACK_DOOR, ZONE_LABEL_MAX_ZONE,
    AREA_LABEL_HOME, AREA_LABEL_MAX_AREA, USER_LABEL_MASTER, USER_LABEL_MAX_USER,
    ECHO_ARM_OK, ECHO_QUICK_ARM_OK, ECHO_DISARM_OK,
    ECHO_PANIC_EMERG_OK, ECHO_PANIC_MED_OK, ECHO_PANIC_FIRE_OK,
    ECHO_UTILITY_KEY_OK, ECHO_ARM_FAIL, ECHO_DISARM_FAIL,
    ECHO_STATUS_FAIL, ECHO_LABEL_FAIL,
    EVENT_ZONE_OK, EVENT_ZONE_OPEN, EVENT_ZONE_TAMPER, EVENT_ARM_USER,
    EVENT_DISARM_USER, EVENT_ZONE_ALARM, EVENT_FIRE_ALARM, EVENT_TROUBLE_AC,
    EVENT_POWER_UP, EVENT_UTILITY_KEY, EVENT_STATUS1_ARMED,
    EVENT_STATUS3_TAMPER, EVENT_ALL_ZERO, EVENT_MAX_VALUES,
    PGM_01_ON, PGM_30_ON, PGM_01_OFF, PGM_30_OFF,
]
