import logging
import re

from paradox.event import Event, LiveEvent

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
