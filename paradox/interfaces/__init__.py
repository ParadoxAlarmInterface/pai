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


class AsyncInterface(Interface):
    def __init__(self):
        super().__init__()

        self._loop = asyncio.get_event_loop()
        self._running_task = None  # type: asyncio.Task

    def start(self):
        self._running_task = self._loop.create_task(self.run())

    def stop(self):
        if self._running_task and not self._running_task.done():
            self._running_task.cancel()

    async def run(self):
        pass


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

