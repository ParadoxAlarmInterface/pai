<div align="center">
    <div style="display: flex;">
        <a href="https://matrix.to/#/#paradox-alarm-interface_community:gitter.im">
            <img alt="Matrix" src="https://img.shields.io/matrix/pai:gitter.im.svg">
        </a>
        #paradox-alarm-interface_community:gitter.im
        <a href="https://github.com/ParadoxAlarmInterface/pai/actions/workflows/master.yml">
            <img alt="CI/CD master" src="https://github.com/ParadoxAlarmInterface/pai/actions/workflows/master.yml/badge.svg?branch=master">
        </a>
        <a href="https://github.com/ParadoxAlarmInterface/pai/actions/workflows/dev.yml">
            <img alt="CI/CD dev" src="https://github.com/ParadoxAlarmInterface/pai/actions/workflows/dev.yml/badge.svg?branch=dev">
        </a>
        <a href="https://hub.docker.com/r/paradoxalarminterface/pai">
            <img alt="Docker Arch" src="https://img.shields.io/badge/docker_arch-386%7Camd64%7Carmv6%7Carmv7%7Carm64-green?logo=docker">
            <img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/paradoxalarminterface/pai?logo=docker">
        </a>
        <a href="https://snyk.io/test/github/ParadoxAlarmInterface/pai?targetFile=requirements.txt">
            <img src="https://snyk.io/test/github/ParadoxAlarmInterface/pai/badge.svg?targetFile=requirements.txt" alt="Known Vulnerabilities" data-canonical-src="https://snyk.io/test/github/ParadoxAlarmInterface/pai?targetFile=requirements.txt" style="max-width:100%;">
        </a>
        <img alt="GitHub" src="https://img.shields.io/github/license/ParadoxAlarmInterface/pai">
    </div>
</div>

<br/>
<p align="center">
<img src="https://github.com/ParadoxAlarmInterface/pai/raw/master/docs/pai_logo.png">
</p>
<h1 align="center">PAI - Paradox Alarm Interface</h1>

Middleware that aims to connect to a Paradox Alarm panel, exposing the interface for monitoring and control via several technologies.
With this interface it is possible to integrate Paradox panels with HomeAssistant, OpenHAB, Homebridge or other domotics system that supports MQTT, as well as several IM methods.

It supports MG/SP/EVO panels (firmwares below 7.50.000) connected through a serial port, which is present in all panels (TTL 5V), or through a USB 307 module. It also supports connections using the IP150 module, both directly (ip module firmware version < 4.0 or >= 4.40.004), and through the SITE ID (firmware versions >4.0).

Support for Magellan, Spectra and EVO panels is very stable. If you find a bug, please report it.


For further information and detailed usage refer to the [Wiki](https://github.com/ParadoxAlarmInterface/pai/wiki).

If you are having issues, or wish to discuss new features, join us at our [Matrix community](https://matrix.to/#/#paradox-alarm-interface_community:gitter.im)

On Android, if you install [MQTT Dash](https://play.google.com/store/apps/details?id=net.routix.mqttdash), and [follow the instructions](https://github.com/ParadoxAlarmInterface/pai/wiki#mqtt-dash) you will automatically get a panel like this:
![mqtt_dash](https://user-images.githubusercontent.com/497717/52603920-d4984d80-2e60-11e9-9772-578b10576b3c.jpg)

## Things you need to have to be able to connect
We support two [connection options](https://github.com/ParadoxAlarmInterface/pai/wiki/Connection-methods): via [Serial](https://github.com/ParadoxAlarmInterface/pai/wiki/Connection-methods#serial-connection) and via [IP150 Module](https://github.com/ParadoxAlarmInterface/pai/wiki/Connection-methods#ip-module-connection-IP100-IP150).

#### For all connection methods
- **PC Password:** 4 digit `[0-9a-f]` password.
Can be looked up in Babyware (_Right click on a panel ⇾ Properties ⇾ PC Communication (BabyWare) ⇾ PC Communication (BabyWare) ⇾ PC Password_)
#### In case of IP150 you need additionally:
- **IP Module password**: Default is `paradox`
##### For IP150 firmware > 4.0 if you connect via Paradox Cloud (SWAN)
- **SITE ID**
- **Email registered in the site**

We do not recommend using SWAN because of https://github.com/CriticalSecurity/paradox

## Firmware Upgrade WARNING:
**Do not upgrade EVO firmware versions to 7.50.000+ if you use Serial connection. Process is irreversible! Paradox introduces serial communication encryption which most probably will break our PAI ability to talk to the panel.**

## How to use
See [wiki](https://github.com/ParadoxAlarmInterface/pai/wiki/Installation)

## Tested Environment

Tested in the following environment:
* Python 3.6, 3.7, 3.8, 3.9, 3.10, 3.11
* Mosquitto MQTT Broker > 1.4.8
* OrangePi 2G-IOT, NanoPi NEO, and Raspberry Pi 3 through their built in Serial Port (with a level shifter!), or a USB RS232 TTL adapter (CP2102, PL2303, CH340, etc..)
* Ubuntu Server 16.04.3 LTS
* Paradox MG5050, SP7000 and EVO panels
* [Signal Cli](https://github.com/AsamK/signal-cli) through a DBUS interface
* Pushbullet.py
* SIM900 module through a serial port
* Serial over TCP (ESP32 or Arduino connected to the panel's serial port acts as a proxy)

## Authors

* João Paulo Barraca - [@jpbarraca](https://github.com/jpbarraca) - Main code and MG/SP devices
* Jevgeni Kiski - [@yozik04](https://github.com/yozik04) - Main code and EVO devices
* Ion Darie - [@iondarie](https://github.com/iondarie) - PAI Logo, Homebridge integration, testing


## Acknowledgments

This work is inspired or uses parts from the following projects:

* Tertiush at https://github.com/Tertiush/ParadoxIP150v2
* Spinza at https://github.com/spinza/paradox_mqtt

## Thanks
* Ivan Markov - [@ivmarkov](https://github.com/ivmarkov) - Multi-platform Docker builds
* Claudiu Bucur - [@clau-bucur](https://github.com/clau-bucur) - For fixing HomeAssistant plugin after Supervisor(2021.02.5) upgrade [#199](https://github.com/ParadoxAlarmInterface/pai/issues/199)
* David Tekan - [@tekand](https://github.com/tekand) - For supporting different label encodings.

## Disclaimer

Paradox, MG5050 and IP150 are registered marks of PARADOX. Other brands are owned by their respective owners.

The code was developed as a way of integrating personally owned Paradox systems, and it cannot be used for other purposes.
It is not affiliated with any company and it doesn't have have commercial intent.

The code is provided AS IS and the developers will not be held responsible for failures in the alarm systems, or any other malfunction.

## Donations

We have fully stopped accepting donations due to lack of free time to spend on this project.

[//]: # (## With support from)

[//]: # ()
[//]: # (<a href="https://www.jetbrains.com/?from=PAI-ParadoxAlarmInterface"><img src="/docs/jetbrains.svg" alt="JetBrains"/></a>)
