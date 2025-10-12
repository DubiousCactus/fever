import importlib
import os
import sys
from copy import copy, deepcopy
from types import ModuleType
from typing import Optional
from uuid import UUID

from rich.console import Console

from fever.ast_analysis import ASTAnalyzer, FeverModule
from fever.registry import Registry

from .call_tracker import CallTracker
from .dependency_tracker import DependencyTracker
from .utils import ConsoleInterface


def parse_verbosity() -> int:
    v = os.getenv("VERBOSITY", "").lower()
    if v in ("v", "1"):
        return 1
    elif v in ("vv", "2"):
        return 2
    elif v in ("vvv", "3"):
        return 3
    return 0


class Fever:
    def __init__(self, rich_console: Optional[Console] = None):
        self._verbosity = parse_verbosity()
        console = None if self._verbosity == 0 else (rich_console or Console())
        self._console_if = ConsoleInterface(console)
        self._ast_analyzer = ASTAnalyzer(
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None)
        )
        self.dependency_tracker = DependencyTracker(
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None)
        )
        self.call_tracker = CallTracker(
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None),
        )
        self.registry = Registry(
            self._ast_analyzer,
            self._console_if if self._verbosity >= 1 else ConsoleInterface(None),
        )

    def setup(self):
        """
        Start tracking user imports and function/method calls in real time. Any `import`
        statements coming before calling this function will not be tracked, and as a
        result, any function calls to functions/classes defined in those modules will not be
        tracked.
        """
        self.dependency_tracker.setup(show_skips=self._verbosity == 3)
        self.dependency_tracker.register_module_load_hook(self.registry)
        self.registry.register_add_hook(self.call_tracker)

    def cleanup(self):
        """
        Remove the import hook.
        """
        self.dependency_tracker.cleanup()

    def plot_dependency_graph(self):
        self.dependency_tracker.plot()

    def plot_call_graph(self):
        self.call_tracker.plot()

    def reload(self):
        """
        Reload all callables that have changed on disk by comparing their hash to the
        ones stored in the registry. All callables are automatically tracked based on
        imports and function calls that happen after calling `setup()`.
        """
        # INFO: Here's the plan:
        # For each tracked module:
        #   1. Reload from disk
        #   2. Run AST analysis
        #   3. Compare hashes of callables with those in the registry
        #   4. For each hash mismatch:
        #       a. Replace the underlying function
        #   5. For each new callable not found in registry, add it.

        # TODO: Now for part 2: reference propagation
        # 1. Topological sort of the call graph
        # 2. Every function that calls an updated function needs to be updated.
        # 3. Propagate backward? Maybe not.
        console = self._console_if if self._verbosity >= 1 else ConsoleInterface(None)
        for module_name in self.dependency_tracker.all_imports:
            console.print(f"Inspecting module '{module_name}'", style="purple on black")
            module_obj: ModuleType = sys.modules[module_name]
            cmp_fever_module: FeverModule = self._ast_analyzer.analyze(
                module_name, module_obj, getattr(module_obj, "__file__")
            )
            for cmp_func in cmp_fever_module.functions:
                # NOTE: Now cames the tricky part... How do we match our previously parsed
                # functions to the new parsed functions?
                # Option 1: by hash(name + scope + args)
                # Option 2: by other heuristics with a diff algorithm?
                # We'll use option 1 for now.
                if fever_callable := self.registry.find_function_by_name(
                    cmp_func.name, module_name
                ):
                    if fever_callable.hash != cmp_func.hash:
                        console.print(
                            f"Hash mismatch for function '{fever_callable.name}': hot reloading!",
                            style="green on black",
                        )
                        # WARN: cmp_func.obj is not valid! Because we get it from
                        # the original module, and it was not reloaded. So either we
                        # reload the module, but I don't like it because it replaces
                        # sys.modules and so reloads the entire thing, or we exec
                        # function code only!
                        # INFO: When executing code with the namespace of a module, it
                        # will replace the definition and references to that function in
                        # the module. That means we can update the function bytecode for
                        # the module namespace, but it won't propagate to other modules
                        # that have references to that function! We need to do this is
                        # step 2.

                        # Execute the function code in the module namespace (the
                        # globals() dict which contains the name of the function):
                        namespace = vars(module_obj)
                        exec(cmp_func.code, namespace)
                        # Delete the original function reference:
                        if hasattr(namespace[fever_callable.name], "__wrapped__"):
                            delattr(namespace[fever_callable.name], "__wrapped__")
                        # Wrap the recompiled function
                        setattr(
                            module_obj,
                            fever_callable.name,
                            self.call_tracker.track_calls(
                                namespace[fever_callable.name]
                            ),
                        )
                else:
                    self.registry.add(module_name, cmp_func)

    def rerun(self, entry_point: UUID):
        """
        Rerun the entire call graph from given entry point (callable UUID), but use
        cached results for every node in the graph that wasn't reloaded.
        """
        pass
