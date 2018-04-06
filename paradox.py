from paradox_messages import *
from serial_connection import *
import logging
import sys
import time

class Paradox:
    MEM_STATUS_BASE1 = 0x8000
    MEM_STATUS_BASE2 = 0x1fe0
    MEM_ZONE_START = 0x010
    MEM_ZONE_END = 0x01f0
    MEM_OUTPUT_START = 0x210
    MEM_OUTPUT_END = 0x2f0
    MEM_PARTITION_START = 0x310
    MEM_PARTITOIN_EnD = 0x310

    def __init__(self, connection, interface, config, encrypted=0, retries=3, alarmeventmap="ParadoxMG5050"):

        self.connection = connection
        self.retries = retries
        self.encrypted = encrypted
        self.alarmeventmap = alarmeventmap
        self.mode = 0
        self.config = config
        self.interface = interface

        # Keep track of alarm state
        self.labels = {'zone': {}, 'partition': {}, 'output': {}}
        self.zones = []
        self.partitions = []
        self.outputs = []

    def connect(self): 
        try:
            message = MessageInitiateCommunication()
            reply = self.send_wait_for_reply(message)

            message = MessageSerialInitialization()
            reply = self.send_wait_for_reply(message)
            reply = self.send_wait_for_reply(reply)

            self.load_labels(self.zones, self.labels['zone'], MEM_ZONE_START, MEM_ZONE_END)
            self.load_labels(self.outputs, self.labels['output'], MEM_OUTPUT_START, MEM_OUTPUT_END)
            self.load_labels(self.partitions, self.labels['partition'], MEM_PARTITION_START, MEM_PARTITION_END)

            return True
        except:
            self.logger.exception("Unable to connect to alarm")
            return False

    def loop(self):
        message = MessageUpload() 
        message.number_of_bytes = 0
        message.bytes_to_read = 0
        message.filler = [0] * 29
        message.control_byte = 0
        message.start_address = 0

        while True:
            i = 0
            while i < 8:
                message.module_address = self.MEM_STATUS_BASE1 + i
                reply = self.send_wait_for_reply(message)
                self.handle_status(reply)
                i += 1

            message.module_address = self.MEM_STATUS_BASE2
            reply = self.send_wait_for_reply(message)
            self.handle_status(reply)
            
            # Listen for events    
            self.send_wait_for_reply(None)


    def send_wait_for_reply(self, message=None):
        
        if message is not None:
            send_message = message.pack()

        retries = self.retries
        while retries > 0:
            
            if message is not None:
                self.connection.write(send_message)

            data = self.connection.read()

            # Retry if no data was available
            if data is None or len(data) == 0:
                retries -= 1
                time.sleep(0.25)
                continue

            recv_message = decode_message(data)

            # Events are async
            if isinstance(recv_message, MessageLiveEvent):
                self.handle_event(recv_message)
                continue

            return recv_message
           
        return None

    def handle_event(self, message):
        """Handle MessageLiveEvent"""
        print(message)

    def handle_status(self, message):
        """Handle MessageStatus"""
        print(message)


    def load_labels(self, labelList, labelDict, start, end, step=0x10):
        """Load labels from panel"""
        message = MessageUpload() 
        message.number_of_bytes = 0
        message.start_address = 0
        message.bytes_to_read = 0
        message.filler = [0] * 29
        message.control_byte = 0

        i = 0
        for address in range(start, end + step, step):
            message.module_address = address
            reply = self.send_wait_for_reply(message)
            
            for j in [0, 16]:
                label = reply.payload[j:j+16].strip().decode('latin')

                if label not in labelDict.keys():
                    if len(labelList) <= i:
                        labelList.append({'label': label})
                    else:
                        labelList[i]['label']= label

                    labelDict[label] = i
                    i += 1 
