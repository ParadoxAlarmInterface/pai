<div align="left">
    <div style="display: flex;">
        <a href="https://gitter.im/paradox-alarm-interface/community">
            <img alt="Gitter" src="https://img.shields.io/gitter/room/paradox-alarm-interface/community?logo=gitter">
        </a>
        <a href="https://travis-ci.org/ParadoxAlarmInterface/pai">
            <img alt="Travis (.org) branch" src="https://img.shields.io/travis/ParadoxAlarmInterface/pai/master?label=master&logo=travis">
        </a>
        <a href="https://travis-ci.org/ParadoxAlarmInterface/pai/branches">
            <img alt="Travis (.org) branch" src="https://img.shields.io/travis/ParadoxAlarmInterface/pai/dev?label=dev&logo=travis">
        </a>
        <a href="https://hub.docker.com/r/paradoxalarminterface/pai">
            <img alt="Docker Arch" src="https://img.shields.io/badge/docker_arch-amd64%7Carmv7%7Carm64-green?logo=docker">
            <img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/paradoxalarminterface/pai?logo=docker">
        </a>
        <a href="https://travis-ci.org/ParadoxAlarmInterface/pai/branches">
            <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/ParadoxAlarmInterface/pai?label=python%203.5%2B&logo=python">
        </a>
	<a href="https://snyk.io/test/github/ParadoxAlarmInterface/pai?targetFile=requirements.txt">
	    <img src="https://snyk.io/test/github/ParadoxAlarmInterface/pai/badge.svg?targetFile=requirements.txt" alt="Known Vulnerabilities" data-canonical-src="https://snyk.io/test/github/ParadoxAlarmInterface/pai?targetFile=requirements.txt" style="max-width:100%;">
	</a>
        <img alt="GitHub" src="https://img.shields.io/github/license/ParadoxAlarmInterface/pai">
    </div>
</div>

# PAI - Paradox Alarm Interface

Middleware that aims to connect to a Paradox Alarm panel, exposing the interface for monitoring and control via several technologies.
With this interface it is possible to integrate Paradox panels with HomeAssistant, OpenHAB, Homebridge or other domotics system that supports MQTT, as well as several IM methods.

It supports MG/SP/EVO panels connected through a serial port, which is present in all panels (TTL 5V), or through a USB 307 module. It also supports connections using the IP150 module, both directly (firmware version <4.0), and through the SITE ID (firmware versions >4.0).

Support for Magellan, Spectra and EVO panels is very stable. If you find a bug, please report it.


For further information and detailed usage refer to the [Wiki](https://github.com/ParadoxAlarmInterface/pai/wiki).

If you are having issues, or wish to discuss new features, join us at our [Gitter community](https://gitter.im/paradox-alarm-interface)

On Android, if you install [MQTT Dash](https://play.google.com/store/apps/details?id=net.routix.mqttdash), and [follow the instructions](https://github.com/ParadoxAlarmInterface/pai/wiki#mqtt-dash) you will automatically get a panel like this:
![mqtt_dash](https://user-images.githubusercontent.com/497717/52603920-d4984d80-2e60-11e9-9772-578b10576b3c.jpg)

## Things you need to have to be able to connect
We support two connection options: via Serial and via IP150 Module

#### For all connection methods
- **PC Password:** 4 digit `[0-9a-f]` password.
Can be looked up in Babyware (_Right click on a panel ⇾ Properties ⇾ PC Communication (BabyWare) ⇾ PC Communication (BabyWare) ⇾ PC Password_)
#### In case of IP150 you need additionally:
- **IP Module password**: Default is `paradox`
##### For IP150 firmware > 4.0 if you connect via Paradox Cloud (SWAN)
- **SITE ID**
- **Email registered in the site**

## How to use
See [wiki](https://github.com/ParadoxAlarmInterface/pai/wiki/Installation)

## Tested Environment

Tested in the following environment:
* Python 3.6, 3.7, 3.8
* Mosquitto MQTT Broker >v 1.4.8
* OrangePi 2G-IOT, NanoPi NEO, and Raspberry Pi 3 through their built in Serial Port (with a level shifter!), or a USB RS232 TTL adapter (CP2102, PL2303, CH340, etc..)
* Ubuntu Server 16.04.3 LTS
* Paradox MG5050, SP7000 and EVO panels
* [Signal Cli](https://github.com/AsamK/signal-cli) through a DBUS interface
* Pushbullet.py
* SIM900 module through a serial port

## Authors

* João Paulo Barraca - [@jpbarraca](https://github.com/jpbarraca) - Main code and MG/SP devices
* Ion Darie - [@iondarie](https://github.com/iondarie) - Homebridge integration
* Jevgeni Kiski - [@yozik04](https://github.com/yozik04) - EVO devices

## Acknowledgments

This work is inspired or uses parts from the following projects:

* Tertiush at https://github.com/Tertiush/ParadoxIP150v2
* Spinza at https://github.com/spinza/paradox_mqtt

## Thanks
* Ivan Markov - [@ivmarkov](https://github.com/ivmarkov) - Multi-platform Docker builds with Travis

## Disclaimer

Paradox, MG5050 and IP150 are registered marks of PARADOX. Other brands are owned by their respective owners.

The code was developed as a way of integrating personally owned Paradox systems, and it cannot be used for other purposes.
It is not affiliated with any company and it doesn't have have commercial intent.

The code is provided AS IS and the developers will not be held responsible for failures in the alarm systems, or any other malfunction.
