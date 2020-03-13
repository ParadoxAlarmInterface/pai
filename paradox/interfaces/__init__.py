# -*- coding: utf-8 -*-

import asyncio
import logging
import threading

logger = logging.getLogger("PAI").getChild(__name__)


class Interface:
    def __init__(self, alarm):
        super().__init__()  # yes it is required!
        self.name = self.__class__.__name__
        self.alarm = alarm

    def start(self):
        pass


class AsyncInterface(Interface):
    def __init__(self, alarm):
        super().__init__(alarm)

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
    def __init__(self, alarm):
        super().__init__(name=self.__class__.__name__)

        self.alarm = alarm

        self.stop_running = threading.Event()
        self.stop_running.clear()

    def stop(self):
        self.stop_running.set()
        if threading.current_thread() != self:
            self.join()
            logger.debug("Interface %s thread stopped", self.name)

    def run(self):
        try:
            self._run()
        except (KeyboardInterrupt, SystemExit):
            logger.debug("Interface loop stopping")
            self.stop()
        except:
            logger.exception("Interface loop")

    def _run(self):
        logger.info("Starting %s Interface", self.name)
