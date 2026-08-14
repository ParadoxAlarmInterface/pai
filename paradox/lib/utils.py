import asyncio
import binascii
from collections.abc import Hashable
from copy import deepcopy
import functools
import json
import re
import threading
import typing

from construct import Container, ListContainer
from slugify import slugify

main_thread_loop = None


def call_soon_in_main_loop(fn: typing.Union[typing.Callable, typing.Coroutine]) -> None:
    global main_thread_loop
    if threading.current_thread() is threading.main_thread():
        loop = asyncio.get_running_loop()
        main_thread_loop = loop
        if isinstance(fn, typing.Coroutine):
            loop.create_task(fn)
        else:
            loop.call_soon(fn)
    else:
        assert main_thread_loop is not None and main_thread_loop.is_running()
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

        return super().default(o)


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
        for key, value in d2.items():
            if key not in d1:  # key is missing
                d1[key] = deepcopy(value)
            elif extend_lists and isinstance(d1[key], list):
                if isinstance(value, list):
                    # Use list concatenation instead of extend for better performance with large lists
                    d1[key] = d1[key] + deepcopy(value)
                else:
                    # Keep original behavior for non-list values
                    d1[key].extend(deepcopy(value))
            elif not isinstance(d1[key], dict):
                d1[key] = deepcopy(value)
            elif isinstance(value, dict):  # Ensure both are dicts before recursion
                d1[key] = merge_into(d1[key], value)
            else:  # d1[key] is dict but value is not
                d1[key] = deepcopy(value)
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
        return {
            k: construct_free(v)
            for k, v in container.items()
            if not (isinstance(k, str) and k.startswith("_"))
        }
    elif isinstance(container, (ListContainer, typing.List)):
        return list(construct_free(v) for v in container)
    else:
        return container


class memoized:
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


def mask_secret(value: typing.Any, keep: int = 4) -> str:
    """Mask a sensitive identifier, keeping only the last ``keep`` characters."""
    if value is None:
        return "****"

    if isinstance(value, (bytes, bytearray)):
        value = binascii.hexlify(bytes(value)).decode("utf-8")
    else:
        value = str(value)

    if keep <= 0 or len(value) <= keep:
        return "****"

    return "****" + value[-keep:]


def mask_email(value: typing.Any) -> str:
    """Render an email address as ``j****@e****.com``."""
    if not value:
        return "****"

    local, sep, domain = str(value).partition("@")
    if not sep or not local or "." not in domain:
        return "****"

    name, _, tld = domain.rpartition(".")
    if not name:
        return "****"

    return f"{local[0]}****@{name[0]}****.{tld}"


def format_duration(seconds: typing.Optional[float]) -> str:
    """Render a duration coarsely, using at most the two largest units."""
    if seconds is None:
        return "unknown"

    total = int(max(0, seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    if days:
        parts = [("d", days), ("h", hours)]
    elif hours:
        parts = [("h", hours), ("m", minutes)]
    elif minutes:
        parts = [("m", minutes), ("s", secs)]
    else:
        return f"{secs}s"

    return " ".join(f"{v}{u}" for u, v in parts if v)


def describe_connection(config=None) -> str:
    """Render the configured connection as a short, redacted descriptor.

    Reads configuration only, so it is safe to call before connecting and
    after a connection has dropped.
    """
    if config is None:
        from paradox.config import config as cfg

        config = cfg

    connection_type = config.CONNECTION_TYPE

    if connection_type == "Serial":
        return f"Serial({config.SERIAL_PORT}@{config.SERIAL_BAUD})"

    if connection_type == "PRT3":
        return f"PRT3({config.PRT3_SERIAL_PORT}@{config.PRT3_SERIAL_BAUD})"

    if connection_type == "IP":
        if config.IP_CONNECTION_BARE:
            return "IP-bare({}:{})".format(
                config.IP_CONNECTION_HOST, config.IP_CONNECTION_PORT
            )
        if config.IP_CONNECTION_SITEID and config.IP_CONNECTION_EMAIL:
            return "SITE({} / {}, serial {})".format(
                config.IP_CONNECTION_SITEID,
                mask_email(config.IP_CONNECTION_EMAIL),
                mask_secret(config.IP_CONNECTION_PANEL_SERIAL),
            )
        return f"IP({config.IP_CONNECTION_HOST}:{config.IP_CONNECTION_PORT})"

    return f"Unknown({connection_type})"
