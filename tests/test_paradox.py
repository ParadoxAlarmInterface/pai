import pytest
import asyncio
import binascii
import mock
from pytest_mock import mocker

from construct import Container

from paradox.paradox import Paradox

@pytest.fixture
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_connect():
    alarm = Paradox(connection=mocker, interface=mocker)

    await alarm.connect_async()