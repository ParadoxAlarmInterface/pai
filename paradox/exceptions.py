class PAIException(Exception):
    pass


class StatusRequestException(PAIException):
    pass


class AuthenticationFailed(PAIException):
    pass