import binascii
import asyncio
import pytest
from mock import MagicMock
import typing
from paradox.hardware import create_panel
from paradox.data.enums import RunState
from paradox.hardware.spectra_magellan.parsers import LiveEvent
from paradox.lib.ps import sendMessage
from paradox.paradox import Paradox
from paradox.lib.async_message_manager import AsyncMessageManager
import logging
import time
import threading

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
        self.connected = True
        return True
    
    def write(self, data: bytes):
        logger.debug(f"PAI -> CON: {binascii.hexlify(data)}")
        if len(self.pending) > 0:
            message = self.pending[0]
            del self.pending[0]

            logger.debug(f"CON -> PAI {binascii.hexlify(message)}")
            self.on_message(message)

        return True

    def close(self):
        logger.info('Closing connection')
        self.connected = False
        self.loop.stop()


class MockInterface():
    def __init__(self, alarm):
        super().__init__()
        self.alarm = alarm
        self.t = threading.Thread(target=self.worker, daemon=False)
        self.t.start()
        self.loop = asyncio.new_event_loop()

    def worker(self):
        self.alarm.control_partition('all', 'arm')


@pytest.mark.asyncio
async def test_partition_arm_spmg():
    cfg.LOGGING_LEVEL_CONSOLE = logging.DEBUG
    cfg.LOGGING_DUMP_PACKETS = True
    
    logger.setLevel(logging.DEBUG)
    alarm = Paradox()

    alarm.run_state = RunState.RUN
    
    await send_initial_status(alarm)

    alarm.panel = create_panel(alarm, 'MAGELLAN_MG5050')

    con = MockConnection(alarm.on_connection_message)
    con.pending.append(binascii.unhexlify('42000400000000000000000000000000000000000000000000000000000000000000000046'))
    con.pending.append(binascii.unhexlify('e2141401110f22020e000000000002494e544552494f5220202020202020200100000000cc'))
    con.pending.append(binascii.unhexlify('42000400000000000000000000000000000000000000000000000000000000000000000046'))

    alarm._connection = con
    alarm._register_connection_handlers()
    
    cli = MockInterface(alarm)
    
    await asyncio.sleep(0.01)
    logger.debug("Cleaning test")
    cli.t.join()
    con.close()
    assert False
