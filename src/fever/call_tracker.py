#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import sys
import warnings
from functools import wraps
from types import FrameType
from typing import Callable, Optional

import networkx as nx

from fever.ast_analysis import FeverClass, FeverFunction, FeverModule, generic_function
from fever.registry import Registry
from fever.utils import ConsoleInterface, FeverWarning


def get_caller_obj(caller_frame: FrameType, caller_name: str) -> object | None:
    caller_obj = None
    if obj := caller_frame.f_locals.get("self", None):
        # Case 1: the caller is an object method
        caller_obj = obj
        try:
            caller_obj = getattr(
                caller_obj, caller_frame.f_code.co_name
            )  # Get the method object from the instance 'caller_obj'
            # FIXME: When I unwrap class methods, I loose their object context
            # in the __str__ or __repr__ methods.  Maybe I need a class wrapper
            # that intercepts __getattr__ and __setattr__ calls?
            caller_instance = getattr(caller_obj, "__self__", None)
            while hasattr(caller_obj, "__wrapped__"):
                caller_obj = getattr(caller_obj, "__wrapped__")
                setattr(caller_obj, "__self__", caller_instance)
        except Exception as e:
            warnings.warn(f"Exception thrown in get_caller_obj(): {e}", FeverWarning)
            caller_obj = None
    elif caller_frame.f_globals["__name__"] == "__main__":
        # Special case: called from the main module. We only want to get
        # information about the caller in this specific case.
        # Most likely the entry point
        caller_obj = sys.modules["__main__"]
    else:
        # Case 2: the caller is a module-level function
        namespace = caller_frame.f_globals["__name__"]
        try:
            caller_obj = getattr(sys.modules[namespace], caller_name)
            # FIXME: What's this unwrapping for again?
            while hasattr(caller_obj, "__wrapped__"):
                caller_obj = getattr(caller_obj, "__wrapped__")
        except Exception:
            caller_obj = None
    return caller_obj


class CallTracker:
    def __init__(self, registry: Registry, console: ConsoleInterface):
        self._console = console
        self._call_graph = nx.DiGraph()
        self._registry = registry

    def track_calls(
        self,
        func: FeverFunction,
        module: FeverModule,
        class_: Optional[FeverClass] = None,
    ) -> Callable:
        @wraps(func.obj)
        def fever_wrapper(*args, **kwargs):
            if func.obj is generic_function:
                raise RuntimeError(
                    "Wrapped function is the generic function! This should never happen."
                )
            nonlocal self
            # FIXME: Decorated methods such as @property don't work!
            # TODO: Handle edge cases (recursion, partials, wrappers, etc.)
            # WARN: Properly track the caller object! We want the parent if it was an
            # object, or if it was within another function. I made some attempt at this,
            # but I need to test it and make sure it handles all edge cases.
            # Anyway, this has become a bit of a mess because I'm not sure what I need
            # as my caller/callee objects. Function addresses? Class instances? Bounded
            # methods? I'll know more as I implement the rest, and I'll revisit this
            # part.
            caller_frame = sys._getframe(1)
            caller_name = caller_frame.f_code.co_qualname
            caller_obj = get_caller_obj(caller_frame, caller_name)
            callable_full_name = f"{class_.name}.{func.name}" if class_ else func.name
            self._console.print(
                f"Callable '{callable_full_name}' defined in '{module.name}' "
                + f"was called by '{caller_name}' at line {caller_frame.f_lineno}",
                style="green on black",
            )
            if caller_obj is None:
                warn = (
                    f"Could not resolve caller object for caller named '{caller_name}'"
                )
                self._console.print(warn, style="red on black")
                warnings.warn(warn, FeverWarning)
                caller_obj = module.obj  # Fallback to the module object
            else:
                self._call_graph.add_edge(caller_obj, func.obj)
                # TODO: Make the weight be statistics about the CPU time spent in the
                # call. We can track that in here, and we want the weight to be the
                # average time.
                if "weight" not in self._call_graph[caller_obj][func.obj]:
                    self._call_graph[caller_obj][func.obj]["weight"] = 1
                else:
                    self._call_graph[caller_obj][func.obj]["weight"] += 1
            registry = (
                self._registry._CLASS_METHOD_PTRS[module.name][class_.name]
                if class_
                else self._registry._FUNCTION_PTRS[module.name]
            )
            func_ptr = registry[func.name]
            # TODO: We should allow wrapped callables, but we should make sure that
            # the wrapper isn't this current one!
            assert not hasattr(func_ptr, "__wrapped__"), (
                "Callable wrapped recursively. This is not good."
            )
            return func_ptr(*args, **kwargs)

        return fever_wrapper

    def plot(self):
        from matplotlib import pyplot as plt

        plt.tight_layout()
        pos = nx.spring_layout(
            self._call_graph  # , seed=1
        )  # positions for all nodes - seed for reproducibility
        edge_labels = nx.get_edge_attributes(self._call_graph, "weight")
        nx.draw_networkx(self._call_graph, pos, arrows=True)
        nx.draw_networkx_edge_labels(self._call_graph, pos, edge_labels)
        plt.show()
