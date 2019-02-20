# -*- coding: utf-8 -*-

import json
import typing

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

