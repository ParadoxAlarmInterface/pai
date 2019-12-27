# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - 2019-12-27
### Changed

- Dockerfile passes config file path via environment variable


## [1.3.0] - 2019-12-26
### Added

- Reading configuration from json, yaml, py, conf files. Preparations for HASS.io addon

## [1.2.0] - 2019-12-26
### Added

- Python 3.8 support
- `IP_CONNECTION_BARE` If you want to connect to panel via Serial over TCP tunnel instead of IP150.
- Enabled Zone autodetection. Remove setting from `LIMITS` for autodetection.
- EVO only: Enabled partition autodetection. Remove setting from `LIMITS` for autodetection.
- Batch EEPROM reading during boot. Should load data faster from EEPROM (labels, definitions).
- MQTT: `paradox/definitions/zones`(EVO/SP/MG), `paradox/definitions/partitions`(EVO).

### Changed

- Config: `MQTT_HOST` default is now `127.0.0.1`
- Docker uses Python 3.7
- run.sh fix

### Removed

- Python 3.5 support

## [1.1.1] - 2017-12-12
### Added

- MQTT_BIND_PORT setting to specify which port to use for MQTT server->client connection
- `run.sh` instead of `run.py`. Just calls `paradox/console_scripts/pai_run.py`

### Changed

- Pushbullet fixes
- Requirement paho_mqtt>=1.5.0

### Removed

- `run.py`

## [1.1.0] - 2019-12-09
Large rewrite. More than 160+ commits merged.
### Added

- HomeAssistant MQTT autodiscovery. Enabled via `MQTT_HOMEASSISTANT_AUTODISCOVERY_ENABLE` config setting
- MQTT: `paradox/states/partitions/First_floor/current_state`. Replaces `current` and `current_hass`
- MQTT: `paradox/states/partitions/First_floor/target_state`. For Homebridge.
- MQTT: `time`, `vdc`, `dc`, `battery`, `rf_noise_floor` topics moved under system and got new names (`date`, `power/vdc`, `power/battery`, `power/dc`, `rf/noise_floor`)
- Config: `PASSWORD` can be string, bytesting or even int. `0000` is automatically translated to None
- Event filtering using tags and event levels. See `*_MIN_EVENT_LEVEL`, `*_EVENT_FILTERS` settings. Provides easier notification configuration than use of regexps(`*_ALLOW_EVENTS` and `*_IGNORE_EVENTS`)
- Help if some dependency is not installed.
- Faster alarm trigger notifications via interfaces
- EVO: zone bypass control

### Changed

- `PUSHBULLET_SECRET` renamed to `PUSHBULLET_KEY`. Fixes bug.
- `IP_INTERFACE_PASSWORD` default changed to `paradox`.
- Faster message processing without a special worker.
- All interfaces rewrites/improvements. Less thread usage.

### Removed

- MQTT: `paradox/states/partitions/First_floor/current_hass`
- MQTT: `paradox/states/partitions/First_floor/current`
- Config: `MQTT_HOMEBRIDGE_*`, `MQTT_HOMEASSISTANT_*`, `MQTT_PARTITION_HOMEASSISTANT_*`


## [1.0.0] - 2019-11-26
First release