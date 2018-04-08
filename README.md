# PAI - Paradox Alarm Interface

Python-based 'middleware' that aims to use any method to connect to a Paradox Alarm, exposing the interface for monitoring and control via an MQTT Broker. 

This is a complete rewrite from [ParadoxMulti-MQTT](https://github.com/jpbarraca/ParadoxMulti-MQTT)

___Alfa stage! Expect bugs.___

Tested in the following environment:

* Python 3.5.2
* Mosquitto MQTT Broker v1.4.14
* OrangePi 2G-IOT, NanoPi NEO, Raspberry Pi 3 through their built in Serial Port (with a level switch!)
* Ubuntu Server 16.04.3 LTS
* Paradox MG5050 panel


# Acknowledgments

This work is inspired or uses parts from the following projects:

* Tertiush at https://github.com/Tertiush/ParadoxIP150v2
* Spinza at https://github.com/spinza/paradox_mqtt
