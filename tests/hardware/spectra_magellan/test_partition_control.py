import asyncio
import binascii
import logging
import threading
import typing

import pytest

from paradox.data.enums import RunState
from paradox.hardware import create_panel
from paradox.lib.async_message_manager import AsyncMessageManager
from paradox.lib.ps import sendMessage
from paradox.lib.utils import call_soon_in_main_loop
from paradox.paradox import Paradox

logger = logging.getLogger('PAI').getChild(__name__)
from paradox.config import config as cfg

async def send_initial_status(alarm):
    sendMessage("labels_loaded", data=dict(
        partition={
            1: dict(
                id=1,
                label='Partition 1',
                key='Partition_1'
            ),
            2: dict(
                id=1,
                label='Partition 2',
                key='Partition_2'
            )
        }
    ))

    sendMessage("status_update", status=dict(
        partition={
            1: dict(
                arm=False,
                alarm_in_memory=False,
                audible_alarm=False,
                exit_delay=False,
                was_in_alarm=False
            ),
            2: dict(
                arm=False,
                alarm_in_memory=False,
                audible_alarm=False,
                exit_delay=False,
                was_in_alarm=False
            )
        }
    ))

    await asyncio.sleep(0.01)

class MockConnection(AsyncMessageManager):
    def __init__(self, on_message: typing.Callable[[bytes], None]):
        super().__init__()
        self.connected = True
        self.on_message = on_message
        self.pending = []

    def connect(self):
        return True
    
    def write(self, data: bytes):
        logger.debug(f"PAI -> CON: {binascii.hexlify(data)}")
        if len(self.pending) > 0:
            message = self.pending.pop(0)

            logger.debug(f"CON -> PAI: {binascii.hexlify(message)}")
            self.on_message(message)

        return True

class MockClient(threading.Thread):
    def __init__(self, alarm, partitions, command):
        threading.Thread.__init__(self)
        self.alarm = alarm
        self.partitions = partitions
        self.command = command
        self.result = None

    async def _control(self):
        self.result = await self.alarm.control_partition(self.partitions, self.command)
        logger.debug(f"Control result: {self.result}")

    def run(self):
        logger.debug(f"Issuing {self.command} to {self.partitions} ")
        call_soon_in_main_loop(self._control())

    def join(self, timeout=None):
        super(MockClient, self).join(timeout)
        # if isinstance(self.result, str) or not self.result:
        #     raise Exception(str(self.result))


@pytest.fixture(scope='function')
async def setup_panel(mocker):
    mocker.patch.object(cfg, "LOGGING_LEVEL_CONSOLE", logging.DEBUG)
    mocker.patch.object(cfg, "LOGGING_DUMP_PACKETS", True)
    mocker.patch("paradox.lib.utils.main_thread_loop", asyncio.get_event_loop())
    # cfg.LOGGING_LEVEL_CONSOLE = logging.DEBUG
    # cfg.LOGGING_DUMP_PACKETS = True
    
    logger.setLevel(logging.DEBUG)
    alarm = Paradox()
    #alarm.work_loop.set_debug(True)

    alarm.run_state = RunState.RUN
    alarm.panel = create_panel(alarm, 'MAGELLAN_MG5050')
    
    await send_initial_status(alarm)
    con = MockConnection(alarm.on_connection_message)
    
    alarm._connection = con
    alarm._register_connection_handlers()
    
    return alarm, con 

@pytest.mark.asyncio
async def test_partition_arm_spmg_single_1(setup_panel):
    alarm, con = setup_panel

    con.pending.append(binascii.unhexlify('42000400000000000000000000000000000000000000000000000000000000000000000046'))
    
    cli = MockClient(alarm, '1', 'arm')
    cli.start()
    await asyncio.sleep(0.01)

    cli.join(1)

    assert not cli.is_alive()

@pytest.mark.asyncio
async def test_partition_arm_spmg_single_2(setup_panel):
    alarm, con = setup_panel

    con.pending.append(binascii.unhexlify('42000400000000000000000000000000000000000000000000000000000000000000000046'))
    
    cli = MockClient(alarm, '2', 'arm')
    cli.start()
    await asyncio.sleep(0.01)

    cli.join(1)

    assert not cli.is_alive()


@pytest.mark.asyncio
async def test_partition_arm_spmg_single_event(setup_panel):
    alarm, con = setup_panel
    
    con.pending.append(binascii.unhexlify('e2141401110f22020e000000000002494e544552494f5220202020202020200100000000cc'))
    con.pending.append(binascii.unhexlify('42000400000000000000000000000000000000000000000000000000000000000000000046'))

    cli = MockClient(alarm, '1', 'arm')
    cli.start()
    await asyncio.sleep(2.01)  # to trigger one timeout

    cli.join(1)

    assert not cli.is_alive()

@pytest.mark.asyncio
async def test_partition_arm_spmg_all(setup_panel):
    alarm, con = setup_panel

    con.pending.append(binascii.unhexlify('42000400000000000000000000000000000000000000000000000000000000000000000046'))
    con.pending.append(binascii.unhexlify('e2141401110f22020e000000000002494e544552494f5220202020202020200100000000cc'))
    con.pending.append(binascii.unhexlify('42000400000000000000000000000000000000000000000000000000000000000000000046'))

    cli = MockClient(alarm, 'all', 'arm')
    cli.start()
    await asyncio.sleep(2.01)  # to trigger one timeout

    cli.join(1)

    assert not cli.is_alive()
