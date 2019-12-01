from pubsub import pub

from paradox.event import Event, Change, Notification

PREFIX="pai_"


def subscribe(listener, topicName: str, **curriedArgs):
    pub.subscribe(listener, PREFIX + topicName, **curriedArgs)


def sendMessage(topicName: str, **msgData):
    pub.sendMessage(PREFIX + topicName, **msgData)


def sendEvent(event: Event):
    pub.sendMessage(PREFIX + "events", event=event)


def sendChange(change: Change):
    pub.sendMessage(PREFIX + "changes", change=change)


def sendNotification(notification: Notification):
    pub.sendMessage(PREFIX + "notifications", notification=notification)
