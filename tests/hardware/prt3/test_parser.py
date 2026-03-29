"""
Smoke tests for paradox.hardware.prt3.parser.

Verifies that the module imports cleanly and that all expected dataclasses
and the parse_line() entry point are present.  Parser logic tests will be
added in Phase 2 once parse_line() is implemented.
"""

import pytest

from paradox.hardware.prt3.parser import (
    PRT3CommStatus,
    PRT3CommandEcho,
    PRT3AreaStatus,
    PRT3ZoneStatus,
    PRT3LabelReply,
    PRT3SystemEvent,
    parse_line,
)


def test_dataclasses_importable():
    """All PRT3 message dataclasses must be importable."""
    assert PRT3CommStatus is not None
    assert PRT3CommandEcho is not None
    assert PRT3AreaStatus is not None
    assert PRT3ZoneStatus is not None
    assert PRT3LabelReply is not None
    assert PRT3SystemEvent is not None


def test_parse_line_raises_not_implemented():
    """parse_line() must raise NotImplementedError until Phase 2."""
    with pytest.raises(NotImplementedError):
        parse_line("COMM&ok")
