import os


class Config:
    def __init__(self):
        entries = {}
        locations = ['/etc/pai/pai.conf',
                     '/usr/local/etc/pai/pai.conf',
                     '~/.local/etc/pai.conf']

        for location in locations:
            location = os.path.expanduser(location)
            if os.path.exists(location):
                break
        else:
            raise(Exception("ERROR: Could not find configuration file. Tried: {}".format(locations)))

        exec(open(location).read(), None, entries)
        for k, v in entries.items():
            if k[0].isupper():
                self.__dict__.update({k: v})


config = Config()
