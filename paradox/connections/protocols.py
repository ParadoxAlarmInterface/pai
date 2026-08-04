"""Deprecated location. Framing now lives in the per-transport packages.

Kept so external code and older configurations keep importing successfully.
"""

from paradox.connections.ip.protocol import IPConnectionProtocol  # noqa: F401
from paradox.connections.protocol_base import ConnectionProtocol  # noqa: F401
from paradox.connections.serial.protocol import (  # noqa: F401
    SerialConnectionProtocol,
)
