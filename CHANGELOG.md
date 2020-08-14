# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2020-08-14
Very large release

### Added
- Time syncing only when there is a large drift. Controlled by `SYNC_TIME_MIN_DRIFT`
- MQTT TLS support
- New tags added for `*_EVENT_FILTERS` properties: `entry_delay`, `entry_delay_finished`, `exit_delay`, `exit_delay_finished`
- PAI service stops if detects critical exception like wrong password or serial port not available
- SP/MG wrong password detection
- EVO: PGM status reading and controlling. Switches added to HomeAssistant autodiscovery.
- EVO: user names who armed or disarmed partition.
- EVO: Loads user definition
- EVO: User/Card door access messages
- Label encodings: `paradox-en` and `paradox-ru`. See [#146](https://github.com/ParadoxAlarmInterface/pai/issues/146)
- Memory dump console script `pai-dump-memory`
- Configuration file search logic improved. Looks in current dir, `~/.local/etc`, `/etc/pai`, `/usr/local/etc/pai`.
File names scanned: `pai.conf`, `pai.json`, `pai.yaml`
- Configuration: `MQTT_BIND_ADDRESS` default matches Paho MQTT default
- Configuration: `MQTT_PUBLISH_DEFINITIONS` default `False`. Publishes zone, partition, user definitions to MQTT. A lot of data on boot.
- Configuration: `MQTT_PUBLISH_COMMAND_STATUS` default `False`. Sends textual command statuses to mqtt.
- Configuration: `IP_INTERFACE_PASSWORD` accepts `string` type

### Changed
- `*_EVENT_FILTERS` defaults changed that selects only live events.
- Partition `current_state` property states: `pending` changed to `arming`
- AES crypto performance improvements. Python can't do faster.
- Serial connection modules are not required for installation if they are not used.
- Docker: No builds for arm/v7 as arm/v6 is fully compatible with it.

### Refactoring
- Large refactoring of all connection code
- IP Interface rewrite

### Alpha
- EVO: Alpha Door actions: [#165](https://github.com/ParadoxAlarmInterface/pai/issues/165)
- Trigger alarm via mqtt in new firmwares: [#162](https://github.com/ParadoxAlarmInterface/pai/issues/162)
- Alpha attempt on HomeAssistant notifications. Controlled by `HOMEASSISTANT_NOTIFICATIONS*` settings.

## [2.1.0] - 2020-02-08

### Added
- Configuration: `PUSHBULLET_DEVICE` option added

### Changed
- Some MQTT bug fixes

## [2.0.2] - 2020-02-07

### Changed
- Homeassistant and Basic MQTT Interface bug fixes

## [2.0.1] - 2020-02-03

### Changed
- Serial connection exceptions fix

## [2.0.0] - 2020-02-03
### Added
- Docker: Installing tzdata package. Fixes [Time zone not correct](https://github.com/ParadoxAlarmInterface/hassio-repository/issues/7)
- Python 3.6+ check.
- In case of a wrong password PAI stops. Prevents panel locking due to many retries with a wrong password.
- All events and commands are scheduled in a run loop for later processing.

### Changed

- Hass.io: Container does not use host network anymore. Please update `MQTT_HOST` to use real IP address or IP address of a docker interface. `localhost`, `127.0.0.1` will stop working.
- MQTT Interfaces now do their work in a separate threads and asyncio run loops. Frees main loop for more urgent work. Probably fixes #89, #126
- `Paradox` class methods changed to async only: `connect`, `loop`, `control_zone`, `control_partition`, `control_output`

### Removed

- Dependencies: PyPubSub fully removed from dependencies and replaced with our own async version.


## [1.5.0] - 2020-01-20
### Added
- MQTT: Added `paradox/interface/run_status` and has more statuses: `error, initializing, paused, online, stopped, offline`
- MQTT: Added `paradox/interface/availability` that has only `online`, `offline` statuses. Basically it is replacement for `MQTTInterface` but has more strict `online` status.
- Proper `SIGTERM` handling. Docker containers do not die instantly but shutdown gracefully.
- PAI reports it's version in logs.
- PAI logs executed command result

### Changed

- Configuration: `0` in`PASSWORD` is not encoded to `a` anymore. If you have problems see [FAQ](https://github.com/ParadoxAlarmInterface/pai/wiki/FAQ#authentication-failed-wrong-password)
- Configuration: `STATUS_REQUESTS` config parameter removed. Panels know what they need.
- MQTT: `paradox/interface/MQTTInterface` removed.
- Dependencies: Sticking to `construct 2.9`.
- Less CRITICAL events in SP/MG
- Some GSM interface fixes
- setup.py improvements

## [1.4.0] - 2020-01-02
### Added

- EVOHD definitions for enabled zone and partition detection.
- Docker platforms i386, amd64, arm64, armv7
- EVO PGM Control (State reading is not yet implemented)
- IPInterface to consider asyncio locks

### Changed

- Configuration: SYNC_TIME off by default. Make sure you turn it on in configuration

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
