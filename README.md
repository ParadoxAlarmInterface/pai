# PAI - Paradox Alarm Interface

Python-based 'middleware' that aims to use any method to connect to a Paradox Alarm, exposing the interface for monitoring and control via several methods.

This is a complete rewrite from [ParadoxMulti-MQTT](https://github.com/jpbarraca/ParadoxMulti-MQTT)

It supports panels connected through a serial port, which is present in all panels, or through a USB 307 module.


Tested in the following environment:

* Python 3.5.2
* Mosquitto MQTT Broker v1.4.14
* OrangePi 2G-IOT, NanoPi NEO, Raspberry Pi 3 through their built in Serial Port (with a level switch!)
* Ubuntu Server 16.04.3 LTS
* Paradox MG5050 panel
* [Signal Cli](https://github.com/AsamK/signal-cli) through a DBUS interface
* Pushbullet.py


## Structure

* __Paradox__: Object that interfaces with the panel and keeps some internal state. Accepts commands to control partitions, zones and outputs. Exposes changes and events

* __Interfaces__: Expose interfaces to the outside world. Currently, MQTT, Signal and Pushbullet are supported, but other are planned and almost any other is supported.

* __Connections__: Handle communication with the panel, at a lower level. Currently, only Serial connections are supported.


## Steps to use it:
1.  Download the files in this repository and place it in some directory
```
git clone https://github.com/jpbarraca/pai.git
```

2.  Copy config_sample.py to config.py and edit it to match your setup
```
cp config_sample.py config.py
```

3.  Install the python requirements

```
pip3 install -r requirements.txt
```
3.  Run the script: 
```
python3 main.py
```



## MQTT

The MQTT Interface allows accessing all relevant states and setting some. The list of states will increase as the knowledge of the alarm internal memory and its states is improved.

All interactions are made through a ```MQTT_BASE_TOPIC```, which defaults to ```paradox```. States are exposed by name with a boolean payload (True or False) and are mainly update by the alarm status messages, updated every ```KEEP_ALIVE_INTERFACE``` seconds.

### States 
* ```paradox/states/partitions/name/property```: Exposes Partition properties where ```name``` identifies the Partition name (e.g. Interior) and ```property``` identifies the property (e.g. ```arm```). 
* ```paradox/states/zones/name/property```: Exposes Partition properties where ```name``` identifies the Zone name (e.g. Kitchen) and ```property``` identifies the property (e.g. ```open```). 
* ```paradox/states/outputs/name/property```: Exposes Partition properties where ```name``` identifies the PGM name (e.g. Gate) and ```property``` identifies the property.

### Events
* ```paradox/states/raw```: Exposes raw event information, composed by a minor and major codes, as well as descriptive text. The payload is a JSON object with the following structure:
```
    {
        'major': (major_code, 'major_text'), 
        'type': 'event_type', 
        'minor': (minor_code, 'minor_text')
    }

```

* ```major_code```  and ```major_text``` represent the major code and corresponding text description as provided by the alarm. This will mostly identify the event.
* ```minor_code```  and ```minor_text``` represent the minor code and corresponding text description as provided by the alarm. This will mostly identify a detail of the event, such as the zone number/name, the user name, partition name, and so on.
* ```type``` identifies the event category, and can take the following values: ```Partition```, ```Bell```, ```NonReportable```, ```User```, ```Remote```, ```Special```, ```Trouble```, ```Software```, ```Output```, ```Wireless```, ```Bus Module```, ```Zone```, ```System```.


### Control

The MQTT Interface allows setting some properties for individual objects by specifying the correct name. In alternative, the ```all``` keyword can be used to apply the same setting to all objects. This is useful to activate all PGMs or to Arm/Disarm all partitions.

* ```paradox/control/partitions/name``` allow setting some partition properties where ```name``` identifies the partition. If the ```name``` is ```all```, all partitions will be updated. The payload can have the values ```arm```, ```arm_stay```, ```arm_sleep``` or ```disarm```.
* ```paradox/control/zones/name``` allow setting some zone properties where ```name``` identifies the partition. If the ```name``` is ```all```, all zones will be updated. The payload can have the values ```bypass``` and ```clear_bypass```.
* ```paradox/control/outputs/name``` allow setting some zone properties where ```name``` identifies the partition. If the ```name``` is ```all```, all outputs will be updated. The payload can have the values ```pulse```, ```on``` (or ```true```, ```1```, ```enable```), or ```off``` (or ```false```, ```0```, ```disable```).


### Code Toggle

Sometimes it is useful to toggle the ARM state through a remote device, such as a NFC reader. Therefore, Partitions arm state can be toggled by issuing a special command with the format ```code_toggle-code_number``` (e.g., code_toggle-123456755). The ```code_toggle-``` keyword is constant, while the ```code_number``` is provided by the card (e.g., Card ID). If the code is present in the ```MQTT_TOGGLE_CODES```, the partition state will be toggled.

The ```MQTT_TOGGLE_CODES``` should be composed by a dictionary where the key contains the code, and the value contains a description. This allows for easily sending notifications in the form: "Alarm unlocked by USERNAME".

This was throughly tested with [ESPEasy](https://www.letscontrolit.com/) running on a ESP8266 board (e.g. NodeMCU or Wemos D1 Mini) connected to a PN532 NFC reader.
Besides the typical ESPEasy configuration, the only "code" required is a simple rule. The following example will publish any ID to the correct topic and will flash a LED for 2 seconds.

```
on reader#tag do
   Publish paradox/control/partitions/all,code_toggle-[reader#tag]
   Pulse,2,0,2000
endon
```

```reader#tag``` identifies the ESPEasy PN532 device name (```reader```) and the property holding the RFID ID (```tag```).


## Signal

The Signal Interface allows accessing major state changes and arming/disarming partitions through the [WhisperSystems](https://www.whispersystems.org/) Signal service. You will require the corresponding mobile application in your smartphone. As this interface will produce notifications to other devices, and are destined to users, only a subset of the events are sent.

Interface with Signal is made through [Signal-CLI](https://github.com/AsamK/signal-cli) running in system dbus mode. Follow the instruction to enable ```Signal-CLI``` and it should work automatically. You will require a valid phone number to be allocated to this service.

The configuration setting ```SIGNAL_CONTACTS``` should contain a list with the contacts used for signal notifications. If the list is empty, the Signal module is disabled.


## Pushbullet

The Pushbullet Interface allows accessing major state changes and arming/disarming partitions. As this interface will produce notifications to other devices, and are destined to users, only a subset of the events are sent.

In order to use this interface, please set the relevant configuration settings. The ```PUSHBULLET_CONTACTS``` setting should contain a list of contacts used for pushbullet notifications.


## Acknowledgments

This work is inspired or uses parts from the following projects:

* Tertiush at https://github.com/Tertiush/ParadoxIP150v2
* Spinza at https://github.com/spinza/paradox_mqtt
