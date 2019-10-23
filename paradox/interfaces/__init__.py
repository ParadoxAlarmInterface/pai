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

