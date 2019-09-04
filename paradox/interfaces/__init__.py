# -*- coding: utf-8 -*-

import asyncio
import logging
import queue
import threading

from paradox.config import config as cfg

logger = logging.getLogger('PAI').getChild(__name__)


class Interface:
    def __init__(self):
        super().__init__()  # yes it is required!
        self.alarm = None

    def set_alarm(self, alarm):
        """ Sets the alarm """
        self.alarm = alarm

    def start(self):
        pass


class AsyncQueueInterface(Interface):
    def __init__(self):
        super().__init__()

        self._started = asyncio.Event()
        self._is_stopped = True
        self.queue = asyncio.queues.PriorityQueue()

    def start(self):
        asyncio.get_event_loop().create_task(self.run())

    def stop(self):
        self.queue.put_nowait((0, None,))

    def is_alive(self):
        if self._is_stopped or not self._started.is_set():
            return False

        return not self._is_stopped

    async def run_loop(self, item):
        pass

    async def run(self):
        self._is_stopped = False
        self._started.set()
        while True:
            try:
                _, item = await self.queue.get()
                if item is None:
                    break
                else:
                    await self.run_loop(item)
            except Exception:
                logger.exception("ERROR in Run loop")

        self._is_stopped = True
        self._started.clear()


class ThreadQueueInterface(threading.Thread, Interface):
    def __init__(self):
        super().__init__()

        self.stop_running = threading.Event()
        self.stop_running.clear()

        self.queue = queue.PriorityQueue()

    def stop(self):
        self.queue.put_nowait((0, None,))
        self.join()

    def run_loop(self, queue_item):
        pass

    def run(self):
        while True:
            try:
                _, item = self.queue.get()
                if item is None:
                    break
                else:
                    self.run_loop(item)
            except Exception:
                logger.exception("ERROR in Run loop")

    def send_command(self, message):
        """Handle message received from the MQTT broker"""
        """Format TYPE LABEL COMMAND """

        message = cfg.COMMAND_ALIAS.get(message, message)

        tokens = message.split(" ")

        if len(tokens) != 3:
            logger.warning("Message format is invalid")
            return False

        if self.alarm is None:
            logger.error("No alarm registered")
            return False

        element_type = tokens[0].lower()
        element = tokens[1]
        command = self._normalize_payload(tokens[2].lower())

        # Process a Zone Command
        if element_type == 'zone':
            if command not in ['bypass', 'clear_bypass']:
                logger.error("Invalid command for Zone {}".format(command))
                return False

            if not self.alarm.control_zone(element, command):
                logger.warning(
                    "Zone command refused: {}={}".format(element, command))
                return False

        # Process a Partition Command
        elif element_type == 'partition':
            if command not in ['arm', 'disarm', 'arm_stay', 'arm_sleep']:
                logger.error(
                    "Invalid command for Partition {}".format(command))
                return False

            if not self.alarm.control_partition(element, command):
                logger.warning(
                    "Partition command refused: {}={}".format(element, command))
                return False

        # Process an Output Command
        elif element_type == 'output':
            if command not in ['on', 'off', 'pulse']:
                logger.error("Invalid command for Output {}".format(command))
                return False

            if not self.alarm.control_output(element, command):
                logger.warning(
                    "Output command refused: {}={}".format(element, command))
                return False
        else:
            logger.error("Invalid control property {}".format(element))
            return False

        return True

    @staticmethod
    def _normalize_payload(message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None
