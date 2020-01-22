import asyncio
import functools
from collections import defaultdict
from typing import Callable, List, Mapping

from paradox.event import Event, Change, Notification

PREFIX = "pai_"


class Listener:
    def __init__(self, callback: Callable, **curriedArgs):
        self.callback = callback
        self.curriedArgs = curriedArgs

    async def call(self, **kwargs):
        kwargs2 = self.curriedArgs.copy()
        kwargs2.update(**kwargs)

        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(functools.partial(self.callback, **kwargs2))

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
        return await asyncio.gather(*(l.call(**msgData) for l in self.listeners[topicName]))


pub = PubSub()


def subscribe(listener, topicName: str, **curriedArgs):
    pub.subscribe(listener, PREFIX + topicName, **curriedArgs)


def sendMessage(topicName: str, **msgData):
    asyncio.get_event_loop().create_task(pub.sendMessage(PREFIX + topicName, **msgData))


def sendEvent(event: Event):
    asyncio.get_event_loop().create_task(pub.sendMessage(PREFIX + "events", event=event))


def sendChange(change: Change):
    asyncio.get_event_loop().create_task(pub.sendMessage(PREFIX + "changes", change=change))


def sendNotification(notification: Notification):
    asyncio.get_event_loop().create_task(pub.sendMessage(PREFIX + "notifications", notification=notification))

