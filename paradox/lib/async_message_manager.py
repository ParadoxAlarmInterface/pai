import asyncio
import logging
from typing import Awaitable, Optional, Callable

from construct import Container

logger = logging.getLogger('PAI').getChild(__name__)


class FutureMessageHandler(asyncio.Future):
    def __init__(self, check_fn=None, loop=None, name=None):
        super(FutureMessageHandler, self).__init__(loop=loop)
        self.persistent = False
        self._check_fn = check_fn
        self.name = name if name is not None else self.__class__.__name__

    def can_handle(self, message: Container) -> bool:
        if isinstance(self._check_fn, Callable):
            return self._check_fn(message)
        return True


class RawFutureMessageHandler(FutureMessageHandler):
    pass


class MessageHandler:
    # handle: Callable

    def __init__(self, callback, name=None):
        self.persistent = False
        self.handle = callback
        self.name = name if name is not None else self.__class__.__name__

    def can_handle(self, message: Container) -> bool:
        return True


class RAWMessageHandler(MessageHandler):
    def __init__(self, callback, name=None):
        super(RAWMessageHandler, self).__init__(callback, name)
        self.persistent = True
        self.name = name if name is not None else self.__class__.__name__


class EventMessageHandler(MessageHandler):
    def __init__(self, callback, name=None):
        super(EventMessageHandler, self).__init__(callback, name)
        self.persistent = True
        self.name = name if name is not None else self.__class__.__name__

    def can_handle(self, message: Container) -> bool:
        values = message.fields.value
        return values.po.command == 0xe and (not hasattr(values, "event_source") or values.event_source == 0xff)


class ErrorMessageHandler(MessageHandler):
    def __init__(self, callback, name=None):
        super(ErrorMessageHandler, self).__init__(callback, name)
        self.persistent = True
        self.name = name if name is not None else self.__class__.__name__

    def can_handle(self, message: Container) -> bool:
        return message.fields.value.po.command == 0x7 and hasattr(message.fields.value, "message")


class AsyncMessageManager:
    # handlers: List[MessageHandler]

    def __init__(self, loop = None):
        super(AsyncMessageManager, self).__init__()

        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop

        self.handlers = []
        self.raw_handlers = []

    async def wait_for_message(self, check_fn=None, timeout=2, raw=False) -> Optional[Container]:
        if raw:
            future = RawFutureMessageHandler(loop=self.loop)
        else:
            future = FutureMessageHandler(check_fn, loop=self.loop)

        self.register_handler(future)

        return await asyncio.wait_for(future, timeout=timeout, loop=self.loop)

    def register_handler(self, handler):
        if isinstance(handler, (RAWMessageHandler, RawFutureMessageHandler,)):
            self.raw_handlers.append(handler)
        else:
            self.handlers.append(handler)

    def deregister_handler(self, name):
        self.handlers = list(filter(lambda x: x.name != name, self.handlers))
        self.raw_handlers = list(filter(lambda x: x.name != name, self.raw_handlers))

    def schedule_message_handling(self, message: Container):
        return self.loop.create_task(self._handle_message(message))

    def schedule_raw_message_handling(self, message):
        return self.loop.create_task(self._handle_raw_message(message))

    async def _handle_raw_message(self, message: Container):
        self.raw_handlers = self._cleanup_handlers(self.raw_handlers)

        for handler in self.raw_handlers:
            if not handler.can_handle(message):
                continue

            if not handler.persistent:
                self.raw_handlers = list(filter(lambda x: x != handler, self.raw_handlers))

            await self._handle(handler, message)

    async def _handle_message(self, message: Container):
        handler = None

        self.handlers = self._cleanup_handlers(self.handlers)

        for h in self.handlers:
            try:
                if h.can_handle(message):
                    handler = h
                    break
            except Exception as e:
                logger.exception("Exception caught during message handling")

        if handler:
            if not handler.persistent:
                self.handlers = list(filter(lambda x: x != handler, self.handlers))

            return await self._handle(handler, message)
        else:
            logger.error("No handler for message {}\nDetail: {}".format(message.fields.value.po.command, message))

    @staticmethod
    async def _handle(handler, message):
        if isinstance(handler, asyncio.Future):
            handler.set_result(message)
            return await handler
        else:
            result = handler.handle(message)
            if isinstance(result, Awaitable):
                return await result
            else:
                return result

    @staticmethod
    def _cleanup_handlers(handlers):
        return list(filter(lambda x: not (isinstance(x, asyncio.Future) and x.done()),
                    handlers))  # remove timeouted and done futures
