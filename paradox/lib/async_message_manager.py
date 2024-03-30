import asyncio
import logging
from typing import Callable, Optional

from construct import Container

from paradox.config import config as cfg
from paradox.lib.handlers import FutureHandler, HandlerRegistry, PersistentHandler

logger = logging.getLogger("PAI").getChild(__name__)


class EventMessageHandler(PersistentHandler):
    def can_handle(self, data: Container) -> bool:
        assert isinstance(data, Container)
        values = data.fields.value
        return values.po.command == 0xE and (not hasattr(values, "requested_event_nr"))


class ErrorMessageHandler(PersistentHandler):
    def can_handle(self, data: Container) -> bool:
        assert isinstance(data, Container)
        return data.fields.value.po.command == 0x7 and hasattr(
            data.fields.value, "message"
        )


class AsyncMessageManager:
    def __init__(self, loop=None):
        super().__init__()

        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop

        self.handler_registry = HandlerRegistry()
        self.raw_handler_registry = HandlerRegistry()

    async def wait_for_message(
        self,
        check_fn: Optional[Callable[[Container], bool]] = None,
        timeout=cfg.IO_TIMEOUT,
    ) -> Container:
        return await self.handler_registry.wait_until_complete(
            FutureHandler(check_fn), timeout
        )

    def register_raw_handler(self, handler):
        self.raw_handler_registry.append(handler)

    def deregister_raw_handler(self, name):
        self.raw_handler_registry.remove_by_name(name)

    def register_handler(self, handler):
        self.handler_registry.append(handler)

    def deregister_handler(self, name):
        self.handler_registry.remove_by_name(name)

    def schedule_message_handling(self, message: Container):
        return self.loop.create_task(self.handler_registry.handle(message))

    def schedule_raw_message_handling(self, message: Container):
        return self.loop.create_task(self.raw_handler_registry.handle(message))
