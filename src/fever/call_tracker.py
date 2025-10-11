#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import inspect
import sys
from functools import wraps
from typing import Callable, Optional

import networkx as nx

from .ast_analysis import FeverModule
from .hooks import RegistryAddHook
from .utils import ConsoleInterface


class CallTracker(RegistryAddHook):
    def __init__(self, console: ConsoleInterface):
        self._console = console
        self._call_graph = nx.DiGraph()

    def track_calls(
        self, func: Callable, class_obj: Optional[object] = None
    ) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal self
            # WARN: Properly track the caller object! We want the parent if it was an
            # object, or if it was within another function. I made some attempt at this,
            # but I need to test it and make sure it handles all edge cases.
            # Anyway, this has become a bit of a mess because I'm not sure what I need
            # as my caller/callee objects. Function addresses? Class instances? Bounded
            # methods? I'll know more as I implement the rest, and I'll revisit this
            # part.
            # TODO: Handle edge cases (recursion, partials, wrappers, etc.)
            caller_frame = sys._getframe(1)
            caller_obj, caller_instance, callee_instance = None, None, None
            if class_obj is not None and isinstance(args[0], class_obj):
                callee_instance = args[0]
            if obj := caller_frame.f_locals.get(
                "self", None
            ):  # This is an object method!
                caller_name = caller_frame.f_code.co_qualname
                caller_obj = obj
                try:
                    caller_obj = getattr(
                        caller_obj, caller_frame.f_code.co_name
                    )  # Get the method object from the instance 'caller_obj'
                    # FIXME: When I unwrap class methods, I loose their object context
                    # in the __str__ or __repr__ methods.  Maybe I need a class wrapper
                    # that intercepts __getattr__ and __setattr__ calls?
                    # NOTE: args[0] is the instance in the case where the callee is a
                    # method
                    caller_instance = getattr(caller_obj, "__self__", None)
                    while hasattr(caller_obj, "__wrapped__"):
                        caller_obj = getattr(caller_obj, "__wrapped__")
                        setattr(caller_obj, "__self__", caller_instance)
                except Exception as e:
                    print(e)
                    caller_obj = None
            elif (
                # "__name__" in caller_frame.f_locals
                # and caller_frame.f_locals["__name__"] == "__main__"
                caller_frame.f_globals["__name__"] == "__main__"
            ):
                # Most likely the entry point
                caller_name = caller_frame.f_locals["__name__"]
                caller_obj = sys.modules["__main__"]
            else:
                # Module-level functions
                caller_name = caller_frame.f_code.co_qualname
                namespace = caller_frame.f_globals["__name__"]
                try:
                    caller_obj = getattr(sys.modules[namespace], caller_name)
                    while hasattr(caller_obj, "__wrapped__"):
                        caller_obj = getattr(caller_obj, "__wrapped__")
                except:
                    caller_obj = None
            self._console.print(
                f"Callable '{func.__name__}' defined in '{inspect.getmodule(func).__name__}' "
                + f"was called by '{caller_name}' at line {caller_frame.f_lineno}",
                style="green on black",
            )
            if caller_obj is None:
                self._console.print(
                    f"Could not resolve caller object for caller named '{caller_name}'",
                    style="red on black",
                )
            else:
                key = caller_obj
                self._call_graph.add_edge(
                    key,
                    func,
                    caller_cls_instance=caller_instance,
                    callee_cls_instance=callee_instance,
                )
                if "weight" not in self._call_graph[key][func]:
                    self._call_graph[key][func]["weight"] = 1
                else:
                    self._call_graph[key][func]["weight"] += 1
            return func(*args, **kwargs)

        return wrapper

    def on_registry_add(self, module: FeverModule) -> None:
        for func in module.functions:
            assert isinstance(func.obj, object)
            setattr(module.obj, func.name, self.track_calls(func.obj))
        for class_, methods in module.methods.items():
            assert isinstance(class_, object)
            for method in methods:
                setattr(
                    class_,
                    method.name,
                    self.track_calls(method.obj, class_obj=class_),
                )
        for lambda_ in module.lambdas:
            # NOTE: We can't really track lambdas as they are anonymous and we have no
            # way to hook them unless we do some AST rewriting?. But I have been able to
            # track lambdas *reactively* at crash time, so I may adopt this strategy
            # later.
            pass

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
