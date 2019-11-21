import logging
import re
from collections import namedtuple

from paradox.event import Event, LiveEvent, EventLevel

re_match = re.compile(r"[+-]?(?P<quote>['\"])?(?(quote).+?|[a-z_A-Z]+)(?(quote)(?P=quote))")
re_unquote = re.compile(r"^(?P<quote>['\"])(.*)(?P=quote)$")

logger = logging.getLogger('PAI').getChild(__name__)


def _unquote(s:str):
    return re_unquote.sub(r'\2', s)


def tag_match(event: Event, queries:list):
    tags = [event.type] + event.tags
    if isinstance(event, LiveEvent):
        tags += [event.name, event.label]

    for query in queries:
        include = set()
        exclude = set()
        for m in re_match.finditer(query):
            token = m.group()
            if token[0] == '+':
                include.add(_unquote(token[1:]))
            elif token[0] == '-':
                exclude.add(_unquote(token[1:]))
            else:
                include.add(_unquote(token))

        if all(t in tags for t in include) and all(t not in tags for t in exclude):
            return True

    return False


class EventFilter:
    def __init__(self, min_level=EventLevel.INFO):
        self.min_level = min_level

    def match(self, event: Event):
        return event.level >= self.min_level


class LiveEventFilter(EventFilter):
    def match(self, event: Event):
        return super().match(event) and isinstance(event, LiveEvent)


TagQuery = namedtuple('TagQuery', ['include', 'exclude'])


class EventTagFilter(EventFilter):
    def __init__(self, queries: list, *args, **kwargs):
        self.queries = list()

        for query in queries:
            include = set()
            exclude = set()
            for m in re_match.finditer(query):
                token = m.group()
                if token[0] == '+':
                    include.add(_unquote(token[1:]))
                elif token[0] == '-':
                    exclude.add(_unquote(token[1:]))
                else:
                    include.add(_unquote(token))

            self.queries.append(TagQuery(include, exclude))
        
        super().__init__(*args, **kwargs)

    def match(self, event: Event):
        tags = [event.type] + event.tags
        if isinstance(event, LiveEvent):
            tags += [event.name, event.label]

        return super().match(event) and any(all(t in tags for t in query.include) and all(t not in tags for t in query.exclude) for query in self.queries)


class LiveEventRegexpFilter(LiveEventFilter):
    def __init__(self, events_allow, events_ignore, *args, **kwargs):
        self.events_allow = events_allow
        self.events_ignore = events_ignore

        super().__init__(*args, **kwargs)

    def match(self, event: Event):
        allow = False
        if super().match(event):
            assert isinstance(event, LiveEvent)

            major_code = event.major
            minor_code = event.minor
            # Only let some elements pass

            for ev in self.events_allow:
                if isinstance(ev, tuple):
                    if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                        allow = True
                        break
                elif isinstance(ev, str):
                    if re.match(ev, event.key):
                        allow = True
                        break

            # Ignore some events
            for ev in self.events_ignore:
                if isinstance(ev, tuple):
                    if major_code == ev[0] and (minor_code == ev[1] or ev[1] == -1):
                        allow = False
                        break
                elif isinstance(ev, str):
                    if re.match(ev, event.key):
                        allow = False
                        break

        return allow