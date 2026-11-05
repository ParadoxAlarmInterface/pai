import pytest

from paradox.interfaces.text.core import strip_command_prefix


@pytest.mark.parametrize(
    "body,prefix,expected",
    [
        ("partition all arm", "", "partition all arm"),
        ("  partition all arm ", "", "partition all arm"),
        ("partition  all\tarm", "", "partition all arm"),
        (None, "", ""),
        ("command partition all arm", "command", "partition all arm"),
        ("Command  partition all arm", "command", "partition all arm"),
        ("COMMAND\tpartition all arm", "command", "partition all arm"),
        ("command", "command", ""),
        ("partition all arm", "command", None),
        ("commander partition all arm", "command", None),
        ("Alarm triggered in zone 3", "command", None),
        (None, "command", None),
        ("", "command", None),
        ("partition all arm", "   ", "partition all arm"),
        ("command partition all arm", " Command ", "partition all arm"),
        ("pai  CMD partition all arm", "pai cmd", "partition all arm"),
        ("pai partition all arm", "pai cmd", None),
        ("pai", "pai cmd", None),
    ],
)
def test_strip_command_prefix(body, prefix, expected):
    assert strip_command_prefix(body, prefix) == expected
