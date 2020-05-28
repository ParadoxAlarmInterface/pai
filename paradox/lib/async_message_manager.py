import asyncio
import logging
from abc import abstractmethod
from typing import Awaitable, Callable, List, Optional

from construct import Container

logger = logging.getLogger("PAI").getChild(__name__)


class MessageHandler:
    def __init__(self, name=None):
        super().__init__()
        self.persistent = False
        self.name = name if name is not None else self.__class__.__name__

    def can_handle(self, message: Container) -> bool:
        return True

    @abstractmethod
    async def __call__(self, message: Container):
        """
        Handle message
        :param message:
        :return:
        """


class AlreadyHandledError(Exception):
    pass


class FutureMessageHandler(MessageHandler, asyncio.Future):
    def __init__(
        self, check_fn: Optional[Callable[[Container], bool]] = None, name=None,
    ):
        super().__init__()
        self.name = name if name is not None else self.__class__.__name__
        self._check_fn = check_fn

    def can_handle(self, message: Container) -> bool:
        if self.done():
            raise AlreadyHandledError()
        if isinstance(self._check_fn, Callable):
            return self._check_fn(message)
        return True

    async def __call__(self, message: Container):
        self.set_result(message)

        return message


class PersistentMessageHandler(MessageHandler):
    def __init__(self, callback: Callable[[Container], None], name=None):
        super(PersistentMessageHandler, self).__init__(name)
        self._handle = callback
        self.persistent = True

    async def __call__(self, message: Container):
        result = self._handle(message)

        if isinstance(result, Awaitable):
            return await result
        else:
            return result


class EventMessageHandler(PersistentMessageHandler):
    def can_handle(self, message: Container) -> bool:
        values = message.fields.value
        return values.po.command == 0xE and (
            not hasattr(values, "event_source") or values.event_source == 0xFF
        )


class ErrorMessageHandler(PersistentMessageHandler):
    def can_handle(self, message: Container) -> bool:
        return message.fields.value.po.command == 0x7 and hasattr(
            message.fields.value, "message"
        )


class HandlerRegistry:
    def __init__(self):
        self.handlers: List[MessageHandler] = []

    def append(self, handler: MessageHandler):
        self.handlers.append(handler)

    def remove(self, handler: MessageHandler):
        self.handlers.remove(handler)

    def remove_by_name(self, name):
        to_remove = filter(lambda x: x.name == name, self.handlers)
        for handler in to_remove:
            self.remove(handler)

    async def wait_until_complete(self, handler: MessageHandler, timeout=2):
        self.append(handler)
        try:
            return await asyncio.wait_for(handler, timeout=timeout)
        finally:
            assert not handler.persistent
            self.remove(handler)

    async def handle(self, message: Container):
        """
        Find handler for inbound message and handle it.
        :param message:
        :return:
        """
        handled = False
        for handler in self.handlers:
            try:
                if handler.can_handle(message):
                    handled = True
                    await handler(message)
            except AlreadyHandledError:
                logger.error("Already handled")
            except:
                logger.exception("Exception caught during message handling")
                raise

        if not handled:
            logger.error(
                "No handler for message {}\nDetail: {}".format(
                    message.fields.value.po.command, message
                )
            )


class AsyncMessageManager:
    def __init__(self, loop=None):
        super(AsyncMessageManager, self).__init__()

        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop

        self.handler_registry = HandlerRegistry()

    async def wait_for_message(
        self, check_fn: Optional[Callable[[Container], bool]] = None, timeout=2
    ) -> Container:
        return await self.handler_registry.wait_until_complete(
            FutureMessageHandler(check_fn), timeout
        )

    def register_handler(self, handler):
        self.handler_registry.append(handler)

    def deregister_handler(self, name):
        self.handler_registry.remove_by_name(name)

    def schedule_message_handling(self, message: Container):
        return self.loop.create_task(self.handler_registry.handle(message))
