import logging
from enum import IntEnum


class RunState(IntEnum):
    STOP = 0
    INIT = 1
    RUN = 2
    PAUSE = 3
    ERROR = 4


class EventLevel(IntEnum):
    NOTSET = logging.NOTSET
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARN
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    @staticmethod
    def from_name(level="NOTSET"):
        if isinstance(level, EventLevel):
            return level

        level = level.upper()
        if level in EventLevel.__members__:
            return EventLevel.__members__[level]

        raise (
            Exception(
                "Invalid log level {}. Valid levels: {}".format(
                    level, list(EventLevel.__members__)
                )
            )
        )

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value

        if other.__class__ is int:
            return self.value < other

        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value

        if other.__class__ is int:
            return self.value > other

        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value

        if other.__class__ is int:
            return self.value <= other

        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value

        if other.__class__ is int:
            return self.value >= other

        return NotImplemented

    def __str__(self):
        return self.name
