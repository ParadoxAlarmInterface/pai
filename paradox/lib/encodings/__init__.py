import codecs
import logging
import re
from importlib import import_module

logger = logging.getLogger("PAI").getChild(__name__)

codec_cache = {}


def paradox_codec_search(name: str):
    name = name.lower()
    match = re.match("^paradox[-_]([a-z]{2})$", name)
    if match:
        enc = match.group(1)
        mod = codec_cache.get(enc)
        if mod is not None:
            return mod
        else:
            try:
                mod = codec_cache[enc] = getregentry(enc)
                logger.debug(f"Loaded {name} encoding")
                return mod
            except ImportError:
                pass         


def getregentry(enc):

    module = import_module("." + enc, "paradox.lib.encodings.charmaps")
    
    decoding_table = module.charmap
    encoding_table = codecs.charmap_build(decoding_table)


    class Codec(codecs.Codec):
        def encode(self, input, errors="strict"):
            return codecs.charmap_encode(input, errors, encoding_table)

        def decode(self, input, errors="strict"):
            return codecs.charmap_decode(input, errors, decoding_table)


    class IncrementalEncoder(codecs.IncrementalEncoder):
        def encode(self, input, final=False):
            return codecs.charmap_encode(input, self.errors, encoding_table)[0]


    class IncrementalDecoder(codecs.IncrementalDecoder):
        def decode(self, input, final=False):
            return codecs.charmap_decode(input, self.errors, decoding_table)[0]


    class StreamWriter(Codec, codecs.StreamWriter):
        pass


    class StreamReader(Codec, codecs.StreamReader):
        pass

    return codecs.CodecInfo(
        name="paradox-"+enc,
        encode=Codec().encode,
        decode=Codec().decode,
        incrementalencoder=IncrementalEncoder,
        incrementaldecoder=IncrementalDecoder,
        streamreader=StreamReader,
        streamwriter=StreamWriter,
    )


def register_encodings():
    codecs.register(paradox_codec_search)
