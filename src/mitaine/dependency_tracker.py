#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-05 13:06:07 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import abc
import builtins
import importlib
import inspect
import os
import sys
from collections import defaultdict
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from types import CodeType, ModuleType
from typing import List, Optional, Sequence, Tuple

import networkx as nx
from rich.console import Console


class NewImportHook(metaclass=abc.ABCMeta):
    def on_new_import(self, module_name: str, module: ModuleType) -> ModuleType:
        raise NotImplementedError


class ModuleLoadHook(metaclass=abc.ABCMeta):
    def on_module_load(self, module_name: str, code_str: str) -> Optional[CodeType]:
        raise NotImplementedError


class DependencyTracker(MetaPathFinder, Loader):
    ignore_dirs = [".git", "__pycache__", ".vscode", ".venv", "mitaine"]

    def __init__(self, console: Console):
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
        # sys.addaudithook(self._audit_hook)

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
        print("create_module(), name=", spec.name)
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
                f"Loading module from {module.__file__}...", style="black on white"
            )
            code_str = f.read()  # Read the source code
        code = None
        for hook in self._module_load_hooks:
            code = hook.on_module_load(module.__name__, code_str)
        code = code or code_str
        exec(code, module.__dict__)  # Execute the code in the module's namespace

    # def _audit_hook(self, event_name: str, args):
    #     if event_name == "import":
    #         print("'import' audit detected:", args[0])
    #     elif event_name == "exec":
    #         code_obj: CodeType = args[0]
    #         found = False
    #         try:
    #             source = inspect.getsource(code_obj)
    #             found = "module_a" in source
    #         except:
    #             pass
    #         print(
    #             "'exec' audit detected:",
    #             code_obj.co_name,
    #             code_obj.co_filename,
    #             code_obj.co_qualname,
    #             code_obj.co_nlocals,
    #             "FOUND module a import " if found else "not found module a improt",
    #             # inspect.getsource(code_obj),
    #         )

    def find_spec(
        self, fullname: str, import_path: Optional[Sequence[str]] = None, target=None
    ) -> ModuleSpec | None:
        """
        For top-level imports, import_path will be None. Otherwise, this is a search for
        a subpackage or module and path will be the value of __path__ from the parent
        package. When passed in, target is a module object that the finder may use to
        make a more educated guess about what spec to return.
        """
        found_local = False
        path = None
        for root, dirs, files in os.walk(os.path.curdir):
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
                    path = os.path.join(root, f)
                    break
            for d in dirs:
                if fullname == d:
                    path = os.path.join(root, d, "__init__.py")
                    found_local = True
                    break
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
        # caller_module = (None, None)
        # for frame in inspect.stack():
        #     if frame.code_context is None:
        #         continue
        #     for context in frame.code_context:
        #         if fullname in context and "import" in context:
        #             caller_module = (
        #                 inspect.getmodulename(frame.filename),
        #                 frame.filename,
        #             )
        # self._console.print(
        #     f"Importing '{fullname}' from module '{caller_module[0]}' defined in '{caller_module[1]}",
        #     style="green on black",
        # )
        # if caller_module[0] is not None:
        #     self._dep_graph.add_edge(caller_module[0], fullname)
        # self._dependencies[caller_module[0]].append((fullname, None))
        # return importlib.util.spec_from_loader(fullname, self, origin=path)
        return importlib.util.spec_from_file_location(fullname, path, loader=self)

    def _import(
        self, name: str, globals=None, locals=None, fromlist=(), level=0
    ) -> ModuleType:
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
