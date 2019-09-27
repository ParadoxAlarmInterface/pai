from collections import MutableMapping
from typing import Mapping

from paradox.lib.utils import deep_merge


class ElementTypeContainer(MutableMapping):
    def __init__(self, *args, **kwargs):
        self.store = dict()
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key):
        if isinstance(key, str):
            for k, v in self.store.items():
                if isinstance(v, Mapping) and "key" in v and v["key"] == key:
                    return v
        return self.store[self.__keytransform__(key)]

    def __setitem__(self, key, value):
        self.store[self.__keytransform__(key)] = value

    def __delitem__(self, key):
        del self.store[self.__keytransform__(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def filter(self, id_arr):
        self.store = dict((i, v) for i, v in self.store.items() if i in id_arr)

    def deep_merge(self, *dicts):
        self.store = deep_merge(self.store, *dicts)

    @staticmethod
    def __keytransform__(key):
        if isinstance(key, str) and key.isdigit():
            return int(key)
        return key
