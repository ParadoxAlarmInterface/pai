from collections import defaultdict

from .element_type_container import ElementTypeContainer

class MemoryStorage():
    def __init__(self):
        self.data = defaultdict(ElementTypeContainer)

    def get_container(self, container_name):
        return self.data[container_name]

    def get_container_object(self, container_name, key, create_if_missing=False):
        c = self.get_container(container_name)
        el = c.get(key)
        if create_if_missing and el is None:
            el = c[key] = {'key': key}

        return el
