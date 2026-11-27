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
    "LIMITS",
    "REGEX_TIMEOUT",
]


@dataclass(frozen=True)
class Limits:
    """
    the resource limits applied to one rule evaluation.
    frozen, so a limit set cannot be mutated in the middle of a request
    (the same Limits object is shared by every evaluate() call in a scope)
    """
    max_recurse_depth: int  # in levels
    max_request_len: int    # in chars
    request_timeout: int    # in mseconds


MAX_DEPTH = 8
MAX_REQUEST_LEN = 1024
REGEX_TIMEOUT = 1000
REQUEST_TIMEOUT = 2000 + REGEX_TIMEOUT

# the default limit set. named kwargs (not positional) so that
# adding a field to Limits cannot silently shift the values
LIMITS = Limits(
    max_recurse_depth=MAX_DEPTH,
    max_request_len=MAX_REQUEST_LEN,
    request_timeout=REQUEST_TIMEOUT,
)


class LimitError(RuntimeError):
    """
    a resource limit was exceeded: recursion depth, request timeout,
    or (in the regex step) the regex timeout.
    carries the limit set that was in effect, so the caller can report it
    """

    def __init__(self, message: str, limits: Limits):
        """
        :param message: what exactly was exceeded, e.g. 'max recurse depth reached'
        :param limits: the limit set that was in effect when the violation happened
        """
        reason = f"{message}. limits were exceeded: {limits}"
        super().__init__(reason)
        self.message = message
        self.limits = limits


class Budget:
    """
    mutable counters for one evaluate() call.
    a Budget lives only inside a limit_scope() block;
    with_limits() reads it from the contextvar and charges every guarded call to it
    """

    def __init__(self, limits: Limits):
        """
        :param limits: the limit set this budget enforces
        """
        self.limits = limits
        self.depth = 0
        # the deadline is fixed at scope entry, not per call: the timeout
        # covers the whole evaluation, not a single function
        self.deadline = time.monotonic() + limits.request_timeout / 1000

    def enter(self):
        """
        charges one level of recursion to the budget and re-checks the limits.
        called by with_limits() right before the wrapped function runs
        :raises LimitError: if the recursion depth or the request deadline is exceeded
        """
        self.depth += 1
        if self.depth > self.limits.max_recurse_depth:
            raise LimitError("max recurse depth reached", self.limits)
        # monotonic, so wall-clock jumps cannot extend or shorten the deadline
        if time.monotonic() > self.deadline:
            raise LimitError("request timeout reached", self.limits)

    def leave(self):
        """
        releases one level of recursion. called by with_limits() in a finally block,
        so the depth is restored even if the wrapped function raises
        """
        self.depth -= 1


# the budget of the currently running evaluation, or None outside limit_scope().
# a contextvar (not a plain global) so that concurrent evaluations
# in different threads/tasks do not share counters
_BUDGET: ContextVar[Budget | None] = ContextVar("dsl_budget", default=None)


@contextmanager
def limit_scope(limits: Limits = LIMITS):
    """
    opens an evaluation scope with the given limits.
    every with_limits() call inside the block is charged to a fresh Budget,
    and the scope is closed (the budget is dropped) on exit,
    even if the block raises
    :param limits: the limit set to enforce in this scope
    """
    token = _BUDGET.set(Budget(limits))
    try:
        yield
    finally:
        _BUDGET.reset(token)


def with_limits(func):
    """
    marks a function as resource-dependent: every call is charged to the
    budget of the current limit_scope().
    outside a scope the function is called as is (no budget to charge),
    which keeps the resolver usable from unit tests without a scope
    :param func: the function to guard
    :return: a wrapper that enters/leaves the budget around the call
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
