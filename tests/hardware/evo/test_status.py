import asyncio
import json

import pytest

from paradox.paradox import Paradox
from paradox.parsers.status import convert_raw_status
from .status_data import message_parser_output, converted_status


def test_convert_raw_status(mocker):
    mocker.patch('paradox.lib.ps')
    p = Paradox()
    status = convert_raw_status(message_parser_output)

    assert status["zone"] == {
        1: dict(open=False, tamper=False, low_battery=False, generated_alarm=False, presently_in_alarm=False,
                activated_entry_delay=False,
                activated_intellizone_delay=False, bypassed=False, shutted_down=False,
                tx_delay=False, supervision_trouble=False),
        2: dict(open=False, tamper=False, low_battery=False, generated_alarm=False,
                presently_in_alarm=False,
                activated_entry_delay=False,
                activated_intellizone_delay=False,
                bypassed=False,
                shutted_down=False,
                tx_delay=False,
                supervision_trouble=False)
    }

    assert status["partition"] == message_parser_output["partition_status"]
    assert status["door"] == {1: dict(open=False), 2: dict(open=False)}
    assert status["bus-module"] == {1: dict(trouble=False), 2: dict(trouble=False)}
    assert status["system"]["troubles"] == message_parser_output["system"]["troubles"]

    a = json.dumps(converted_status, sort_keys=True, indent=2, default=str)
    b = json.dumps(status, sort_keys=True, indent=2, default=str)
    assert a == b

    # import deepdiff
    # from pprint import pprint
    # for key, value in status.items():
    #     try:
    #         result = deepdiff.DeepDiff(status[key].store, converted_status[key], ignore_order=True, ignore_type_subclasses=True)
    #         pprint(result)
    #     except KeyError as e:
    #         raise


@pytest.mark.asyncio
async def test_update_properties(mocker):
    alarm = Paradox()
    alarm.panel = mocker.MagicMock()
    ps = mocker.patch("paradox.lib.ps")

    alarm._on_status_update(converted_status)

    await asyncio.sleep(0.01)
