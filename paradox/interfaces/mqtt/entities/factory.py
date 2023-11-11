from paradox.interfaces.mqtt.entities.alarm_control_panel import AlarmControlPanel
from paradox.interfaces.mqtt.entities.binary_sensors import ZoneStatusBinarySensor, \
    SystemBinarySensor, PartitionBinarySensor
from paradox.interfaces.mqtt.entities.sensor import PAIStatusSensor, SystemStatusSensor, ZoneNumericSensor
from paradox.interfaces.mqtt.entities.switch import ZoneBypassSwitch, PGMSwitch


class MQTTAutodiscoveryEntityFactory:
    def __init__(self, availability_topic, device=None):
        self.availability_topic = availability_topic
        self.device = device

    def set_device(self, device):
        self.device = device

    def make_alarm_control_panel_config(self, partition, code: str = None):
        return AlarmControlPanel(partition, self.device, self.availability_topic, code)

    def make_partition_status_binary_sensor(self, partition, status):
        return PartitionBinarySensor(partition, status, self.device, self.availability_topic)

    def make_pai_status_sensor(self, pai_status_topic):
        return PAIStatusSensor(pai_status_topic, self.device, self.availability_topic)

    def make_zone_bypass_switch(self, zone):
        return ZoneBypassSwitch(zone, self.device, self.availability_topic)

    def make_zone_status_binary_sensor(self, zone, status):
        return ZoneStatusBinarySensor(zone, status, self.device, self.availability_topic)

    def make_zone_status_numeric_sensor(self, zone, status):
        return ZoneNumericSensor(zone, status, self.device, self.availability_topic)

    def make_pgm_switch(self, pgm):
        return PGMSwitch(pgm, self.device, self.availability_topic)

    def make_system_status(self, system_key, status):
        if system_key == 'troubles':
            return SystemBinarySensor(system_key, status, self.device, self.availability_topic)
        else:
            return SystemStatusSensor(system_key, status, self.device, self.availability_topic)
