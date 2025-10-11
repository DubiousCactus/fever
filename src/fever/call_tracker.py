#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import inspect
import sys
from collections import defaultdict
from functools import wraps
from typing import Callable, Dict

import networkx as nx
from rich.console import Console

from .ast_analysis import ASTAnalyzer, FeverModule
from .dependency_tracker import DependencyTracker, ModuleLoadHook


class CallTracker(ModuleLoadHook):
    def __init__(self, console: Console):
        self._console = console
        self._call_graph = nx.DiGraph()
        self._ast_analyzer = ASTAnalyzer(console)
        self._callables: Dict[str, FeverModule] = {}

    def track(self, dependency_tracker: DependencyTracker):
        """
        Begin tracking function calls and building the runtime call graph.
        """
        dependency_tracker.register_module_load_hook(self)

    def track_calls(self, func: Callable):
        callers = defaultdict(int)

        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal callers
            nonlocal self
            # WARN: Properly track the caller object! We want the parent if it was an
            # object, or if it was within another function. I made some attempt at this,
            # but I need to test it and make sure it handles all edge cases.
            # TODO: Handle edge cases (recursion, partials, wrappers, etc.)
            caller_frame = inspect.currentframe().f_back
            caller_obj = None
            if obj := caller_frame.f_locals.get("self"):
                # This is an object method!
                caller_name = caller_frame.f_code.co_qualname
                caller_obj = obj
            else:
                caller_name = caller_frame.f_code.co_qualname
                namespace = caller_frame.f_globals["__name__"]
                try:
                    caller_obj = getattr(sys.modules[namespace], caller_name)
                    while hasattr(caller_obj, "__wrapped__"):
                        caller_obj = getattr(caller_obj, "__wrapped__")
                except:
                    caller_obj = None
            callers[caller_name] += 1
            self._console.print(
                f"Callable '{func.__name__}' defined in '{inspect.getmodule(func).__name__}' "
                + f"was called by '{caller_name}' at line {caller_frame.f_lineno} "
                + f"for the {callers[caller_name]}th time",
                style="green on black",
            )
            key = caller_obj or caller_name
            self._call_graph.add_edge(key, func)
            if "weight" not in self._call_graph[key][func]:
                self._call_graph[key][func]["weight"] = 1
            else:
                self._call_graph[key][func]["weight"] += 1
            func(*args, **kwargs)

        return wrapper

    def on_module_load(self, module_name: str, code_str: str) -> None:
        if module_name == "mitaine":
            # TODO: Find a better way? But in fact, our import hook already excludes
            # non-user code, so this problem arises only when testing mitaine from
            # mitaine's project!
            return
        self._console.print(
            f"Analyzing AST for module '{module_name}'", style="blue on black"
        )
        # NOTE: This all feels a bit redundant, but let's see. What we do is:
        # 1. Load the module from disk via exec(). This compiles it to byte code.
        # 2. Retrieve the compiled module from sys.modules
        # 3. Analyze its AST to find all callables and their memory addresses.
        # 4. Wrap each callable in a decorator. This gives us a new function pointer.
        # 5. Replace the module's function pointer with our wrapped function pointer.
        # ~6. Reload the modified module and replace it in sys.modules.
        # So it seems that only step 6 is a bit redundant after all. Can we directly
        # hook the pointer in the module without reloading it?~
        # EDIT: I've successfully removed step 6. All in all, it's not redundant as we
        # directly modify memory addresses :) Neat!
        module = sys.modules[module_name]
        self._callables[module_name] = self._ast_analyzer.analyze(
            module_name, module, show_ast=False
        )
        #
        # # TODO: For each callable in the returned FeverModule, wrap it in the tracker
        # # decorator.
        # # Let's start with module level functions!
        for func in self._callables[module_name].functions:
            assert isinstance(func.obj, object)
            setattr(module, func.name, self.track_calls(func.obj))

    def plot_call_graph(self):
        from matplotlib import pyplot as plt

        plt.tight_layout()
        pos = nx.spring_layout(
            self._call_graph, seed=2
        )  # positions for all nodes - seed for reproducibility
        edge_labels = nx.get_edge_attributes(self._call_graph, "weight")
        nx.draw_networkx(self._call_graph, pos, arrows=True)
        nx.draw_networkx_edge_labels(self._call_graph, pos, edge_labels)
        plt.show()
