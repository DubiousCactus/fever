#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-05 13:06:07 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import builtins
import importlib
import inspect
import sys
from collections import defaultdict
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import List, Optional, Sequence, Tuple

import networkx as nx

from fever.hooks import ModuleLoadHook, NewImportHook

from .utils import ConsoleInterface, is_user_module


class DependencyTracker(MetaPathFinder, Loader):
    ignore_dirs = [".git", "__pycache__", ".vscode", ".venv", "fever"]

    def __init__(self, console: ConsoleInterface):
        self._console = console
        self._dep_graph = nx.DiGraph()
        self._show_skips = False
        self._new_import_hooks: List[NewImportHook] = []
        self._module_load_hooks: List[ModuleLoadHook] = []

    def setup(self, show_skips: bool = False):
        """
        Setup the import hook to keep track of user module imports.
        """
        self._original_importer = builtins.__import__
        self._console.print("Seting up the import hook", style="green on black")
        self._show_skips = show_skips
        builtins.__import__ = self._import
        sys.meta_path.insert(0, self)

    def cleanup(self):
        """
        Remove the import hook.
        """
        self._console.print("Cleaning up the import hook", style="green on black")
        builtins.__import__ = self._original_importer
        for finder in sys.meta_path.copy():
            if isinstance(finder, self.__class__):
                sys.meta_path.remove(finder)

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        return None  # Fallback to default machinery

    def exec_module(self, module) -> None:
        file_path = None
        try:
            file_path = module.__spec__.origin
        except:
            file_path = module.__file__
        assert file_path is not None
        with open(file_path) as f:
            self._console.print(
                f"Loading {module.__name__} from {module.__file__}...",
                style="black on white",
            )
            code_str = f.read()  # Read the source code
        exec(code_str, module.__dict__)  # Execute the code in the module's namespace
        # NOTE: Our main post-load hook is to run the AST analysis and decorate all
        # callables in the module; see call_tracker.py for that.
        for hook in self._module_load_hooks:
            hook.on_module_load(module.__name__, code_str)

    def find_spec(
        self, fullname: str, import_path: Optional[Sequence[str]] = None, target=None
    ) -> ModuleSpec | None:
        """
        For top-level imports, import_path will be None. Otherwise, this is a search for
        a subpackage or module and path will be the value of __path__ from the parent
        package. When passed in, target is a module object that the finder may use to
        make a more educated guess about what spec to return.
        """
        found_local, path = is_user_module(fullname, self.ignore_dirs)
        if not found_local:
            if self._show_skips:
                self._console.print(
                    f"Skipping non-user module '{fullname}'", style="red on black"
                )
            return None
        # INFO: Finding the caller module in the finder seems difficult, probably  due
        # to the import chains that call the finder and since we use the call frame to
        # find the caller. So we use the __import__ override hook for this, which is
        # also very useful for re-imports that don't call the finder/loader. That way we
        # can keep track of dependencies everywhere, which we couldn't do with just the
        # loader/finder.
        return importlib.util.spec_from_file_location(fullname, path, loader=self)

    def _import(
        self, name: str, globals=None, locals=None, fromlist=(), level=0
    ) -> ModuleType:
        module = self._original_importer(
            name, globals=globals, locals=locals, fromlist=fromlist, level=level
        )
        found_local, _ = is_user_module(name, self.ignore_dirs)
        if not found_local:
            return module

        caller_module = (
            (globals["__name__"], globals["__file__"])
            if globals is not None
            else (None, None)
        )
        found_local, _ = is_user_module(
            caller_module[0], self.ignore_dirs, caller_module[1]
        )
        if not found_local:
            if self._show_skips:
                self._console.print(
                    f"Skipping module '{name}' imported from non-user module"
                    + f"'{caller_module[0]}' defined in '{caller_module[1]}'",
                    style="red on black",
                )
            return module

        self._console.print(
            f"Importing '{name}' from module '{caller_module[0]}' defined in '{caller_module[1]}",
            style="yellow on black",
        )
        if caller_module[0] is not None:
            self._dep_graph.add_edge(caller_module[0], name)

        for hook in self._new_import_hooks:
            hook.on_new_import(name, module)

        return module

    def register_new_import_hook(self, hook: NewImportHook):
        self._new_import_hooks.append(hook)

    def register_module_load_hook(self, hook: ModuleLoadHook):
        self._module_load_hooks.append(hook)

    def get_dependencies(self, module_name: str) -> List[str]:
        """
        Return the list of all modules that directly or indirectly depend on
        module_name.
        """

        visited = defaultdict(lambda: False)

        def accumulate_pred(node: str) -> List[str]:
            if visited[node]:
                return []
            preds = list(self._dep_graph.predecessors(node))
            visited[node] = True
            for pred in preds.copy():
                preds += accumulate_pred(pred)
            return preds

        return accumulate_pred(module_name)

    def get_dependent_modules(self, module_name: str) -> List[Tuple[str, str, object]]:
        """
        Return a list of dependencies as tuples of module (name, path and object), given
        a query module name.
        """
        deps = []
        for dep_name in self.get_dependencies(module_name):
            module = sys.modules[dep_name]
            path = inspect.getfile(module)
            self._console.print(
                f"Found module '{module_name}''s path: <{path}>",
                style="green on black",
            )
            deps.append((dep_name, path, module))
        return deps

    def plot(self):
        from matplotlib import pyplot as plt

        plt.tight_layout()
        nx.draw_networkx(self._dep_graph, arrows=True)
        plt.show()

    @property
    def all_imports(self) -> List[str]:
        return self._dep_graph.nodes
