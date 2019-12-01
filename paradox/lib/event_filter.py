import logging
import re
from collections import namedtuple

from paradox.event import Event, LiveEvent, EventLevel

re_match = re.compile(r"[+-]?(?P<quote>['\"])?(?(quote).+?|[a-z_A-Z=]+)(?(quote)(?P=quote))")
re_unquote = re.compile(r"^(?P<quote>['\"])(.*)(?P=quote)$")

logger = logging.getLogger('PAI').getChild(__name__)


def _unquote(s:str):
    return re_unquote.sub(r'\2', s)


class EventFilter:
    def __init__(self, min_level=EventLevel.INFO):
        assert isinstance(min_level, EventLevel)
        self.min_level = min_level

    def match(self, event: Event):
        return event.level >= self.min_level


class LiveEventFilter(EventFilter):
    def match(self, event: Event):
        return super().match(event) and isinstance(event, LiveEvent)


TagQuery = namedtuple('TagQuery', ['include', 'exclude', 'changes_include', 'changes_exclude'])
KeyValue = namedtuple('KeyValue', ['key', 'value'])
lowercase_value_mapping = {
    '': None,
    'true': True,
    'false': False
}

class EventTagFilter(EventFilter):
    def __init__(self, queries: list, min_level=EventLevel.INFO):
        self.queries = list()

        for query in queries:
            include = set()
            exclude = set()
            changes_include = set()
            changes_exclude = set()
            for m in re_match.finditer(query):
                token = m.group()
                if '=' in token:
                    changes = changes_include
                    if token[0] == '+':
                        token = token[1:]
                    elif token[0] == '-':
                        changes = changes_exclude
                        token = token[1:]

                    k, v = token.split('=', 1)
                    k = _unquote(k)
                    v = _unquote(v)
                    if not k:
                        raise AssertionError('Invalid filter query "%s", token: "%s"' % (query, token))

                    v = lowercase_value_mapping.get(v.lower(), v)

                    changes.add(KeyValue(k, v))
                elif token[0] == '+':
                    include.add(_unquote(token[1:]))
                elif token[0] == '-':
                    exclude.add(_unquote(token[1:]))
                else:
                    include.add(_unquote(token))

            self.queries.append(TagQuery(include, exclude, changes_include, changes_exclude))
        
        super().__init__(min_level=min_level)

    def match(self, event: Event):
        tags = [event.type]
        if event.tags:
            tags += event.tags

        if isinstance(event, LiveEvent):
            tags += [event.name, event.label]

        return super().match(event) and any(
            all(i in tags for i in query.include)
            and all(e not in tags for e in query.exclude)
            and all((ci.key in event.change and (ci.value is None or event.change.get(ci.key) == ci.value)) for ci in query.changes_include)
            and all((ce.key not in event.change or (ce.value is not None and event.change.get(ce.key) != ce.value)) for ce in query.changes_exclude)
            for query in self.queries
        )


class LiveEventRegexpFilter(LiveEventFilter):
    def __init__(self, events_allow, events_ignore, min_level=EventLevel.INFO):
        self.events_allow = events_allow
        self.events_ignore = events_ignore

        super().__init__(min_level=min_level)

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