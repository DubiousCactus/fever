#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-05 13:06:07 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import builtins
import importlib
import inspect
import os
import sys
from collections import defaultdict
from importlib.abc import MetaPathFinder
from typing import List, Optional, Sequence, Tuple

import networkx as nx
from rich.console import Console


class DependencyTrackerV1(MetaPathFinder):
    ignore_dirs = [".git", "__pycache__", ".vscode"]

    def __init__(self, console: Console):
        self._console = console
        self._dep_graph = nx.DiGraph()
        self._show_skips = False

    def setup(self, show_skips: bool = False):
        """
        Setup the import hook to keep track of user module imports.
        """
        self.cleanup()
        self._console.print("Seting up the import hook", style="green on black")
        self._show_skips = show_skips
        sys.meta_path.insert(0, self)

    def cleanup(self):
        """
        Remove the import hook.
        """
        self._console.print("Cleaning up the import hook", style="green on black")
        for finder in sys.meta_path.copy():
            if isinstance(finder, self.__class__):
                sys.meta_path.remove(finder)

    def find_spec(
        self, fullname: str, import_path: Optional[Sequence[str]] = None, target=None
    ):
        """
        For top-level imports, import_path will be None. Otherwise, this is a search for
        a subpackage or module and path will be the value of __path__ from the parent
        package. When passed in, target is a module object that the finder may use to
        make a more educated guess about what spec to return.
        """
        found_local = False
        for _, dirs, files in os.walk(os.path.curdir):
            if found_local:
                break
            try:
                for ignore_dir in self.ignore_dirs:
                    dirs.remove(ignore_dir)
            except Exception:
                pass

            for f in files:
                if f.split(".")[0] == fullname:
                    found_local = True
                    break
            for d in dirs:
                if fullname == d:
                    found_local = True
                    break
        if not found_local:
            if self._show_skips:
                self._console.print(
                    f"Skipping non-user module '{fullname}'", style="red on black"
                )
            return None
        caller_module = (None, None)
        for frame in inspect.stack():
            if frame.code_context is None:
                continue
            for context in frame.code_context:
                if fullname in context and "import" in context:
                    caller_module = (
                        inspect.getmodulename(frame.filename),
                        frame.filename,
                    )
        self._console.print(
            f"Importing '{fullname}' from module '{caller_module[0]}' defined in '{caller_module[1]}",
            style="green on black",
        )
        if caller_module[0] is not None:
            self._dep_graph.add_edge(caller_module[0], fullname)
            # self._dependencies[caller_module[0]].append((fullname, None))
        return None  # Fallback to other finders (default behaviour of import())

    def get_dependencies(self, module_name: str) -> List[str]:
        """
        Return the list of all modules that directly or indirectly depend on
        module_name.
        """

        def accumulate_pred(node: str) -> List[str]:
            preds = list(self._dep_graph.predecessors(node))
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
            module = importlib.import_module(dep_name)
            path = inspect.getfile(module)
            self._console.print(
                f"Found module '{module_name}''s path: <{path}>",
                style="green on black",
            )
            deps.append((dep_name, path, module))
        return deps

    def plot_dependency_graph(self):
        from matplotlib import pyplot as plt

        plt.tight_layout()
        nx.draw_networkx(self._dep_graph, arrows=True)
        plt.show()


class DependencyTrackerV2:
    ignore_dirs = [".git", "__pycache__", ".vscode", ".venv"]

    def __init__(self, console: Console):
        self._console = console
        self._dep_graph = nx.DiGraph()
        self._show_skips = False

    def setup(self, show_skips: bool = False):
        """
        Setup the import hook to keep track of user module imports.
        """
        self._original_importer = builtins.__import__
        self._console.print("Seting up the import hook", style="green on black")
        self._show_skips = show_skips
        builtins.__import__ = self._import

    def cleanup(self):
        """
        Remove the import hook.
        """
        self._console.print("Cleaning up the import hook", style="green on black")
        builtins.__import__ = self._original_importer

    def _import(self, name: str, globals=None, locals=None, fromlist=(), level=0):
        module = self._original_importer(
            name, globals=globals, locals=locals, fromlist=fromlist, level=level
        )
        if name == "":
            return module
        found_local = False
        for _, dirs, files in os.walk(os.path.curdir):
            if found_local:
                break
            try:
                for ignore_dir in self.ignore_dirs:
                    dirs.remove(ignore_dir)
            except Exception:
                pass

            for f in files:
                if f.split(".")[0] == name:
                    found_local = True
                    break
            for d in dirs:
                if name == d:
                    found_local = True
                    break
        if not found_local:
            if self._show_skips:
                self._console.print(
                    f"Skipping non-user module '{name}'", style="red on black"
                )
            return module
        caller_module = (
            (globals["__name__"], globals["__file__"])
            if globals is not None
            else (None, None)
        )
        self._console.print(
            f"Importing '{name}' from module '{caller_module[0]}' defined in '{caller_module[1]}",
            style="green on black",
        )
        if caller_module[0] is not None:
            self._dep_graph.add_edge(caller_module[0], name)

        return module

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
            module = importlib.import_module(dep_name)
            path = inspect.getfile(module)
            self._console.print(
                f"Found module '{module_name}''s path: <{path}>",
                style="green on black",
            )
            deps.append((dep_name, path, module))
        return deps

    def plot_dependency_graph(self):
        from matplotlib import pyplot as plt

        plt.tight_layout()
        nx.draw_networkx(self._dep_graph, arrows=True)
        plt.show()
