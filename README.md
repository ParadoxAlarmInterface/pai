# PAI — Paradox Alarm Interface

PAI connects Paradox alarm panels to home automation through MQTT. It integrates
with Home Assistant, Homebridge, OpenHAB, and other MQTT clients.

The code includes drivers for Digiplex, EVO, Spectra/Magellan, and MG6250
(partial support). Compatible panels can also connect through a PRT3 module.
Compatibility depends on the panel model, firmware, and connection method.

## Documentation

- [Installation](https://github.com/ParadoxAlarmInterface/pai/wiki/Installation)
- [Configuration](https://github.com/ParadoxAlarmInterface/pai/wiki/Configuration)
- [Connection methods](https://github.com/ParadoxAlarmInterface/pai/wiki/Connection-methods)
- [Compatibility reports](https://github.com/ParadoxAlarmInterface/pai/wiki/Compatibility)
- [Integration guides](https://github.com/ParadoxAlarmInterface/pai/wiki)

For help or discussion, join the [Discord community](https://discord.gg/6KaXFtg39r)
or [report an issue](https://github.com/ParadoxAlarmInterface/pai/issues).

## Authors

* João Paulo Barraca - [@jpbarraca](https://github.com/jpbarraca) - Main code and MG/SP devices
* Jevgeni Kiski - [@yozik04](https://github.com/yozik04) - Main code and EVO devices
* Ion Darie - [@iondarie](https://github.com/iondarie) - PAI Logo, Homebridge integration, testing
* Ricardas - [@richka](https://github.com/richka) - Digiplex (DGP-48/848/NE96)
* Sylvain Pelissier - [@sylvainpelissier](https://github.com/sylvainpelissier) - MG6250
* Naanya Biz - [@NaanyaBiz](https://github.com/NaanyaBiz) - PRT3

## Acknowledgments

Inspired by [Tertiush/ParadoxIP150v2](https://github.com/Tertiush/ParadoxIP150v2)
and [spinza/paradox_mqtt](https://github.com/spinza/paradox_mqtt). Thanks to
[@ivmarkov](https://github.com/ivmarkov), [@clau-bucur](https://github.com/clau-bucur),
and [@tekand](https://github.com/tekand) for their contributions.
