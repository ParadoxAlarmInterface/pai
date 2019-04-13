import asyncio
import logging
from typing import Awaitable

logger = logging.getLogger('PAI').getChild(__name__)


class MessageHandler:
    # handle: Callable

    def __init__(self, callback):
        self.persistent = False
        self.handle = callback

    def can_handle(self, message):
        return True


class FutureMessageHandler(asyncio.Future):
    def __init__(self, check_fn=lambda m: True, loop=None):
        super(FutureMessageHandler, self).__init__(loop=loop)
        self.persistent = False
        self.can_handle = check_fn


class EventMessageHandler(MessageHandler):
    def __init__(self, callback):
        super(EventMessageHandler, self).__init__(callback)
        self.persistent = True

    def can_handle(self, message):
        return message.fields.value.po.command == 0xe


class ErrorMessageHandler(MessageHandler):
    def __init__(self, callback):
        super(ErrorMessageHandler, self).__init__(callback)
        self.persistent = True

    def can_handle(self, message):
        return message.fields.value.po.command == 0x7 and hasattr(message.fields.value, "message")


class AsyncMessageManager:
    # handlers: List[MessageHandler]

    def __init__(self, loop=asyncio.get_event_loop()):
        super(AsyncMessageManager, self).__init__()
        self.loop = loop

        self.handlers = []

    async def wait_for(self, check_fn, timeout=2):
        future = FutureMessageHandler(check_fn, loop=self.loop)
        self.register_handler(future)

        try:
            return await asyncio.wait_for(future, timeout=timeout, loop=self.loop)
        except asyncio.TimeoutError:
            return None

    def register_handler(self, handler):
        self.handlers.append(handler)

    def schedule_message_handling(self, message):
        return self.loop.create_task(self.handle_message(message))

    async def handle_message(self, message):
        handler = None

        self.handlers = list(filter(lambda x: not (isinstance(x, asyncio.Future) and x.cancelled()),
                                    self.handlers))  # remove timeouted futures
        # TODO: improve performance

        for h in self.handlers:
            try:
                if h.can_handle(message):
                    handler = h
                    break
            except Exception:
                pass

        if handler:
            if not handler.persistent:
                self.handlers = list(filter(lambda x: x != handler, self.handlers))

            if isinstance(handler, asyncio.Future):
                handler.set_result(message)
                return await handler
            else:
                result = handler.handle(message)
                if isinstance(result, Awaitable):
                    return await result
                else:
                    return result
        else:
            logger.error("No handler for message {}\nDetail: {}".format(message.fields.value.po.command, message))
