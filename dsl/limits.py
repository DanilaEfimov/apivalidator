import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from dataclasses import dataclass


__all__ = [
    "Limits",
    "LimitError",
    "with_limits",
    "limit_scope",
]


class Budget:
    """
    mutable counters for one evaluate() call
    """
    def __init__(self, limits: Limits):
        self.limits = limits
        self.depth = 0
        self.deadline = time.monotonic() + limits.request_timeout / 1000

    def enter(self):
        self.depth += 1
        if self.depth > self.limits.max_recurse_depth:
            raise LimitError("max recurse depth reached", self.limits)
        if time.monotonic() > self.deadline:
            raise LimitError("request timeout reached", self.limits)

    def leave(self):
        self.depth -= 1


_BUDGET: ContextVar[Budget | None] = ContextVar("dsl_budget", default=None)


@dataclass(frozen=True)
class Limits:
    """

    """
    max_recurse_depth: int  # in levels
    max_request_len: int    # in chars
    request_timeout: int    # in mseconds


_MAX_DEPTH = 8
_MAX_REQUEST_LEN = 1024
_REGEX_TIMEOUT = 1000
_REQUEST_TIMEOUT = 2000 + _REGEX_TIMEOUT
LIMITS = Limits(max_recurse_depth=_MAX_DEPTH,
                max_request_len=_MAX_REQUEST_LEN,
                request_timeout=_REQUEST_TIMEOUT)


@contextmanager
def limit_scope(limits: Limits=LIMITS):
    token = _BUDGET.set(Budget(limits))
    try:
        yield
    finally:
        _BUDGET.reset(token)


def with_limits(func):
    """

    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        budget = _BUDGET.get()
        if budget is None:
            return func(*args, **kwargs)
        budget.enter()
        try:
            return func(*args, **kwargs)
        finally:
            budget.leave()
    return wrapper


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
