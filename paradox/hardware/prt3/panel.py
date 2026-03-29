"""
PRT3Panel — Panel adapter for the Paradox PRT3 Printer Module.

Subclasses Panel (paradox.hardware.panel.Panel) and implements all
panel-facing methods using the PRT3 ASCII protocol instead of binary
EEPROM reads.

The Panel base class is not abstract in the strict sense — it provides
fallback implementations for most methods.  PRT3Panel overrides the ones
that would otherwise silently do nothing or crash on binary assumptions.

Design constraints:
  - Zone bypass has no PRT3 command; control_zones() raises NotImplementedError.
  - PGM / output control has no PRT3 command; control_outputs() raises
    NotImplementedError.
  - EEPROM reads are not available via PRT3; load_definitions() returns {}.

TODO (Phase 2): Implement initialize_communication() — await COMM&ok.
TODO (Phase 2): Implement load_labels() — send AL/ZL/UL requests, collect replies.
TODO (Phase 2): Implement request_status() — send RA/RZ requests, return flat dict.
TODO (Phase 3): Implement get_status_requests() — return list of coroutines.
TODO (Phase 3): Implement parse_message() for PRT3 lines (delegate to parser.py).
TODO (Phase 3): Implement send_panic() using PE/PM/PF commands.
TODO (Phase 3): Implement control_partitions() using AA/AQ/AD commands.
"""

import logging

from paradox.hardware.panel import Panel
from paradox.hardware.prt3.property import property_map

logger = logging.getLogger("PAI").getChild(__name__)


class PRT3Panel(Panel):
    """
    Panel implementation for the PRT3 ASCII serial interface.

    Uses ASCII RA/RZ/AL/ZL/UL commands for status and labels, and
    AA/AQ/AD/PE/PM/PF commands for control.  All EEPROM-based operations
    from the base Panel class are replaced.
    """

    property_map = property_map  # re-exported from spectra_magellan

    def __init__(self, core):
        # variable_message_length=False: PRT3Protocol.variable_message_length()
        # is a no-op, so we don't need the base class to manage lengths.
        super().__init__(core, variable_message_length=False)

    # ------------------------------------------------------------------
    # Startup handshake
    # ------------------------------------------------------------------

    async def initialize_communication(self, password) -> bool:
        """
        Wait for COMM&ok from the panel, then optionally verify the connection.

        The PRT3 module sends 'COMM&ok\\r' shortly after power-on or reconnect.
        There is no password exchange in the PRT3 protocol; the ``password``
        argument is accepted for interface compatibility but is not used.

        TODO (Phase 2): Await COMM&ok via the reply queue with a timeout.
        """
        raise NotImplementedError(
            "PRT3Panel.initialize_communication() not yet implemented — see Phase 2"
        )

    # ------------------------------------------------------------------
    # Label loading
    # ------------------------------------------------------------------

    async def load_labels(self) -> dict:
        """
        Request area, zone, and user labels via AL/ZL/UL ASCII commands.

        Sends AL{nnn}, ZL{nnn}, UL{nnn} for each index in range, collects
        replies, and returns a dict compatible with Paradox._on_labels_load().

        TODO (Phase 2): Implement label request/reply loop.
        """
        raise NotImplementedError(
            "PRT3Panel.load_labels() not yet implemented — see Phase 2"
        )

    async def load_definitions(self) -> dict:
        # PRT3 provides no EEPROM access; definitions are not available.
        return {}

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------

    async def request_status(self, nr: int):
        """
        Poll area and zone status via RA/RZ ASCII commands.

        Returns a flat dict in the format expected by convert_raw_status():
            {
                'zone_open':   {1: bool, 2: bool, ...},
                'zone_alarm':  {1: bool, ...},
                'partition_arm': {1: bool, ...},
                ...
            }

        TODO (Phase 2): Send RA/RZ requests, parse replies, return flat dict.
        """
        raise NotImplementedError(
            "PRT3Panel.request_status() not yet implemented — see Phase 2"
        )

    # ------------------------------------------------------------------
    # Control — partitions
    # ------------------------------------------------------------------

    async def control_partitions(self, partitions: list, command: str) -> bool:
        """
        Arm or disarm partitions using AA/AQ/AD ASCII commands.

        TODO (Phase 3): Map PAI command strings ('arm', 'arm_stay', 'disarm', …)
        to PRT3 encoder calls.
        """
        raise NotImplementedError(
            "PRT3Panel.control_partitions() not yet implemented — see Phase 3"
        )

    # ------------------------------------------------------------------
    # Control — zones (not supported by PRT3)
    # ------------------------------------------------------------------

    async def control_zones(self, zones: list, command: str) -> bool:
        raise NotImplementedError(
            "PRT3 has no zone bypass command — control_zones() is not supported"
        )

    # ------------------------------------------------------------------
    # Control — outputs (not supported by PRT3)
    # ------------------------------------------------------------------

    async def control_outputs(self, outputs, command) -> bool:
        raise NotImplementedError(
            "PRT3 has no PGM output command — control_outputs() is not supported"
        )

    # ------------------------------------------------------------------
    # Panic
    # ------------------------------------------------------------------

    async def send_panic(self, partition: int, panic_type: str, _code) -> bool:
        """
        Send a PE/PM/PF panic command.

        TODO (Phase 3): Map panic_type ('emergency', 'medical', 'fire') to
        encoder calls.
        """
        raise NotImplementedError(
            "PRT3Panel.send_panic() not yet implemented — see Phase 3"
        )

    # ------------------------------------------------------------------
    # Message parsing (delegated to parser.py)
    # ------------------------------------------------------------------

    def parse_message(self, message, direction="topanel"):
        """
        Parse a raw PRT3 ASCII line (bytes) into a typed PRT3Message.

        TODO (Phase 2): Decode bytes, strip \\r, delegate to parser.parse_line().
        """
        raise NotImplementedError(
            "PRT3Panel.parse_message() not yet implemented — see Phase 2"
        )
