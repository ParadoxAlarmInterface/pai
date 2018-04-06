
class MQTTInterface():

    def __init__(self, config):
        self.callback = None
        self.config = config

    def start(self):
        pass

    def set_callback(self, callback):
        self.callback = callback

    def expose(self, topic, message):
        pass