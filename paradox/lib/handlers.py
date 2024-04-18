from abc import abstractmethod
import asyncio
import logging
from typing import Any, Awaitable, Callable, List, Optional, Union

from paradox.config import config as cfg

logger = logging.getLogger("PAI").getChild(__name__)


class Handler:
    def __init__(self, name=None):
        super().__init__()
        self.persistent = False
        self.name = name if name is not None else self.__class__.__name__

    def can_handle(self, data) -> bool:
        return True

    @abstractmethod
    async def __call__(self, data):
        """
        Handle message
        :param message:
        :return:
        """


class AlreadyHandledError(Exception):
    pass


class FutureHandler(Handler, asyncio.Future):
    def __init__(
        self,
        check_fn: Optional[Callable[[Any], bool]] = None,
        name=None,
    ):
        super().__init__()
        self.name = name if name is not None else self.__class__.__name__
        self._check_fn = check_fn

    def can_handle(self, data) -> bool:
        if self.done():
            raise AlreadyHandledError()
        if isinstance(self._check_fn, Callable):
            return self._check_fn(data)
        return True

    async def __call__(self, data):
        self.set_result(data)

        return data


class PersistentHandler(Handler):
    def __init__(
        self, callback: Callable[[Any], Union[None, Awaitable[None]]], name=None
    ):
        super().__init__(name)
        self._handle = callback
        self.persistent = True

    async def __call__(self, data):
        result = self._handle(data)

        if isinstance(result, Awaitable):
            return await result
        else:
            return result


class HandlerRegistry:
    def __init__(self, should_ignore_no_handlers=False):
        self._handlers: List[Handler] = []
        self._should_ignore_no_handlers = should_ignore_no_handlers

    def __len__(self):
        return len(self._handlers)

    def set_ignore_if_no_handlers(self, value):
        self._should_ignore_no_handlers = value

    def append(self, handler: Handler):
        assert isinstance(handler, Handler)
        self._handlers.append(handler)

    def remove(self, handler: Handler):
        assert isinstance(handler, Handler)
        self._handlers.remove(handler)

    def remove_by_name(self, name: str):
        to_remove = filter(lambda x: x.name == name, self._handlers)
        for handler in to_remove:
            self.remove(handler)

    async def wait_until_complete(self, handler: Handler, timeout=cfg.IO_TIMEOUT):
        self.append(handler)
        try:
            return await asyncio.wait_for(handler, timeout=timeout)
        finally:
            assert not handler.persistent
            self.remove(handler)

    async def handle(self, data) -> None:
        """
        Find handler for inbound message and handle it.
        :param data:
        :return:
        """
        handled = False
        for handler in self._handlers:
            try:
                if handler.can_handle(data):
                    handled = True
                    await handler(data)
            except AlreadyHandledError:
                logger.error("Already handled")
            except Exception:
                logger.exception("Exception caught during message handling")
                raise

        if not handled and not self._should_ignore_no_handlers:
            logger.error(
                "No handler for message {}\nDetail: {}".format(
                    data.fields.value.po.command, data
                )
            )
