import pytest
import asyncio
from construct import Container
from paradox.lib.async_message_manager import AsyncMessageManager, RAWMessageHandler, EventMessageHandler


@pytest.mark.asyncio
async def test_persistent_raw_handler(mocker):
    cb = mocker.MagicMock()
    msg = Container()

    handler = RAWMessageHandler(cb)

    mm = AsyncMessageManager()
    mm.register_handler(handler)

    assert len(mm.raw_handlers) == 1

    task1 = mm.schedule_raw_message_handling(msg)
    await task1
    task2 = mm.schedule_raw_message_handling(msg)
    await task2

    assert cb.call_count == 2
    cb.assert_has_calls([mocker.call(msg), mocker.call(msg)])

    assert len(mm.raw_handlers) == 1


@pytest.mark.asyncio
async def test_raw_handler_register_unregister(mocker):
    cb = mocker.MagicMock()
    msg = Container()

    h_name = 'removable'
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

    task1 = loop.create_task(mm.wait_for_message(raw=True))
    mm.schedule_raw_message_handling(msg)

    assert await task1 == msg

    assert len(mm.raw_handlers) == 0
    assert len(mm.handlers) == 0


@pytest.mark.asyncio
async def test_wait_for_message(mocker):
    loop = asyncio.get_event_loop()
    msg = Container()

    mm = AsyncMessageManager()

    task1 = loop.create_task(mm.wait_for_message())
    mm.schedule_message_handling(msg)

    assert await task1 == msg

    assert len(mm.raw_handlers) == 0
    assert len(mm.handlers) == 0


@pytest.mark.asyncio
async def test_handler_exception(mocker):
    loop = asyncio.get_event_loop()
    msg = Container(
        fields=Container(
            value=Container(
                po=Container(
                    command=0xe
                ),
                event_source=0xff
            )
        )
    )

    mm = AsyncMessageManager()
    eh = EventMessageHandler(callback=mocker.MagicMock(side_effect=Exception('screw it')))
    mm.register_handler(eh)

    with pytest.raises(Exception):
        await mm.schedule_message_handling(msg)

    assert len(mm.raw_handlers) == 0
    assert len(mm.handlers) == 1
