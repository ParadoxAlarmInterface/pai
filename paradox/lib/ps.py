from pubsub import pub

PREFIX="pai_"

def subscribe(listener, topicName: str, **curriedArgs):
    pub.subscribe(listener, PREFIX + topicName, **curriedArgs)

def sendMessage(topicName: str, **msgData):
    pub.sendMessage(topicName, **msgData)