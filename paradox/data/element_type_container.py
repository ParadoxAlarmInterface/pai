from typing import Mapping, Sequence

from paradox.lib.utils import deep_merge

class ElementTypeContainer(dict):
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
        if needle == 'all' or needle == '0':
            selected = list(self)
        else:
            if needle.isdigit() and 0 < int(needle) < len(self):
                el = self.get(int(needle))
            else:
                el = self.get(needle)

            if el:
                if "id" not in el:
                    raise Exception("Invalid dictionary of elements provided")
                selected = [el["id"]]

        return selected

    def deep_merge(self, *dicts):
        deep_merge(self, *dicts)

    def get(self, k, default=None):
        try:
            return self.__getitem__(k)
        except KeyError:
            return default

    def __contains__(self, key):
        for k, v in self.items():
            if isinstance(v, Mapping) and "key" in v and v["key"] == key:
                return True
        return super(ElementTypeContainer, self).__contains__(self.__keytransform__(key))

    def __getitem__(self, key):
        if isinstance(key, str):
            for k, v in self.items():
                if isinstance(v, Mapping) and "key" in v and v["key"] == key:
                    return v
        return super(ElementTypeContainer, self).__getitem__(self.__keytransform__(key))

    def __setitem__(self, key, value):
        super(ElementTypeContainer, self).__setitem__(self.__keytransform__(key), value)

    def __delitem__(self, key):
        if isinstance(key, str):
            for k, v in self.items():
                if isinstance(v, Mapping) and "key" in v and v["key"] == key:
                    key = k
                    break
        super(ElementTypeContainer, self).__delitem__(self.__keytransform__(key))

    @staticmethod
    def __keytransform__(key):
        if isinstance(key, str) and key.isdigit():
            return int(key)
        return key
