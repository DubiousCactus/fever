import importlib
import os
import sys
from copy import copy, deepcopy
from types import ModuleType
from typing import Optional
from uuid import UUID

from rich.console import Console

import fever.registry as registry
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
        self.registry = Registry(
            self._ast_analyzer,
            self._console_if if self._verbosity >= 1 else ConsoleInterface(None),
        )
        self.call_tracker = CallTracker(
            self.registry,
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None),
        )

    def setup(self):
        """
        Start tracking user imports and function/method calls in real time. Any `import`
        statements coming before calling this function will not be tracked, and as a
        result, any function calls to functions/classes defined in those modules will not be
        tracked.


        Fever tracks imports and wraps all callables to insert a registry hook, where
        the actual code will be stored and updated. It does so in the following steps:
        1. Insert an import hook which detects user modules and ignores others.
        2. On first import, load the module from disk via exec(); this compiles it to byte code.
        3. Retrieve the compiled module from sys.modules.
        4. Analyze its AST to find all callables.
        4. Wrap each callable in a decorator and save the underlying pointer to a registry.
        5. Replace the module's function pointer with our wrapped function pointer. Any
        subsequent call to the callable will be redirected to the proxy callable which
        will pull the bytecode from the registry.
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

        For each tracked module:
          1. Reload from disk.
          2. Run AST analysis to extract callables (functions and methods).
          3. Compare hashes of callables with those in the registry.
          4. For each hash mismatch:
              a. Replace the function bytecode in the registry.
          5. For each new callable not found in registry, add it.
        """
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
                        # sys.modules and reloads the entire thing, or we exec
                        # function code only!
                        # INFO: Compile the new function code into the registry
                        # namespace, where it should already be defined since the
                        # original function is placed there by our call wrapper. For
                        # subsequent calls to the function, from anywhere, the new code
                        # will be used automatically. It's beautiful, there is no need
                        # to refresh imports or references.
                        module_namespace = vars(module_obj)
                        # FIXME: This assert is broken. We need the hierarchy of the
                        # function definition. It will only work for level 0 (module).
                        # assert hasattr(
                        #     module_namespace[fever_callable.name], "__wrapped__"
                        # ), (
                        #     f"Function '{fever_callable.name}' was never wrapped "
                        #     + "and so is not in the registry. "
                        #     + "This should not happen, please make a bug report."
                        # )
                        registry_namespace = self.registry._FUNCTION_DEFS[module_name]
                        exec(cmp_func.code, registry_namespace)
                else:
                    self.registry.add_function(module_name, cmp_func)

            for cmp_class, cmp_methods in cmp_fever_module.methods.items():
                for cmp_method in cmp_methods:
                    if fever_callable := self.registry.find_method_by_name(
                        cmp_method.name, cmp_class.name, module_name
                    ):
                        if fever_callable.hash != cmp_method.hash:
                            console.print(
                                f"Hash mismatch for method '{fever_callable.name}': hot reloading!",
                                style="green on black",
                            )
                            # FIXME: This assert is broken. We need the hierarchy of the
                            # method definition. It will only work for level 1 (class in
                            # module).
                            # module_namespace = vars(module_obj)
                            # assert hasattr(
                            #     getattr(
                            #         module_namespace[cmp_class.name],
                            #         fever_callable.name,
                            #     ),
                            #     "__wrapped__",
                            # ), (
                            #     f"Function '{fever_callable.name}' was never wrapped "
                            #     + "and so is not in the registry. "
                            #     + "This should not happen, please make a bug report."
                            # )
                            registry_namespace = self.registry._CLASS_METHOD_DEFS[
                                module_name
                            ][cmp_class.name]
                            exec(cmp_method.code, registry_namespace)
                    else:
                        self.registry.add_method(module_name, cmp_class, cmp_method)

    def rerun(self, entry_point: UUID):
        """
        Rerun the entire call graph from given entry point (callable UUID), but use
        cached results for every node in the graph that wasn't reloaded.
        """
        pass
