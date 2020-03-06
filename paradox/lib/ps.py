import asyncio
import logging
from asyncio import Future
from collections import defaultdict
from typing import Awaitable, Callable, List, Mapping, Union

from paradox.event import Change, Event, Notification
from paradox.lib.utils import call_soon_in_main_loop

PREFIX = "pai_"

logger = logging.getLogger("PAI").getChild(__name__)
loop = asyncio.get_event_loop()


class Listener:
    def __init__(self, callback: Union[Callable, Future], **curriedArgs):
        if not isinstance(callback, (Callable, Future)):
            raise AssertionError("Wrong callback")
        self.callback = callback
        self.curriedArgs = curriedArgs

    async def call(self, **kwargs):
        kwargs2 = self.curriedArgs.copy()
        kwargs2.update(**kwargs)

        if isinstance(self.callback, Callable):
            result = self.callback(**kwargs2)
            if isinstance(result, Awaitable):
                await result
        elif isinstance(self.callback, Future):
            if not self.callback.done():
                self.callback.set_result(kwargs2)
            else:
                logger.debug("Future already done")
        else:
            raise Exception("Should not happen")

    def __eq__(self, other):
        if isinstance(other, Listener):
            return self.callback == other.callback
        return False


class PubSub:
    listeners: Mapping[str, List[Listener]]

    def __init__(self):
        self.listeners = defaultdict(list)

    def subscribe(self, listener: Callable, topicName: str, **curriedArgs):
        self.listeners[topicName].append(Listener(listener, **curriedArgs))

    def unsubscribe(self, listener: Callable, topicName: str):
        self.listeners[topicName].remove(Listener(listener))

    async def sendMessage(self, topicName: str, **msgData):
        return await asyncio.gather(
            *(l.call(**msgData) for l in self.listeners[topicName])
        )


pub = PubSub()


def subscribe(listener, topicName: str, **curriedArgs):
    pub.subscribe(listener, PREFIX + topicName, **curriedArgs)


def sendMessage(topicName: str, **msgData):
    call_soon_in_main_loop(pub.sendMessage(PREFIX + topicName, **msgData))


def sendEvent(event: Event):
    call_soon_in_main_loop(pub.sendMessage(PREFIX + "events", event=event))


def sendChange(change: Change):
    call_soon_in_main_loop(pub.sendMessage(PREFIX + "changes", change=change))


def sendNotification(notification: Notification):
    call_soon_in_main_loop(
        pub.sendMessage(PREFIX + "notifications", notification=notification)
    )
