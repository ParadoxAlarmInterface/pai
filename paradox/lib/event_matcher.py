import logging
import re

from paradox.event import Event

re_match = re.compile(r'[+-]?[a-z]+')

logger = logging.getLogger('PAI').getChild(__name__)


def tag_match(event: Event, queries:list):
    tags = [event.type] + event.tags

    for query in queries:
        include = set()
        exclude = set()
        for m in re_match.finditer(query):
            token = m.group()
            if token[0] == '+':
                include.add(token[1:])
            elif token[0] == '-':
                exclude.add(token[1:])
            else:
                include.add(token)

        if all(t in tags for t in include) and all(t not in tags for t in exclude):
            return True

    return False
