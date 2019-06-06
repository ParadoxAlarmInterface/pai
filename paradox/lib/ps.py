from pubsub import pub

PREFIX="pai_"

def subscribe(listener, topic):
    pub.subscribe(listener, PREFIX + topic)

def sendMessage(topic, *args, **kwargs):
    pub.sendMessage(topic, *args, **kwargs)