"""Paradox Digiplex panel support (DGP-48 / DGP-848 / DGP-NE96).

See ``parsers`` for the protocol details. This family is the reason for
ParadoxAlarmInterface/pai#257: Digiplex panels ignore InitiateCommunication
(0x72) and only answer to StartCommunication (0x5F) with ``source_id=0``.
"""

from .panel import Panel_DGP848

__all__ = ["Panel_DGP848"]
