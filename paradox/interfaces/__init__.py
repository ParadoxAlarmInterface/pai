# -*- coding: utf-8 -*-

import threading
import queue

from paradox.config import config as cfg
from paradox.event import Event


class Interface(threading.Thread):

    def __init__(self):
        super().__init__()

        self.alarm = None
        self.logger = None  # assign logger in the subclass
        self.partitions = {}

        self.stop_running = threading.Event()
        self.stop_running.clear()

        self.queue = queue.PriorityQueue()

    def set_alarm(self, alarm):
        """ Sets the alarm """
        self.alarm = alarm

    def stop(self):
        pass

    def notify(self, source, message, level):
        pass

    def run(self):
        pass

    def handle_notify(self, raw):
        source, message, level = raw

        try:
            self.send_message(message)
        except Exception:
            self.logger.exception("handle_notify")

    def handle_panel_event(self, event):
        """Handle Live Event"""
        pass

    def send_command(self, message):
        """Handle message received from the MQTT broker"""
        """Format TYPE LABEL COMMAND """

        message = cfg.COMMAND_ALIAS.get(message, message)

        tokens = message.split(" ")

        if len(tokens) != 3:
            self.logger.warning("Message format is invalid")
            return False

        if self.alarm is None:
            self.logger.error("No alarm registered")
            return False

        element_type = tokens[0].lower()
        element = tokens[1]
        command = self.normalize_payload(tokens[2].lower())

        # Process a Zone Command
        if element_type == 'zone':
            if command not in ['bypass', 'clear_bypass']:
                self.logger.error("Invalid command for Zone {}".format(command))
                return False

            if not self.alarm.control_zone(element, command):
                self.logger.warning(
                    "Zone command refused: {}={}".format(element, command))
                return False

        # Process a Partition Command
        elif element_type == 'partition':
            if command not in ['arm', 'disarm', 'arm_stay', 'arm_sleep']:
                self.logger.error(
                    "Invalid command for Partition {}".format(command))
                return False

            if not self.alarm.control_partition(element, command):
                self.logger.warning(
                    "Partition command refused: {}={}".format(element, command))
                return False

        # Process an Output Command
        elif element_type == 'output':
            if command not in ['on', 'off', 'pulse']:
                self.logger.error("Invalid command for Output {}".format(command))
                return False

            if not self.alarm.control_output(element, command):
                self.logger.warning(
                    "Output command refused: {}={}".format(element, command))
                return False
        else:
            self.logger.error("Invalid control property {}".format(element))
            return False

        return True

    @staticmethod
    def normalize_payload(message):
        message = message.strip().lower()

        if message in ['true', 'on', '1', 'enable']:
            return 'on'
        elif message in ['false', 'off', '0', 'disable']:
            return 'off'
        elif message in ['pulse', 'arm', 'disarm', 'arm_stay', 'arm_sleep', 'bypass', 'clear_bypass']:
            return message

        return None

    def send_message(self, message):
        pass
