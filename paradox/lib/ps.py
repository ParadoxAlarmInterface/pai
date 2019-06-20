from pubsub import pub

PREFIX="pai_"

def subscribe(listener, topicName: str, **curriedArgs):
    pub.subscribe(listener, PREFIX + topicName, **curriedArgs)

def sendMessage(topicName: str, **msgData):
    pub.sendMessage(topicName, **msgData)

def sendEvent(event: dict):
    pub.sendMessage(PREFIX + "events", event=event)

def sendChange(etype: str, label: str, property: str, value: str, initial: bool=False):
    payload = dict(type=etype, label=label, property=property, value=value, initial=initial)
    pub.sendMessage(PREFIX + "changes", change=payload)
