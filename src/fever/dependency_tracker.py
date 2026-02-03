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
import warnings
from collections import defaultdict
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from types import FrameType, ModuleType
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import networkx as nx

from .types import FeverWarning
from .utils import ConsoleInterface


def find_module_path(root: str, name: str) -> Tuple[str | None, List[str] | None]:
    file_path, submodule_locations = None, None
    if (module_init := os.path.join(root, name, "__init__.py")) and os.path.isfile(
        module_init
    ):
        # this module has children modules
        file_path = module_init
        submodule_locations = [os.path.dirname(module_init)]
    elif (module_path := os.path.join(root, f"{name}.py")) and os.path.isfile(
        module_path
    ):
        file_path = module_path
    return file_path, submodule_locations


class DependencyTracker(MetaPathFinder, Loader):
    ignore_dirs = [".git", "__pycache__", ".vscode", ".venv", "fever"]

    def __init__(self, console: ConsoleInterface, on_module_load_callback: Callable):
        self._absolute_ignore_dirs = [
            os.path.join(os.getcwd(), d) for d in self.ignore_dirs
        ]
        self._console = console
        self._dep_graph = nx.DiGraph()
        self._show_skips = False
        self._user_modules: Dict[str, str] = {}
        self._on_module_load_callback = on_module_load_callback

    def setup(
        self,
        show_skips: bool = False,
        caller_frame: Optional[FrameType] = None,
    ):
        """
        Setup the import hook to keep track of user module imports.
        """
        self._console.print("Seting up the import hook", style="green on black")
        self._show_skips = show_skips
        caller_frame = caller_frame or sys._getframe(1)
        caller_code_obj = caller_frame.f_code
        if caller_code_module := inspect.getmodule(caller_code_obj):
            self._console.print(
                "Calling fever dep tracker from",
                caller_code_module.__name__,
                inspect.getfile(caller_code_obj),
                style="italic blue on black",
            )
            self._user_modules[caller_code_module.__name__] = inspect.getfile(
                caller_code_obj
            )
        else:
            warnings.warn(
                "Could not determine caller module for Fever setup. Please make a bug report.",
                FeverWarning,
            )
        # NOTE: For now we don't need this hook bc we don't need the full dependency graph
        # self._original_importer = builtins.__import__
        # builtins.__import__ = self._import

        # Insert our finder/loader as top priority:
        sys.meta_path.insert(0, self)

    def cleanup(self):
        """
        Remove the import hook.
        """
        self._console.print("Cleaning up the import hook", style="green on black")
        # builtins.__import__ = self._original_importer
        for finder in sys.meta_path.copy():
            if isinstance(finder, self.__class__):
                sys.meta_path.remove(finder)

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        _ = spec
        return None  # Fallback to default machinery

    def exec_module(self, module) -> None:
        file_path = None
        if module_spec := getattr(module, "__spec__", None):
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
            code_obj = compile(code_str, file_path, "exec")
            exec(
                code_obj, module.__dict__
            )  # Execute the code in the module's namespace
            self._console.print("\t - Done!", style="green on black")
            # NOTE: Our main post-load hook is to run the AST analysis and decorate all
            # callables in the module; see call_tracker.py for that.
            self._on_module_load_callback(module.__name__)

    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target=None
    ) -> ModuleSpec | None:
        """
        For top-level imports, path will be None. Otherwise, this is a search for
        a subpackage or module and path will be the value of __path__ from the parent
        package. When passed in, target is a module object that the finder may use to
        make a more educated guess about what spec to return.
        """
        _ = target
        curdir = os.getcwd()
        path = [curdir] if path is None or path == [] else path
        name = fullname.split(".")[-1] if "." in fullname else fullname
        if (
            os.path.commonpath([os.path.abspath(path[0]), os.path.abspath(str(curdir))])
            != curdir
        ):
            return None

        for entry in path:
            if any([d in entry for d in self._absolute_ignore_dirs]):
                if self._show_skips:
                    self._console.print(
                        f"Skipping ignored path '{entry}'", style="red on black"
                    )
                return None
            if self._show_skips:
                self._console.print(
                    f"Searching for module '{fullname}' in path entry '{entry}'",
                    style="italic yellow on black",
                )
            file_path, submodule_locations = find_module_path(entry, name)
            if file_path is None:
                # NOTE: In edge cases, the user may alter the system path to emulate
                # project imports from other locations within the project's tree, such
                # as git submodules or vendors. We handle this here:
                for sys_path in sys.path:
                    if self._show_skips:
                        self._console.print(
                            f"Searching for {fullname} in sys path {sys_path}",
                            style="italic yellow on black",
                        )
                    if any([d in sys_path for d in self._absolute_ignore_dirs]):
                        continue
                    if (
                        os.path.commonpath(
                            [os.path.abspath(entry), os.path.abspath(sys_path)]
                        )
                        == entry
                    ):
                        file_path, submodule_locations = find_module_path(
                            sys_path, name
                        )
                        if file_path:  # Found it
                            break
                if file_path is None:
                    continue

            # INFO: Finding the caller module in the finder seems difficult, probably  due
            # to the import chains that call the finder and since we use the call frame to
            # find the caller. So we use the __import__ override hook for this, which is
            # also very useful for re-imports that don't call the finder/loader. That way we
            # can keep track of dependencies everywhere, which we couldn't do with just the
            # loader/finder.
            self._dep_graph.add_node(fullname)
            return importlib.util.spec_from_file_location(
                fullname,
                file_path,
                loader=self,
                submodule_search_locations=submodule_locations,
            )
        if self._show_skips:
            self._console.print(
                f"Module '{fullname}' not found in path '{path}'", style="red on black"
            )
        return None

    def invalidate_caches(self):
        self._user_modules = {}

    # NOTE: We actually don't need the module imports DAG, so this hook is disabled for
    # now. If the DAG is needed in the future, we can re-enable it.
    # def _import(
    #     self, name: str, globals=None, locals=None, fromlist=(), level=0
    # ) -> ModuleType:
    #     fromlist = fromlist or ()
    #     module = self._original_importer(
    #         name, globals=globals, locals=locals, fromlist=fromlist, level=level
    #     )
    #     path = self._user_modules.get(name, None)
    #     if path is None:
    #         return module
    #
    #     caller_module = (
    #         (globals["__name__"], globals["__file__"])
    #         if globals is not None
    #         else (None, None)
    #     )
    #     path = (
    #         self._user_modules.get(caller_module[0], None) if caller_module[0] else None
    #     )
    #     if path is None:
    #         if self._show_skips:
    #             self._console.print(
    #                 f"Skipping module '{name}' imported from non-user module"
    #                 + f"'{caller_module[0]}' defined in '{caller_module[1]}'",
    #                 style="red on black",
    #             )
    #         return module
    #
    #     composite_name = name if len(fromlist) == 0 else name + "." + ".".join(fromlist)
    #     self._console.print(
    #         f"Importing '{composite_name}' "
    #         + f"from module '{caller_module[0]}' defined in '{caller_module[1]}",
    #         style="yellow on black",
    #     )
    #     if caller_module[0] is not None:
    #         # WARN: If the composite name is module.func or module.class we
    #         # map it to module! But ideally we dont want to reload the entire
    #         # module, so we need a way to specify that func is in namespace module. For
    #         # now we load the entire module because it's much simpler and it's not
    #         # critical that we only load specific items.
    #         # INFO: It turns out that the composite name is not given to the meta
    #         # finder! So that means that the import function loads the entire module and
    #         # returns only the function of interest anyway, right?
    #         parts = composite_name.split(".")
    #         for i, el in enumerate(parts):
    #             if el in sys.modules:
    #                 # Either the element is a function
    #                 self._dep_graph.add_edge(caller_module[0], el)
    #             elif ".".join(parts[: i + 1]) in sys.modules:
    #                 # Or the combination is a submodule
    #                 self._dep_graph.add_edge(caller_module[0], ".".join(parts[: i + 1]))
    #
    #     self.fever.on_new_import(name, module)
    #     return module

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

        warnings.warn(
            "DependencyTracker.plot(): The module imports DAG is currently disabled as it's not needed. "
            + "The plot only shows imported module nodes.",
            FeverWarning,
        )

        plt.tight_layout()
        nx.draw_networkx(self._dep_graph, arrows=True)
        plt.show()

    @property
    def all_imports(self) -> List[str]:
        return list(self._dep_graph.nodes)
