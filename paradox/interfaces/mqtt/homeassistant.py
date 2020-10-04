import asyncio
import json
import logging
import typing
from collections import namedtuple

from paradox.config import config as cfg
from paradox.lib import ps
from paradox.lib.utils import sanitize_key

from ...data.model import DetectedPanel
from .core import AbstractMQTTInterface

logger = logging.getLogger("PAI").getChild(__name__)

PreparseResponse = namedtuple("preparse_response", "topics element content")


class HomeAssistantMQTTInterface(AbstractMQTTInterface):
    def __init__(self, alarm):
        super().__init__(alarm)
        self.armed = dict()
        self.partitions = {}
        self.zones = {}
        self.pgms = {}

        self.availability_topic = self.mqtt.availability_topic
        self.run_status_topic = self.mqtt.run_status_topic

        self.connected_future = (
            asyncio.Future()
        )  # TODO: do not create it, use some other
        panel_detected_future = asyncio.Future()
        first_status_update_future = asyncio.Future()

        def _ready_future_callback(x):
            self._publish_when_ready(
                panel_detected_future.result()["panel"],
                first_status_update_future.result()["status"],
            )

        ready_future = asyncio.ensure_future(
            asyncio.gather(
                self.connected_future, panel_detected_future, first_status_update_future
            )
        )
        ready_future.add_done_callback(_ready_future_callback)

        ps.subscribe(panel_detected_future, "panel_detected")
        ps.subscribe(self._handle_labels_loaded, "labels_loaded")
        ps.subscribe(first_status_update_future, "status_update")

    def on_connect(self, client, userdata, flags, result):
        # TODO: do not create connected_future, use some other
        if not self.connected_future.done():
            self.connected_future.set_result(True)

    def _handle_labels_loaded(self, data):
        partitions = data.get("partition", {})
        for k, v in partitions.items():
            p_data = {}
            p_data.update(v)
            self.partitions[k] = p_data

        self.zones = data.get("zone", {})
        self.pgms = data.get("pgm", {})

    def _publish_when_ready(self, panel: DetectedPanel, status):
        device = dict(
            manufacturer="Paradox",
            model=panel.model,
            identifiers=["Paradox", panel.model, panel.serial_number],
            name=panel.model,
            sw_version=panel.firmware_version,
        )

        self._publish_run_state_sensor(device, panel.serial_number)
        if "partition" in status:
            self._process_partition_statuses(
                status["partition"], device, panel.serial_number
            )
        if "zone" in status:
            self._process_zone_statuses(status["zone"], device, panel.serial_number)
        if "pgm" in status:
            self._process_pgm_statuses(status["pgm"], device, panel.serial_number)
        if "system" in status:
            self._process_system_statuses(status['system'], device, panel.serial_number)

    def _publish_run_state_sensor(self, device, device_sn):
        configuration_topic = "{}/sensor/{}/{}/config".format(
            cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX, device_sn, "run_status"
        )

        config = dict(
            name=f'Paradox {device_sn} PAI Status',
            unique_id=f'paradox_{device_sn}_pai_status',
            state_topic=self.run_status_topic,
            # availability_topic=self.availability_topic,
            device=device,
        )

        self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

    def _process_partition_statuses(self, partition_statuses, device, device_sn):
        for p_key, p_status in partition_statuses.items():
            if p_key not in self.partitions:
                continue
            partition = self.partitions[p_key]
            key = sanitize_key(partition["key"])

            # Publish Alarm Panel
            state_topic = "{}/{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_STATES_TOPIC,
                cfg.MQTT_PARTITION_TOPIC,
                key,
                "current_state",
            )

            configuration_topic = "{}/alarm_control_panel/{}/{}/config".format(
                cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                device_sn,
                key
            )
            command_topic = "{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_CONTROL_TOPIC,
                cfg.MQTT_PARTITION_TOPIC,
                key
            )

            config = dict(
                name=f'Paradox {device_sn} Partition {partition["key"]}',
                unique_id=f'paradox_{device_sn}_partition_{key.lower()}',
                command_topic=command_topic,
                state_topic=state_topic,
                availability_topic=self.availability_topic,
                device=device,
                payload_disarm="disarm",
                payload_arm_home="arm_stay",
                payload_arm_away="arm",
                payload_arm_night="arm_sleep",
                force_update=True
            )
            self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)
            
            # Publish individual entities

            for status in p_status:

                topic = "{}/{}/{}/{}/{}".format(
                    cfg.MQTT_BASE_TOPIC,
                    cfg.MQTT_STATES_TOPIC,
                    cfg.MQTT_PARTITION_TOPIC,
                    key,
                    status,
                )

                config = dict(
                    name=f'Paradox {device_sn} Partition {partition["key"]} {status.replace("_"," ").title()}',
                    unique_id=f'paradox_{device_sn}_partition_{key.lower()}_{status}',
                    state_topic=topic,
                    availability_topic=self.availability_topic,
                    payload_on="True",
                    payload_off="False",
                    device=device,
                    force_update=True
                )

                configuration_topic = "{}/binary_sensor/{}/partition_{}_{}/config".format(
                    cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                    device_sn,
                    key, 
                    status)

                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

    def _process_zone_statuses(self, zone_statuses, device, device_sn):
        for z_key, p_status in zone_statuses.items():

            if z_key not in self.zones:
                continue
            
            zone = self.zones[z_key]
            key = sanitize_key(zone["key"])
            
            # Publish command
                
            topic = "{}/{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_STATES_TOPIC,
                cfg.MQTT_ZONE_TOPIC,
                key,
                "bypassed",
            )
            
            command_topic = "{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_CONTROL_TOPIC,
                cfg.MQTT_ZONE_TOPIC,
                key,
            )
            
            config = dict(
                name=f'Paradox {device_sn} Zone {zone["key"]} Bypass',
                unique_id=f'paradox_{device_sn}_zone_{key.lower()}_bypass',
                state_topic=topic,
                availability_topic=self.availability_topic,
                command_topic=command_topic,
                payload_on="bypass",
                payload_off="clear_bypass",
                state_on="True",
                state_off="False",
                device=device,
                force_update=True
            )
            configuration_topic = "{}/switch/{}/zone_{}_bypass/config".format(
                cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                device_sn, 
                key,
            )
                
            self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

            # Publish Status
            for status in p_status:

                topic = "{}/{}/{}/{}/{}".format(
                    cfg.MQTT_BASE_TOPIC,
                    cfg.MQTT_STATES_TOPIC,
                    cfg.MQTT_ZONE_TOPIC,
                    key,
                    status,
                )

                config = dict(
                    name=f'Paradox {device_sn} Zone {zone["key"]} {status.replace("_"," ").title()}',
                    unique_id=f'paradox_{device_sn}_zone_{key.lower()}_{status}',
                    state_topic=topic,
                    availability_topic=self.availability_topic,
                    payload_on="True",
                    payload_off="False",
                    device=device,
                    force_update=True
                )
                
                if status == 'open':
                    config['device_class'] = 'motion'

                configuration_topic = "{}/binary_sensor/{}/zone_{}_{}/config".format(
                    cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                    device_sn, 
                    key,
                    status
                )
                
                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)

    def _process_pgm_statuses(self, pgm_statuses, device, device_sn):
        for pgm_key, p_status in pgm_statuses.items():
            if pgm_key not in self.pgms:
                continue

            pgm = self.pgms[pgm_key]
            key = sanitize_key(pgm["key"])

            on_topic = "{}/{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_STATES_TOPIC,
                cfg.MQTT_OUTPUT_TOPIC,
                key,
                "on",
            )

            command_topic = "{}/{}/{}/{}".format(
                cfg.MQTT_BASE_TOPIC,
                cfg.MQTT_CONTROL_TOPIC,
                cfg.MQTT_OUTPUT_TOPIC,
                key
            )

            config = dict(
                name=f'Paradox {device_sn} PGM {pgm["label"]} Open',
                unique_id=f'paradox_{device_sn}_pgm_{key.lower()}_open',
                state_topic=on_topic,
                command_topic=command_topic,
                availability_topic=self.availability_topic,
                device=device,
                force_update=True
            )

            configuration_topic = "{}/switch/{}/pgm_{}_open/config".format(
                cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                device_sn,
                key,
            )

            self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)
    
    def _process_system_statuses(self, system_statuses, device, device_sn):
        for system_key, p_status in system_statuses.items():
            for status in p_status:
                
                topic = "{}/{}/{}/{}/{}".format(
                    cfg.MQTT_BASE_TOPIC,
                    cfg.MQTT_STATES_TOPIC,
                    cfg.MQTT_SYSTEM_TOPIC,
                    system_key,
                    status,
                )

                config = dict(
                    name=f'Paradox {device_sn} System {system_key.title()} {status.replace("_"," ").title()}',
                    unique_id=f'paradox_{device_sn}_system_{system_key}_{status}',
                    state_topic=topic,
                    availability_topic=self.availability_topic,
                    device=device,
                    force_update=True
                )

                if system_key == 'troubles':
                    dev_type = 'binary_sensor'
                    config['payload_on'] = 'True'
                    config['payload_off'] = 'False'
                    config['device_class'] = 'problem'
                else:
                    dev_type = 'sensor'
                    if system_key == 'power':
                        config['unit_of_measurement'] = 'V'

                configuration_topic = "{}/{}/{}/{}_{}/config".format(
                    cfg.MQTT_HOMEASSISTANT_DISCOVERY_PREFIX,
                    dev_type,
                    device_sn,
                    system_key,
                    status
                )

                self.publish(configuration_topic, json.dumps(config), 0, cfg.MQTT_RETAIN)
