"""
PRT3SerialConnection — serial transport for the Paradox PRT3 Printer Module.

Inherits all of SerialCommunication's robust serial-open logic
(permission fix, 5-second timeout, connected_future pattern) and only
overrides make_protocol() to return PRT3Protocol instead of the binary
SerialConnectionProtocol.
"""

import logging

from paradox.connections.serial_connection import SerialCommunication
from paradox.connections.prt3.protocol import PRT3Protocol

logger = logging.getLogger("PAI").getChild(__name__)


class PRT3SerialConnection(SerialCommunication):
    """
    Serial transport for the PRT3 ASCII interface.

    Identical to SerialCommunication except it uses PRT3Protocol for
    line-delimited ASCII framing instead of the binary nibble-pattern framer.
    """

    def make_protocol(self) -> PRT3Protocol:
        return PRT3Protocol(self)
