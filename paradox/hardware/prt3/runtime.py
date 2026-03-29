"""
PRT3Paradox — Paradox subclass for the PRT3 ASCII connection type.

Overrides connect() and the connection message handler to implement the
PRT3-specific handshake and reply routing.

Why a subclass of Paradox and not a modified Paradox.connect():
  - Paradox.connect() assumes binary panel detection (InitiateCommunication /
    StartCommunication), which does not exist in PRT3.
  - The binary HandlerRegistry calls data.fields.value.po.command on every
    unhandled message; PRT3 messages are plain dataclasses that have no such
    attribute — routing them through the registry would crash.
  - Keeping the override here avoids adding PRT3-specific branches throughout
    the base class.

Reply routing:
  All PRT3 replies (echoes, status, labels) are routed through
  _prt3_reply_queue (asyncio.Queue).  Callers in panel.py await items from
  this queue rather than registering HandlerRegistry entries.

TODO (Phase 2): Implement connect() — await COMM&ok, instantiate PRT3Panel,
  call load_labels() and kick off status polling loop.
TODO (Phase 2): Implement on_connection_message() — parse incoming ASCII line,
  put result into _prt3_reply_queue.
TODO (Phase 3): Implement _register_connection_handlers() — register only the
  raw handler; skip EventMessageHandler and ErrorMessageHandler (binary only).
"""

import asyncio
import logging

from paradox.paradox import Paradox
from paradox.hardware.prt3.panel import PRT3Panel

logger = logging.getLogger("PAI").getChild(__name__)


class PRT3Paradox(Paradox):
    """
    Paradox orchestrator subclass for the PRT3 ASCII interface.

    Callers that set CONNECTION_TYPE = 'PRT3' should instantiate this
    class rather than the base Paradox class.

    TODO (Phase 2): Replace the NotImplementedError stubs below with
    working implementations.
    """

    def __init__(self, retries=3):
        super().__init__(retries=retries)
        # Queue used to route PRT3 reply lines back to awaiting callers
        # in PRT3Panel without going through HandlerRegistry (which would
        # crash on the missing .fields.value.po.command attribute).
        self._prt3_reply_queue: asyncio.Queue = asyncio.Queue()

    def _register_connection_handlers(self):
        """
        Register only the raw message handler for PRT3.

        The base class also registers EventMessageHandler and
        ErrorMessageHandler, which access binary Container fields.
        PRT3 messages must never reach those handlers.

        TODO (Phase 3): Register PersistentHandler(self.on_connection_message) only.
        """
        raise NotImplementedError(
            "PRT3Paradox._register_connection_handlers() not yet implemented — see Phase 3"
        )

    async def connect(self) -> bool:
        """
        PRT3-specific connection sequence:

          1. Open the serial port (inherited serial_asyncio logic).
          2. Wait for COMM&ok\\r from the panel (timeout 30 s).
          3. Instantiate PRT3Panel.
          4. Call panel.load_labels() to populate storage.
          5. Set run_state = CONNECTED and return True.

        There is no InitiateCommunication / StartCommunication binary exchange.

        TODO (Phase 2): Implement this method.
        """
        raise NotImplementedError(
            "PRT3Paradox.connect() not yet implemented — see Phase 2"
        )

    def on_connection_message(self, message: bytes):
        """
        Receive a raw \\r-stripped ASCII line from PRT3Protocol.

        Parses the line via parser.parse_line() and routes the result:
          - PRT3CommStatus   → handle connect/disconnect state
          - PRT3CommandEcho  → put in _prt3_reply_queue
          - PRT3AreaStatus   → put in _prt3_reply_queue
          - PRT3ZoneStatus   → put in _prt3_reply_queue
          - PRT3LabelReply   → put in _prt3_reply_queue
          - PRT3SystemEvent  → publish to ps 'events' topic

        TODO (Phase 2): Implement this method.
        """
        raise NotImplementedError(
            "PRT3Paradox.on_connection_message() not yet implemented — see Phase 2"
        )
