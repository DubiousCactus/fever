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
from importlib.abc import Loader, MetaPathFinder, SourceLoader
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Dict, List, Tuple

import networkx as nx

from fever.hooks import ModuleLoadHook, NewImportHook

from .utils import ConsoleInterface


class TestLoader(Loader):
    def __init__(self, name: str, path: str):
        print(f"TestLoader: Loading module {name} from {path}")


class MyLoader(SourceLoader):
    def __init__(self, fullname, path):
        print(f"SourceLoader: Loading module {fullname} from {path}")
        self.fullname = fullname
        self.path = path

    def get_filename(self, fullname):
        return self.path

    def get_data(self, filename):
        """exec_module is already defined for us, we just have to provide a way
        of getting the source code of the module"""
        with open(filename) as f:
            data = f.read()
        # do something with data ...
        # eg. ignore it... return "print('hello world')"
        return data


class DependencyTracker(MetaPathFinder, Loader):
    ignore_dirs = [".git", "__pycache__", ".vscode", ".venv", "fever"]

    def __init__(self, console: ConsoleInterface):
        self._console = console
        self._dep_graph = nx.DiGraph()
        self._show_skips = False
        self._new_import_hooks: List[NewImportHook] = []
        self._module_load_hooks: List[ModuleLoadHook] = []
        self._user_modules: Dict[str, str] = {}

    def setup(self, show_skips: bool = False):
        """
        Setup the import hook to keep track of user module imports.
        """
        self._original_importer = builtins.__import__
        self._console.print("Seting up the import hook", style="green on black")
        self._show_skips = show_skips
        # self._user_modules = self._scan_user_modules()
        caller_code_obj = sys._getframe(2).f_code  # 2 bc 1 is Fever.__init__
        self._user_modules[inspect.getmodule(caller_code_obj).__name__] = (
            inspect.getfile(caller_code_obj)
        )
        self.curdir = os.getcwd()
        self._console.print(
            f"User modules: {', '.join(self._user_modules.keys())}",
            style="blue on black",
        )
        # print(self._user_modules)
        # NOTE: For now we don't need this hook bc we don't need the full dependency graph I think
        builtins.__import__ = self._import
        sys.meta_path.insert(0, self)
        # sys.path_hooks.insert(0, FileFinder.path_hook((self.test_loader, ["*.py"])))
        # sys.path_hooks.insert(0, FileFinder.path_hook((TestLoader, ["*.py"])))
        # clear any loaders that might already be in use by the FileFinder
        # sys.path_importer_cache.clear()
        # importlib.invalidate_caches()

    def cleanup(self):
        """
        Remove the import hook.
        """
        self._console.print("Cleaning up the import hook", style="green on black")
        builtins.__import__ = self._original_importer
        for finder in sys.meta_path.copy():
            if isinstance(finder, self.__class__):
                sys.meta_path.remove(finder)

    def test_loader(self, name: str, path: str):
        print(f"Loading module {name} from {path}")

    def _scan_user_modules(self) -> Dict[str, str]:
        user_modules = {}
        base_dir = os.path.curdir
        for root, dirs, files in os.walk(base_dir):
            for ignore_dir in self.ignore_dirs:
                dirs[:] = [d for d in dirs if d != ignore_dir]
            for f in files:
                if not f.endswith(".py"):
                    continue
                module_name = f.split(".")[0]
                user_modules[module_name] = os.path.join(root, f)
            for d in dirs:
                if not os.path.isfile(os.path.join(root, d, "__init__.py")):
                    continue
                user_modules[d] = os.path.join(root, d, "__init__.py")
        return user_modules

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        return None  # Fallback to default machinery

    def exec_module(self, module) -> None:
        file_path = None
        if module_spec := getattr(module, "__spec__", None):
            # print(module_spec)
            file_path = module_spec.origin
            self._user_modules[module_spec.name] = file_path
            assert file_path is not None
            with open(file_path) as f:
                self._console.print(
                    f"Loading {module_spec.name} from {file_path}...",
                    style="black on white",
                )
                code_str = f.read()  # Read the source code
                self._console.print("Done!", style="green on black")
            self._console.print("\t - Executing module...", style="black on white")
            exec(
                code_str, module.__dict__
            )  # Execute the code in the module's namespace
            self._console.print("\t - Done!", style="green on black")
            # NOTE: Our main post-load hook is to run the AST analysis and decorate all
            # callables in the module; see call_tracker.py for that.
            for hook in self._module_load_hooks:
                hook.on_module_load(module.__name__, code_str)

    def find_spec(self, fullname: str, path: str, target=None) -> ModuleSpec | None:
        """
        For top-level imports, path will be None. Otherwise, this is a search for
        a subpackage or module and path will be the value of __path__ from the parent
        package. When passed in, target is a module object that the finder may use to
        make a more educated guess about what spec to return.
        """
        if path is None or path == "" or path == []:
            path = [self.curdir]  # top level import --
        if "." in fullname:
            *parents, name = fullname.split(".")
        else:
            name = fullname
        if os.path.commonpath([path[0], str(self.curdir)]) != self.curdir:
            return None
        for ignore_dir in self.ignore_dirs:
            ignore_dir = os.path.join(self.curdir, ignore_dir)
            if os.path.commonpath([path[0], ignore_dir]) == ignore_dir:
                if self._show_skips:
                    self._console.print(
                        f"Skipping ignored directory '{ignore_dir}' in path '{path[0]}'",
                        style="red on black",
                    )
                return None
        for entry in path:
            if os.path.isdir(os.path.join(entry, name)):
                # this module has children modules
                file_path = os.path.join(entry, name, "__init__.py")
                submodule_locations = [os.path.join(entry, name)]
            else:
                file_path = os.path.join(entry, name + ".py")
                submodule_locations = None
            if not os.path.exists(file_path):
                continue

            print(
                f"Loading module {fullname} (path={path}, target={target}) stored in "
            )

            # INFO: Finding the caller module in the finder seems difficult, probably  due
            # to the import chains that call the finder and since we use the call frame to
            # find the caller. So we use the __import__ override hook for this, which is
            # also very useful for re-imports that don't call the finder/loader. That way we
            # can keep track of dependencies everywhere, which we couldn't do with just the
            # loader/finder.
            return importlib.util.spec_from_file_location(
                fullname,
                file_path,
                loader=self,
                submodule_search_locations=submodule_locations,
            )
        return None

    def invalidate_caches(self):
        self._user_modules = {}

    def _import(
        self, name: str, globals=None, locals=None, fromlist=(), level=0
    ) -> ModuleType:
        module = self._original_importer(
            name, globals=globals, locals=locals, fromlist=fromlist, level=level
        )
        path = self._user_modules.get(name, None)
        if path is None:
            return module

        caller_module = (
            (globals["__name__"], globals["__file__"])
            if globals is not None
            else (None, None)
        )
        path = (
            self._user_modules.get(caller_module[0], None) if caller_module[0] else None
        )
        if path is None:
            if self._show_skips:
                self._console.print(
                    f"Skipping module '{name}' imported from non-user module"
                    + f"'{caller_module[0]}' defined in '{caller_module[1]}'",
                    style="red on black",
                )
            return module

        composite_name = name if len(fromlist) == 0 else name + "." + ".".join(fromlist)
        self._console.print(
            f"Importing '{composite_name}' "
            + f"from module '{caller_module[0]}' defined in '{caller_module[1]}",
            style="yellow on black",
        )
        if caller_module[0] is not None:
            self._dep_graph.add_edge(caller_module[0], composite_name)

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
