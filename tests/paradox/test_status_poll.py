"""The status poll cycle must be bounded and self-contained.

``Paradox.loop`` polls every RAM status address once per ``KEEP_ALIVE_INTERVAL``.
The requests are serialised behind ``request_lock`` and ``send_wait`` retries
five times, so an unbounded cycle can outlive the interval by a wide margin --
publishing no status and counting no missing reply for the whole time.

``asyncio.gather`` makes that worse: it propagates the first failure but leaves
its siblings running, so the stragglers stay queued on ``request_lock`` and
collide with the next cycle's requests. One slow address then compounds into
cross-cycle contention instead of staying in its own cycle.
"""

import asyncio

import pytest

from paradox.config import config as cfg
from paradox.exceptions import StatusRequestException
from paradox.hardware import Panel
from paradox.hardware.prt3.panel import PRT3Panel
from paradox.paradox import Paradox


class _TenAddressPanel(Panel):
    status_request_addresses = list(range(10))


@pytest.mark.asyncio
async def test_poll_status_cancels_siblings_when_one_request_fails(mocker):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_sibling():
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def failing():
        await started.wait()
        raise StatusRequestException("no reply to status request: 1")

    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.get_status_requests.return_value = [slow_sibling(), failing()]

    with pytest.raises(StatusRequestException):
        await alarm._poll_status()

    await asyncio.wait_for(cancelled.wait(), 1)


@pytest.mark.asyncio
async def test_poll_status_keeps_the_blocks_that_did_parse(mocker):
    """``handle_status()`` returns None for a block it cannot parse.

    Passing that to ``deep_merge`` raises, which the loop logged as a generic
    error -- dropping the whole cycle, including the blocks that parsed fine,
    without counting a missing reply.
    """

    async def parsed():
        return {"zone": {1: {"open": True}}}

    async def unparsable():
        return None

    alarm = Paradox()
    alarm.panel = mocker.Mock(spec=Panel)
    alarm.panel.get_status_requests.return_value = [parsed(), unparsable()]

    assert await alarm._poll_status() == {"zone": {1: {"open": True}}}


def test_cycle_budget_covers_every_status_address(monkeypatch):
    monkeypatch.setattr(cfg, "IO_TIMEOUT", 1.0)
    monkeypatch.setattr(cfg, "KEEP_ALIVE_INTERVAL", 10)

    # Ten addresses, each allowed a reply window plus one retry.
    assert _TenAddressPanel(core=None).status_cycle_budget == 40.0


def test_cycle_budget_never_drops_below_the_keepalive_interval(monkeypatch):
    monkeypatch.setattr(cfg, "IO_TIMEOUT", 0.1)
    monkeypatch.setattr(cfg, "KEEP_ALIVE_INTERVAL", 30)

    assert _TenAddressPanel(core=None).status_cycle_budget == 30


def test_prt3_cycle_budget_covers_every_area_and_zone(monkeypatch):
    """PRT3 expands one virtual address into a request per area and zone.

    Sizing its budget from ``status_request_addresses`` -- a single entry --
    would cancel every cycle on a panel with a realistic zone count.
    """
    monkeypatch.setattr(cfg, "IO_TIMEOUT", 0.5)
    monkeypatch.setattr(cfg, "KEEP_ALIVE_INTERVAL", 10)
    monkeypatch.setattr(cfg, "PRT3_MAX_AREAS", 8)
    monkeypatch.setattr(cfg, "PRT3_MAX_ZONES", 96)

    assert PRT3Panel(core=None).status_cycle_budget == 104.0
