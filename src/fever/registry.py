#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:15:09 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import sys
from collections import defaultdict
from typing import Dict, List

from fever.ast_analysis import (
    ASTAnalyzer,
    FeverClass,
    FeverFunction,
    FeverLambda,
    FeverModule,
)
from fever.dependency_tracker import ModuleLoadHook
from fever.hooks import RegistryAddHook
from fever.utils import ConsoleInterface


class Registry(ModuleLoadHook):
    _FUNCTION_DEFS = defaultdict(dict)
    _CLASS_METHOD_DEFS = defaultdict(dict)

    def __init__(self, ast_analyzer: ASTAnalyzer, console_if: ConsoleInterface):
        self._console = console_if
        self._ast_analyzer = ast_analyzer
        self._callables: Dict[str, FeverModule] = {}
        self._hooks: List[RegistryAddHook] = []

    def register_add_hook(self, hook: RegistryAddHook) -> None:
        self._hooks.append(hook)

    def find_function_by_name(
        self, name: str, module_name: str
    ) -> FeverFunction | None:
        for func in self._callables[module_name].functions:
            if func.name == name:
                return func
        return None

    def find_method_by_name(
        self, name: str, class_name: str, module_name: str
    ) -> FeverFunction | None:
        for cls_, methods in self._callables[module_name].methods.items():
            if cls_.name != class_name:
                continue
            for method in methods:
                if method.name == name:
                    return method
        return None

    def find_class_by_name(self, name: str) -> FeverClass | None:
        return None

    def add(
        self, module_name: str, callable: FeverFunction | FeverClass | FeverLambda
    ) -> None:
        raise NotImplementedError
        if module_name not in self._callables:
            raise KeyError(f"'{module_name}' is not a tracked module")
        if isinstance(callable, FeverFunction):
            self._callables[module_name].functions.append(callable)
        else:
            raise NotImplementedError
        for hook in self._hooks:
            hook.on_registry_add(self._callables[module_name])

    def on_module_load(self, module_name: str, code_str: str) -> None:
        if module_name == "fever":
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
        # TODO: Move this line to the registry! Then the registry should call a hook
        # into the call tracker which will wrap the function.
        self._callables[module_name] = self._ast_analyzer.analyze(
            module_name, module, show_ast=False
        )
        for hook in self._hooks:
            hook.on_registry_add(self._callables[module_name])
