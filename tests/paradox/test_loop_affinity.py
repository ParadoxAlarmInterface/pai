"""Paradox is constructed before the event loop exists.

``paradox.main.main`` does ``asyncio.run(_run(Paradox()))`` and
``pai_dump_memory`` does ``alarm = Paradox()`` followed by ``asyncio.run(...)``.
In both cases ``Paradox.__init__`` runs while there is no running loop, and
``asyncio.run`` afterwards creates a *different* loop than the one
``asyncio.get_event_loop()`` would have returned at construction time.

On Python 3.8/3.9 ``asyncio.Lock()`` and ``asyncio.Event()`` capture
``get_event_loop()`` in ``__init__``, so primitives built that early stay bound
to a loop that never runs. Acquiring an *uncontended* lock never touches the
bound loop, so panel login and label loading work; the first *contended*
acquire calls ``self._loop.create_future()`` and raises

    RuntimeError: ... got Future <Future pending> attached to a different loop

which is exactly what ``Paradox.loop`` does via
``asyncio.gather(*self.panel.get_status_requests())`` -- turning every polling
cycle into a reconnect.
"""

import asyncio

import pytest

from paradox.paradox import Paradox


def _run_in_fresh_loop(coro_factory):
    """Mimic main(): build Paradox with no running loop, then asyncio.run().

    A fresh interpreter has a default loop that ``get_event_loop()`` creates on
    demand in the main thread; pytest-asyncio leaves none behind, so install one
    to reproduce what actually happens under ``pai_run``.
    """
    previous = asyncio.new_event_loop()
    asyncio.set_event_loop(previous)
    try:
        alarm = Paradox()
        return asyncio.run(coro_factory(alarm))
    finally:
        previous.close()
        asyncio.set_event_loop(None)


def test_request_lock_survives_contention_in_a_later_loop():
    async def contend(alarm):
        async def hold():
            async with alarm.request_lock:
                await asyncio.sleep(0)

        # Two waiters force the slow path in Lock.acquire(), which is the only
        # place the bound loop is used.
        await asyncio.gather(hold(), hold(), hold())
        return True

    assert _run_in_fresh_loop(contend)


def test_busy_lock_survives_contention_in_a_later_loop():
    async def contend(alarm):
        async def hold():
            await alarm.busy.acquire()
            try:
                await asyncio.sleep(0)
            finally:
                alarm.busy.release()

        await asyncio.gather(hold(), hold(), hold())
        return True

    assert _run_in_fresh_loop(contend)


def test_loop_wait_event_survives_waiting_in_a_later_loop():
    async def wait_for_event(alarm):
        async def setter():
            await asyncio.sleep(0)
            alarm.loop_wait_event.set()

        asyncio.ensure_future(setter())
        # Event.wait() always builds a future on the bound loop.
        await asyncio.wait_for(alarm.loop_wait_event.wait(), 5)
        return True

    assert _run_in_fresh_loop(wait_for_event)


@pytest.mark.asyncio
async def test_primitives_are_still_assignable():
    """Tests substitute their own primitives; keep that working."""
    alarm = Paradox()
    lock = asyncio.Lock()
    event = asyncio.Event()

    alarm.request_lock = lock
    alarm.busy = lock
    alarm.loop_wait_event = event

    assert alarm.request_lock is lock
    assert alarm.busy is lock
    assert alarm.loop_wait_event is event
