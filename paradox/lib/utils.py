# -*- coding: utf-8 -*-

import json
import typing

from copy import deepcopy
from functools import reduce


class JSONByteEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, typing.ByteString):
            return o.decode('utf-8')

        return super(JSONByteEncoder, self).default(o)


class SortableTuple(tuple):
    def __lt__(self, rhs):
        return self[0] < rhs[0]

    def __gt__(self, rhs):
        return self[0] > rhs[0]

    def __le__(self, rhs):
        return self[0] <= rhs[0]

    def __ge__(self, rhs):
        return self[0] >= rhs[0]


def deep_merge(*dicts, extend_lists=False):
    def merge_into(d1, d2):
        for key in d2:
            if key not in d1:  # key is missing
                d1[key] = deepcopy(d2[key])
            elif extend_lists and isinstance(d1[key], list):
                d1[key].extend(deepcopy(d2[key]))
            elif not isinstance(d1[key], dict):
                d1[key] = deepcopy(d2[key])
            else:
                d1[key] = merge_into(d1[key], d2[key])
        return d1

    return reduce(merge_into, dicts, {})
