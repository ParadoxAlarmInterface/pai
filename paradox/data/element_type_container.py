from typing import Sequence, Union

from paradox.lib.utils import deep_merge


class ElementTypeContainer(dict):
    def __init__(self, *args, **kwargs):
        super(ElementTypeContainer, self).__init__(*args, **kwargs)

        self.key_index = {}

        self.reindex()

    def reindex(self):
        """Update additional text key index"""
        for key, value in self.items():
            if isinstance(value, dict) and "key" in value:
                self.key_index[value["key"]] = value

    def filter(self, keys: Sequence[Union[int, str]]):
        """
        Drops all elements that are not in `id_arr`. Does not support textual keys.
        :param Sequence[int] id_arr: Array of ints
        :return:
        """
        id_arr = self.select(keys)
        remove_keys = set(self.keys()) - set(id_arr)
        for i in remove_keys:
            try:
                self.__delitem__(i)
            except KeyError:
                pass

    def select(
        self, needle: Union[str, int, Sequence[Union[int, str]]]
    ) -> Sequence[int]:
        """
        Helper function to select objects from provided dictionary

        :param needle:
        :return: Sequence[int] list of object indexes
        """

        if needle == "all" or needle == "0":
            return list(self)

        else:
            if isinstance(needle, range):
                needle = list(needle)
            elif not isinstance(needle, (list, set)):
                needle = [needle]

            selected = []

            for n in needle:
                index = self.get_index(n)
                if index is not None:
                    selected.append(index)

            return selected

    def deep_merge(self, *dicts):
        deep_merge(self, *dicts)

    def get_index(self, key: Union[str, int]):
        if isinstance(key, int):
            return key
        e = self.get(key)
        if e is not None:
            for k, v in self.items():
                if v == e:
                    return k

    def get(self, key: Union[str, int], default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def __contains__(self, key: Union[str, int]):
        item = self.get(key)
        return item is not None

    def __getitem__(self, key: Union[str, int]):
        key = self.__keytransform__(key)
        if isinstance(key, str):
            e = self.key_index.get(key)
            if e is not None:
                return e

        return super(ElementTypeContainer, self).__getitem__(key)

    def __setitem__(self, key: Union[str, int], value):
        key = self.__keytransform__(key)
        super(ElementTypeContainer, self).__setitem__(key, value)

        if isinstance(value, dict) and "key" in value:
            self.key_index[value["key"]] = value

    def __delitem__(self, key: Union[str, int]):
        key = self.get_index(key)
        try:
            el = self[key]
            if isinstance(el, dict) and "key" in el:
                text_key = el["key"]

                del self.key_index[text_key]
        except KeyError:
            pass

        super(ElementTypeContainer, self).__delitem__(self.__keytransform__(key))

    @staticmethod
    def __keytransform__(key: Union[str, int]):
        if isinstance(key, str) and key.isdigit():
            return int(key)
        return key
