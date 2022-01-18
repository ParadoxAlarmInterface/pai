# -*- coding: utf-8 -*-
import asyncio
import functools
import json
import re
import threading
import typing
from collections.abc import Hashable

from slugify import slugify

from copy import deepcopy

from construct import Container, ListContainer

main_thread_loop = asyncio.get_event_loop()


def call_soon_in_main_loop(fn: typing.Union[typing.Callable, typing.Coroutine]) -> None:
    if threading.current_thread() is threading.main_thread():
        loop = asyncio.get_event_loop()
        if isinstance(fn, typing.Coroutine):
            loop.create_task(fn)
        else:
            loop.call_soon(fn)
    else:
        assert main_thread_loop.is_running()
        if isinstance(fn, typing.Coroutine):
            asyncio.run_coroutine_threadsafe(
                fn, loop=main_thread_loop
            )  # Returns concurrent.futures.Future
        else:
            main_thread_loop.call_soon_threadsafe(fn)


class JSONByteEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, bytes):
            return o.decode("utf-8")

        return super(JSONByteEncoder, self).default(o)


class SerializableToJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "serialize") and callable(obj.serialize):
            return obj.serialize()
        return super().default(obj)


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

    return functools.reduce(merge_into, dicts, initializer)


re_sanitize_key = re.compile(r"\W")


def sanitize_key(key):
    if isinstance(key, int):
        return str(key)
    else:
        return re_sanitize_key.sub("_", slugify(key, lowercase=False)).strip("_")


def construct_free(container: Container):
    if isinstance(container, (Container, typing.Mapping)):
        return dict(
            (k, construct_free(v))
            for k, v in container.items()
            if not (isinstance(k, str) and k.startswith("_"))
        )
    elif isinstance(container, (ListContainer, typing.List)):
        return list(construct_free(v) for v in container)
    else:
        return container


class memoized(object):
    """From: https://wiki.python.org/moin/PythonDecoratorLibrary#Memoize
   Decorator. Caches a function's return value each time it is called.
   If called later with the same arguments, the cached value is returned
   (not reevaluated).
   """

    def __init__(self, func):
        self.func = func
        self.cache = {}

    def __call__(self, *args):
        if args in self.cache:
            return self.cache[args]
        else:
            if not isinstance(args, Hashable):
                # uncacheable. a list, for instance.
                # better to not cache than blow up.
                return self.func(*args)

            value = self.func(*args)
            self.cache[args] = value
            return value

    def __repr__(self):
        """Return the function's docstring."""
        return self.func.__doc__

    def __get__(self, obj, objtype):
        """Support instance methods."""
        return functools.partial(self.__call__, obj)
