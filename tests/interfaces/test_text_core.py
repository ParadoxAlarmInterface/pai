import pytest

from paradox.interfaces.text.core import strip_command_prefix


@pytest.mark.parametrize(
    "body,prefix,expected",
    [
        ("partition all arm", "", "partition all arm"),
        ("Command partition all arm", "command", "partition all arm"),
        ("partition all arm", "command", None),
        ("commander partition all arm", "command", None),
    ],
)
def test_strip_command_prefix(body, prefix, expected):
    assert strip_command_prefix(body, prefix) == expected
