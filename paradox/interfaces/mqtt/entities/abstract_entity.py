class AbstractEntity:
    def __init__(self, device, availability_topic):
        self.availability_topic = availability_topic
        self.device = device

    def serialize(self):
        return dict(
            availability_topic=self.availability_topic,
            device=self.device
        )

    def get_configuration_topic(self):
        raise NotImplemented()
