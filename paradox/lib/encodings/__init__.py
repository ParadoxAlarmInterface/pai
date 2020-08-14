import codecs
import logging
import re
from importlib import import_module

logger = logging.getLogger("PAI").getChild(__name__)

codec_cache = {}


def paradox_codec_search(name: str):
    name = name.lower()
    match = re.match("^paradox-([a-z]{2})$", name)
    if match:
        enc = match.group(1)
        mod = codec_cache.get(enc)
        if mod is not None:
            return mod
        else:
            try:
                module = import_module("." + enc, "paradox.lib.encodings")
                mod = codec_cache[enc] = module.getregentry()
                logger.debug(f"Loaded {name} encoding")
                return mod
            except ImportError:
                pass


def register_encodings():
    codecs.register(paradox_codec_search)
