import logging
from collections import defaultdict
from typing import Dict

from construct import Container

from paradox.config import config as cfg
from paradox.data.element_type_container import ElementTypeContainer

logger = logging.getLogger('PAI').getChild(__name__)


def _iterate_properties(data):
    if isinstance(data, list):
        for key, value in enumerate(data):
            yield (key, value)
    elif isinstance(data, dict):
        for key, value in data.items():
            if type(key) == str and key.startswith('_'):  # ignore private properties
                continue
            yield (key, value)


def convert_raw_status(raw_status: Container) -> Dict[str, ElementTypeContainer]:
    out = defaultdict(ElementTypeContainer)

    for root_key, value in _iterate_properties(raw_status):
        element_type = root_key.split('_')[0]
        prop_name = '_'.join(root_key.split('_')[1:])

        if not prop_name:
            prop_name = element_type

        out[element_type].deep_merge(_parse_raw_status(prop_name, value))

    return out


def _parse_raw_status(prop_name: str, value) -> (dict, list):
    if isinstance(value, dict):
        arr = {}
        all_keys_are_int = all([isinstance(k, int) for k in value.keys()])
        for element_key, element_value in _iterate_properties(value):
            if all_keys_are_int:  # we deal with int keys. it should be a list of elements
                arr[element_key] = _parse_raw_status(prop_name, element_value)
            else:  # we deal with text keys
                if isinstance(element_value, dict):  # ignore prop_name, go deeper to find keys
                    arr[element_key] = _parse_raw_status(element_key, element_value)
                else:  # use element_key instead of prop_name
                    arr[element_key] = element_value
        return arr
    else:
        return {prop_name: value}
