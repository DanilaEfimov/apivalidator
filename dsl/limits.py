#TODO: config mutable class
#TODO: limit data class
#TODO: limit error
#TODO: counters, triggers, timeouts
#TODO: regex analizator

from dataclasses import dataclass


@dataclass
class Limits:
    """

    """
    max_recurse_depth: int  # in levels
    max_request_len: int    # in chars
    regex_timeout: int      # in mseconds
    request_timeout: int    # in mseconds


_MAX_DEPTH = 8
_MAX_REQUEST_LEN = 1024
_REGEX_TIMEOUT = 1000
_REQUEST_TIMEOUT = 2000 + _REGEX_TIMEOUT
LIMITS = Limits(_MAX_DEPTH, _MAX_REQUEST_LEN, _REGEX_TIMEOUT, _REQUEST_TIMEOUT)


class LimitError(RuntimeError):
    """

    """

    def __init__(self, message: str, limits: Limits):
        """
        :param message:
        :param limits:
        """
        reason = f"{message}. limits were exused: {limits}"
        super().__init__(reason)
        self.message = message
        self.limits = limits
