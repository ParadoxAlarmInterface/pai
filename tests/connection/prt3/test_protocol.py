"""
Smoke tests for paradox.connections.prt3.

These tests verify that the module graph imports cleanly and that the
scaffolded classes are importable and have the expected type hierarchy.
Protocol logic tests will be added in Phase 2.
"""

from paradox.connections.prt3.protocol import PRT3Protocol
from paradox.connections.prt3.connection import PRT3SerialConnection
from paradox.connections.protocols import ConnectionProtocol
from paradox.connections.serial_connection import SerialCommunication


def test_prt3_protocol_is_connection_protocol():
    """PRT3Protocol must inherit from ConnectionProtocol."""
    assert issubclass(PRT3Protocol, ConnectionProtocol)


def test_prt3_serial_connection_is_serial_communication():
    """PRT3SerialConnection must inherit from SerialCommunication."""
    assert issubclass(PRT3SerialConnection, SerialCommunication)


def test_prt3_serial_connection_make_protocol_returns_prt3_protocol():
    """make_protocol() must return a PRT3Protocol instance."""
    # We cannot open a real serial port in tests; pass a fake port path
    # and a dummy handler.  make_protocol() is a synchronous factory that
    # just calls PRT3Protocol(self), so no I/O occurs.
    conn = PRT3SerialConnection.__new__(PRT3SerialConnection)
    proto = conn.make_protocol()
    assert isinstance(proto, PRT3Protocol)
