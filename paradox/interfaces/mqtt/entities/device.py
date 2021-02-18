from paradox.data.model import DetectedPanel


class Device:
    def __init__(self, panel: DetectedPanel):
        self.panel = panel

    @property
    def serial_number(self):
        return self.panel.serial_number

    @property
    def model(self):
        return self.panel.model

    @property
    def firmware_version(self):
        return self.panel.firmware_version

    def serialize(self):
        return dict(
            manufacturer="Paradox",
            model=self.model,
            identifiers=[f"Paradox_{self.model}_{self.serial_number}"],
            name=self.model,
            sw_version=self.firmware_version,
        )