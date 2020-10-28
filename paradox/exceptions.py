import logging

logger = logging.getLogger("PAI").getChild(__name__)


class PAIException(Exception):
    pass


class StatusRequestException(PAIException):
    pass


class PAIConnectionError(PAIException):
    pass


class ConnectToIpModuleFailed(PAIConnectionError):
    pass


class ConnectToSiteFailed(PAIConnectionError):
    pass


class StunSessionRefreshFailed(PAIConnectionError):
    pass


# CRITICAL Exceptions below that will stop PAI.
class PAICriticalException(PAIException):
    pass


class AuthenticationFailed(PAICriticalException):
    pass

class CodeLockout(PAICriticalException):
    pass

class PanelNotDetected(PAICriticalException):
    pass


class SerialConnectionOpenFailed(PAICriticalException):
    pass


def async_loop_unhandled_exception_handler(loop, context):
    exception = context.get("exception")

    msg = context.get("exception", context["message"])

    task = context.get("task")
    if task:
        msg += ", task: %s" % task

    logger.exception(
        "Unhandled exception in async loop(%s): %s", loop, msg, exc_info=exception
    )
    loop.default_exception_handler(context)
