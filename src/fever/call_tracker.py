#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import enum
import sys
import timeit
import warnings
from functools import wraps
from types import FrameType
from typing import Callable, Optional

import networkx as nx

from fever.ast_analysis import FeverClass, FeverFunction, FeverModule, generic_function
from fever.cache import Cache
from fever.registry import Registry
from fever.types import FeverParameters, FeverWarning
from fever.utils import ConsoleInterface


class TrackingMode(enum.Enum):
    """
    KV_POINTERS: Track calls using caller and callee object pointers as keys and values.
    This results in multiple copies of the same function in the call graph, if that
    function is recompiled. This is desired if we want to keep track of specific
    function objects.
    KV_NAMES: Track calls using caller and callee names as keys and values. This
    simplifies the graph to the original function names, but we lose information about
    which version of the function was called or is calling.
    """

    KV_POINTERS = enum.auto()
    KV_NAMES = enum.auto()


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
    def __init__(
        self, registry: Registry, tracking_mode: TrackingMode, console: ConsoleInterface
    ):
        self._console = console
        self._call_graph = nx.MultiDiGraph()
        self._registry = registry
        self._tracking_mode = tracking_mode
        self._cache = Cache()

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
            callable_full_name = f"{class_.name}.{func.name}" if class_ else func.name
            self._console.print(
                f"Callable '{callable_full_name}' defined in '{module.name}' "
                + f"was called by '{caller_name}' at line {caller_frame.f_lineno}",
                style="green on black",
            )
            params = None
            k, v = caller_name, func.name
            if self._tracking_mode == TrackingMode.KV_POINTERS:
                caller_obj = get_caller_obj(caller_frame, caller_name)
                if caller_obj is None:
                    warn = f"Could not resolve caller object for caller named '{caller_name}'"
                    self._console.print(warn, style="red on black")
                    warnings.warn(warn, FeverWarning)
                    caller_obj = module.obj  # Fallback to the module object
                k, v = caller_obj, func.obj

            self._call_graph.add_nodes_from([k, v])
            params = FeverParameters(args, kwargs)
            self._call_graph.add_edge(k, v, key=params.hash, params=params)
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
            if cached_result := self._cache.get(func_ptr, params):
                self._console.print(
                    f"Cache hit for callable '{callable_full_name}' with params: {params}",
                    style="yellow on black",
                )
                return cached_result
            start = timeit.default_timer()
            result = func_ptr(*args, **kwargs)
            end = timeit.default_timer()
            # WARN: The caller object will change as the caller function is recompiled!
            # Because we look for it in the call stack. This is normal, but we might
            # want the caller to be the function name instead of the pointer, so we
            # parameterize the strategy with self._tracking_mode.
            edge_data = self._call_graph.edges[k, v, params.hash]
            if "weight" not in edge_data:
                edge_data["cum_time"] = 0.0
                edge_data["calls"] = 0
            edge_data["cum_time"] += end - start
            edge_data["calls"] += 1
            edge_data["weight"] = edge_data["cum_time"] / edge_data["calls"]
            self._cache.set(func_ptr, params, edge_data, result)
            return result

        return fever_wrapper

    def plot(self):
        import itertools as it

        import matplotlib.pyplot as plt

        G = self._call_graph
        ax = plt.gca()
        # Works with arc3 and angle3 connectionstyles
        # connectionstyle = [f"arc3,rad={r}" for r in it.accumulate([0.15] * 4)]
        connectionstyle = [f"angle3,angleA={r}" for r in it.accumulate([30] * 4)]

        # pos = nx.spring_layout(
        #     self._call_graph  # , seed=1
        # )  # positions for all nodes - seed for reproducibility
        # pos = nx.random_layout(G)
        pos = nx.shell_layout(G)
        nx.draw_networkx_nodes(G, pos, ax=ax)
        nx.draw_networkx_labels(G, pos, font_size=10, ax=ax)
        nx.draw_networkx_edges(
            G, pos, edge_color="grey", connectionstyle=connectionstyle, ax=ax
        )

        labels = {
            tuple(edge): attrs["params"]
            for *edge, attrs in G.edges(keys=True, data=True)
        }
        nx.draw_networkx_edge_labels(
            G,
            pos,
            labels,
            connectionstyle=connectionstyle,
            label_pos=0.3,
            font_color="blue",
            bbox={"alpha": 0},
            ax=ax,
        )
        plt.tight_layout()
        plt.show()
