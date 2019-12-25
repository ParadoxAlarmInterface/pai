# -*- coding: utf-8 -*-

import json
import re
from copy import deepcopy
from functools import reduce
from construct import Container, ListContainer
from typing import Mapping, List

class JSONByteEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, bytes):
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


def deep_merge(*dicts, extend_lists=False, initializer=None):
    def merge_into(d1, d2):
        if d1 is None:
            return d2
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

    return reduce(merge_into, dicts, initializer)


re_sanitize_key = re.compile(r'\W')
def sanitize_key(key):
    if isinstance(key, int):
        return str(key)
    else:
        return re_sanitize_key.sub('_', key).strip('_')


def construct_free(container: Container):
    if isinstance(container, (Container, Mapping)):
        return dict((k, construct_free(v)) for k, v in container.items() if not (isinstance(k, str) and k.startswith('_')))
    elif isinstance(container, (ListContainer, List)):
        return list(construct_free(v) for v in container)
    else:
        return container