from ..panel import Panel_EVOBase

class Panel_EVO48(Panel_EVOBase):
    mem_map = dict(
        elements=dict(
            zone=dict(
                label_offset=0, addresses=[
                    range(0x00430, 0x00730, 0x10),  # EVO48
                ]),
            output=dict(
                label_offset=0, addresses=[range(0x07082, 0x7482, 0x20)], template=dict(
                    on=False,
                    pulse=False)
                ),
            partition=dict(
                label_offset=0, addresses=[
                    range(0x03a6b, 0x03c17, 0x6b),  # EVO48
                ]),
            user=dict(
                label_offset=0, addresses=[range(0x03e47, 0x04447, 0x10)]),
            bus=dict(  # modules
                label_offset=0, addresses=[
                    range(0x04e47, 0x05637, 0x10),  # EVO48
                ]),
            door=dict(
                label_offset=0, addresses=[range(0x0345c, 0x365c, 0x10)]),
        )
    )