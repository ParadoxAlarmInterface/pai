from typing import Sequence

from paradox.lib.utils import deep_merge


class ElementTypeContainer(dict):
    def __init__(self, *args, **kwargs):
        super(ElementTypeContainer, self).__init__(*args, **kwargs)

        self.key_index = {}

        self.reindex()

    def reindex(self):
        for key, value in self.items():
            if isinstance(value, dict) and "key" in value:
                self.key_index[value["key"]] = value

    def filter(self, id_arr):
        remove_keys = set(self.keys()) - set(id_arr)
        for i in remove_keys:
            self.pop(i)

    def select(self, needle: str) -> Sequence[int]:
        """
        Helper function to select objects from provided dictionary

        :param needle:
        :return: Sequence[int] list of object indexes
        """
        selected = []  # type: Sequence[int]
        if needle == "all" or needle == "0":
            selected = list(self)
        else:
            index = self.get_index(needle)
            if index:
                selected = [index]

        return selected

    def deep_merge(self, *dicts):
        deep_merge(self, *dicts)

    def get_index(self, key):
        e = self.get(key)
        if e:
            for k, v in self.items():
                if v == e:
                    return k

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __contains__(self, key):
        item = self.get(key)
        return item is not None

    def __getitem__(self, key):
        key = self.__keytransform__(key)
        if isinstance(key, str):
            e = self.key_index.get(key)
            if e is not None:
                return e
        return super(ElementTypeContainer, self).__getitem__(key)

    def __setitem__(self, key, value):
        key = self.__keytransform__(key)
        super(ElementTypeContainer, self).__setitem__(key, value)

        if isinstance(value, dict) and "key" in value:
            self.key_index[value["key"]] = value

    def __delitem__(self, key):
        key = self.__keytransform__(key)
        if isinstance(key, str):
            for k, v in self.items():
                if isinstance(v, dict) and "key" in v and v["key"] == key:
                    del self.key_index[key]
                    key = k
                    break
        super(ElementTypeContainer, self).__delitem__(self.__keytransform__(key))

    @staticmethod
    def __keytransform__(key):
        if isinstance(key, str) and key.isdigit():
            return int(key)
        return key
