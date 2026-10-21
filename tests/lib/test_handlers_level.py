import logging

from paradox.lib.handlers import HandlerRegistry


async def test_no_handler_logs_warning_not_error(caplog):
    registry = HandlerRegistry()

    with caplog.at_level(logging.WARNING, logger="PAI"):
        await registry.handle("some unhandled message")

    records = [r for r in caplog.records if "No handler for message" in r.message]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
