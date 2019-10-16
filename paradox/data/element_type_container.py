from collections import MutableMapping
from typing import Mapping, Sequence

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

    def __str__(self):
        return self.store.__str__()

    def __repr__(self):
        return self.store.__str__()

    def filter(self, id_arr):
        self.store = dict((i, v) for i, v in self.store.items() if i in id_arr)

    def select(self, needle) -> Sequence[int]:
        """
        Helper function to select objects from provided dictionary

        :param haystack: dictionary
        :param needle:
        :return: Sequence[int] list of object indexes
        """
        selected = []  # type: Sequence[int]
        if needle == 'all' or needle == '0':
            selected = list(self.store)
        else:
            if needle.isdigit() and 0 < int(needle) < len(self.store):
                el = self.get(int(needle))
            else:
                el = self.get(needle)

            if el:
                if "id" not in el:
                    raise Exception("Invalid dictionary of elements provided")
                selected = [el["id"]]

        return selected

    def deep_merge(self, *dicts):
        self.store = deep_merge(self.store, *dicts)

    @staticmethod
    def __keytransform__(key):
        if isinstance(key, str) and key.isdigit():
            return int(key)
        return key
