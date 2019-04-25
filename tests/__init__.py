from os import path

from paradox.config import config
config.load(path.join(path.dirname(__file__), 'pai.conf'))