# INFO: Here's the plan:
# 1. Run AST analysis on the callable (or owner module?).
# 2. For every callable found in the analysis, monkey-patch the original code so that we
# wrap it.
# 3. For every call, pass the globals and locals so that we know about the caller.
import inspect
from collections import defaultdict
from functools import wraps
from typing import Callable

from .dependency_tracker import DependencyTracker


def track_calls(func: Callable):
    callers = defaultdict(int)

    @wraps(func)
    def wrapper(*args, **kwargs):
        caller_frame = inspect.currentframe().f_back
        # TODO: Handle edge cases (recursion, partials, wrappers, etc.)
        caller_name = caller_frame.f_globals["__name__"]
        callers[caller_name] += 1
        print(
            f"Callable '{func.__name__}' defined in '{inspect.getmodule(func).__name__}' was called by '{caller_name}' at line {caller_frame.f_lineno} for the {callers[caller_name]}th time"
        )
        func(*args, **kwargs)

    return wrapper
