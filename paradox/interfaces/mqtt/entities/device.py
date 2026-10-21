from paradox.data.model import DetectedPanel


class Device:
    def __init__(self, panel: DetectedPanel):
        self.panel = panel

    @property
    def serial_number(self):
        return self.panel.serial_number

    @property
    def model(self):
        model = self.panel.model
        model = model.split("\x00", 1)[0]
        model = "".join(ch for ch in model if 32 <= ord(ch) < 127)
        return model.strip()

    @property
    def firmware_version(self):
        return self.panel.firmware_version

    def serialize(self):
        return dict(
            manufacturer="Paradox",
            model=self.model,
            identifiers=[f"Paradox_{self.serial_number}"],
            name=self.model,
            sw_version=self.firmware_version,
        )
