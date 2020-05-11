import asyncio

import pytest
from construct import Container

from paradox.lib.async_message_manager import (AsyncMessageManager,
                                               EventMessageHandler,
                                               RAWMessageHandler)


@pytest.mark.asyncio
async def test_persistent_raw_handler(mocker):
    cb = mocker.MagicMock()
    msg1 = Container()
    msg2 = Container()

    handler = RAWMessageHandler(cb)

    mm = AsyncMessageManager()
    mm.register_handler(handler)

    assert len(mm.raw_handlers) == 1

    task1 = mm.schedule_raw_message_handling(msg1)
    await task1
    task2 = mm.schedule_raw_message_handling(msg2)
    await task2

    assert task1.done()
    assert task2.done()

    assert cb.call_count == 2
    cb.assert_has_calls([mocker.call(msg1), mocker.call(msg2)])

    assert len(mm.raw_handlers) == 1


@pytest.mark.asyncio
async def test_raw_handler_register_unregister(mocker):
    cb = mocker.MagicMock()
    msg = Container()

    h_name = "removable"
    handler = RAWMessageHandler(cb, name=h_name)

    mm = AsyncMessageManager()
    mm.register_handler(handler)

    assert len(mm.raw_handlers) == 1

    mm.deregister_handler(h_name)

    assert len(mm.raw_handlers) == 0


@pytest.mark.asyncio
async def test_wait_for_raw_message(mocker):
    loop = asyncio.get_event_loop()
    msg = Container()

    mm = AsyncMessageManager()

    task1 = loop.create_task(mm.wait_for_raw_message())
    s = mm.schedule_raw_message_handling(msg)

    assert await task1 == msg
    assert task1.done()
    assert s.done()

    assert len(mm.raw_handlers) == 0
    assert len(mm.handlers) == 0


@pytest.mark.asyncio
async def test_wait_for_message(mocker):
    loop = asyncio.get_event_loop()
    msg = Container()

    mm = AsyncMessageManager()

    task1 = loop.create_task(mm.wait_for_message())
    s = mm.schedule_message_handling(msg)

    assert await task1 == msg
    assert task1.done()
    assert s.done()

    assert len(mm.raw_handlers) == 0
    assert len(mm.handlers) == 0


@pytest.mark.asyncio
async def test_handler_exception(mocker):
    loop = asyncio.get_event_loop()
    msg = Container(
        fields=Container(value=Container(po=Container(command=0xE), event_source=0xFF))
    )

    mm = AsyncMessageManager()
    eh = EventMessageHandler(
        callback=mocker.MagicMock(side_effect=Exception("screw it"))
    )
    mm.register_handler(eh)

    with pytest.raises(Exception):
        await mm.schedule_message_handling(msg)

    assert len(mm.raw_handlers) == 0
    assert len(mm.handlers) == 1
