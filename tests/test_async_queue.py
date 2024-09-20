import asyncio
import binascii
from unittest import mock

from construct import Container
import pytest

from paradox.hardware.evo.parsers import LiveEvent, ReadEEPROMResponse
from paradox.lib.async_message_manager import AsyncMessageManager
from paradox.lib.handlers import PersistentHandler


class EventMessageHandler(PersistentHandler):
    def can_handle(self, message):
        return message.fields.value.po.command == 0xE


def print_beer(m):
    print("beer")


@pytest.mark.asyncio
async def test_event_handler():
    eh = EventMessageHandler(print_beer)

    mh = AsyncMessageManager()
    mh.register_handler(eh)

    assert 1 == len(mh.handler_registry)

    payload = b"\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc"

    message = LiveEvent.parse(payload)

    await mh.schedule_message_handling(message)

    assert 1 == len(mh.handler_registry)


@pytest.mark.asyncio
async def test_event_handler_failure():
    # eeprom_request_bin = binascii.unhexlify('500800009f004037')
    eeprom_response_bin = binascii.unhexlify(
        "524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e85"
    )

    eh = EventMessageHandler(print_beer)
    eh.handle = mock.MagicMock()

    mh = AsyncMessageManager()
    mh.register_handler(eh)

    assert 1 == len(mh.handler_registry)

    message = ReadEEPROMResponse.parse(eeprom_response_bin)

    coro = mh.schedule_message_handling(message)
    result = await coro
    assert (
        result is None
    )  # failed to parse response message return None. Maybe needs to throw something.

    assert 1 == len(mh.handler_registry)
    eh.handle.assert_not_called()


async def test_handler_two_messages():
    def event_handler(message):
        print("event")

    async def get_eeprom_result(mhm):
        return await mhm.wait_for_message(lambda m: m.fields.value.po.command == 0x5)

    event_response_bin = b"\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc"

    eeprom_response_bin = binascii.unhexlify(
        "524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e85"
    )

    mh = AsyncMessageManager()

    event_handler = EventMessageHandler(event_handler)
    mh.register_handler(event_handler)

    # running
    task_handle_wait = asyncio.create_task(asyncio.sleep(0.1))
    task_get_eeprom = asyncio.create_task(get_eeprom_result(mh))
    task_handle_event1 = mh.schedule_message_handling(
        LiveEvent.parse(event_response_bin)
    )
    mh.schedule_message_handling(ReadEEPROMResponse.parse(eeprom_response_bin))
    mh.schedule_message_handling(LiveEvent.parse(event_response_bin))

    await asyncio.gather(task_handle_wait, task_get_eeprom)

    assert 1 == len(mh.handler_registry)

    assert task_handle_event1.done()
    assert isinstance(task_get_eeprom.result(), Container)

    assert 1 == len(mh.handler_registry)


@pytest.mark.asyncio
async def test_handler_timeout():
    def event_handler(message):
        print("event received")

    async def get_eeprom_result(mhm):
        return await mhm.wait_for_message(
            lambda m: m.fields.value.po.command == 0x5, timeout=0.1
        )

    async def post_eeprom_message(mhm):
        await asyncio.sleep(0.2)

        eeprom_response_bin = binascii.unhexlify(
            "524700009f0041133e001e0e0400000000060a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000121510010705004e85"
        )

        return await mhm.schedule_message_handling(
            ReadEEPROMResponse.parse(eeprom_response_bin)
        )

    mh = AsyncMessageManager()

    # running
    task_get_eeprom = asyncio.create_task(get_eeprom_result(mh))
    asyncio.create_task(post_eeprom_message(mh))

    assert 0 == len(mh.handler_registry)

    with pytest.raises(asyncio.TimeoutError):
        await task_get_eeprom

    assert 0 == len(mh.handler_registry)

    # Also test EventMessageHandler
    event_handler_instance = EventMessageHandler(event_handler)
    mh.register_handler(event_handler_instance)

    event_response_bin = b"\xe2\xff\xad\x06\x14\x13\x01\x04\x0e\x10\x00\x01\x05\x00\x00\x00\x00\x00\x02Living room     \x00\xcc"
    task_handle_event1 = mh.schedule_message_handling(
        LiveEvent.parse(event_response_bin)
    )

    assert 1 == len(mh.handler_registry)

    await task_handle_event1

    assert 1 == len(mh.handler_registry)
