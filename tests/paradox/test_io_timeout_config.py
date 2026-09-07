"""IO_TIMEOUT has to be read at call time, not frozen into a default argument.

``pai_run`` imports ``paradox.main`` -- and through it ``paradox.paradox``,
``paradox.lib.handlers`` and the IP connection -- before ``main()`` calls
``cfg.load()``. A ``timeout=cfg.IO_TIMEOUT`` default argument is evaluated at
import time, so every request path silently kept the built-in 0.5 s no matter
what the user configured, and raising IO_TIMEOUT to cope with a slow link did
nothing at all.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from paradox.config import config as cfg
from paradox.lib.handlers import FutureHandler, HandlerRegistry
from paradox.paradox import Paradox


@pytest.mark.asyncio
async def test_send_wait_uses_the_configured_timeout(mocker, monkeypatch):
    monkeypatch.setattr(cfg, "IO_TIMEOUT", 7.0)

    alarm = Paradox()
    alarm._connection = mocker.Mock()
    alarm._connection.connected = True
    alarm._connection.wait_for_message = AsyncMock(return_value="reply")

    assert await alarm.send_wait(message=b"x", reply_expected=0x1) == "reply"

    # send_wait allows a reply twice the configured IO timeout.
    assert alarm._connection.wait_for_message.await_args.kwargs["timeout"] == 14.0


@pytest.mark.asyncio
async def test_wait_until_complete_uses_the_configured_timeout(monkeypatch):
    monkeypatch.setattr(cfg, "IO_TIMEOUT", 0.01)

    registry = HandlerRegistry()

    with pytest.raises(asyncio.TimeoutError):
        await registry.wait_until_complete(FutureHandler())

    # The handler is removed even when the wait times out.
    assert len(registry) == 0
