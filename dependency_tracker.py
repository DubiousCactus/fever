#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-05 13:06:07 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import importlib
import inspect
import os
import sys
from importlib.abc import MetaPathFinder
from typing import List, Optional, Sequence, Tuple

import networkx as nx
from rich.console import Console


class DependencyTracker(MetaPathFinder):
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
            try:
                for ignore_dir in self.ignore_dirs:
                    dirs.remove(ignore_dir)
            except Exception:
                pass

            for f in files:
                if f.startswith(fullname):
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

    def get_dependencies(self, module_name: str) -> List[Tuple[str, str, object]]:
        """
        Return a list of dependencies as tuples of module (name, path and object), given
        a query module name.
        """
        deps = []
        for dep_name in self._dep_graph[module_name]:
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
