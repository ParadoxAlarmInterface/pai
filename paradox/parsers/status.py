from collections import defaultdict
import logging
from typing import Dict

from construct import Container

from paradox.data.element_type_container import ElementTypeContainer
from paradox.lib.utils import deep_merge

logger = logging.getLogger("PAI").getChild(__name__)


def _iterate_properties(data):
    if isinstance(data, list):
        for key, value in enumerate(data):
            yield (key, value)
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and key.startswith(
                "_"
            ):  # ignore private properties
                continue
            yield (key, value)


def convert_raw_status(raw_status: Container) -> Dict[str, ElementTypeContainer]:
    # Merge into plain dicts first: ElementTypeContainer's key lookups are slow
    merged = defaultdict(dict)

    for root_key, value in _iterate_properties(raw_status):
        element_type = root_key.split("_")[0]
        prop_name = "_".join(root_key.split("_")[1:])

        if not prop_name:
            prop_name = element_type

        # _parse_raw_status returns fresh dicts, no need to deepcopy them
        deep_merge(
            merged[element_type], _parse_raw_status(prop_name, value), copy=False
        )

    out = defaultdict(ElementTypeContainer)
    for element_type, elements in merged.items():
        out[element_type] = ElementTypeContainer(elements)
    return out


def _parse_raw_status(prop_name: str, value) -> (dict, list):
    if isinstance(value, dict):
        arr = {}
        all_keys_are_int = all([isinstance(k, int) for k in value.keys()])
        for element_key, element_value in _iterate_properties(value):
            if (
                all_keys_are_int
            ):  # we deal with int keys. it should be a list of elements
                arr[element_key] = _parse_raw_status(prop_name, element_value)
            else:  # we deal with text keys
                if isinstance(
                    element_value, dict
                ):  # ignore prop_name, go deeper to find keys
                    arr[element_key] = _parse_raw_status(element_key, element_value)
                else:  # use element_key instead of prop_name
                    arr[element_key] = element_value
        return arr
    else:
        return {prop_name: value}
