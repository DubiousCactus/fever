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
    FeverModule,
    generic_function,
)
from fever.dependency_tracker import ModuleLoadHook
from fever.hooks import RegistryAddHook
from fever.utils import ConsoleInterface


class Registry(ModuleLoadHook):
    # FIXME: Get rid of these and instead place the code pointers in the _callables
    # attribute! Just simplify all these dicts, it's a mess seriously.
    _FUNCTION_DEFS = defaultdict(dict)
    _CLASS_METHOD_DEFS = defaultdict(dict)

    def __init__(self, ast_analyzer: ASTAnalyzer, console_if: ConsoleInterface):
        self._console = console_if
        self._ast_analyzer = ast_analyzer
        self._callables: Dict[str, FeverModule] = {}
        self._hooks: List[RegistryAddHook] = []

    def cleanup(self) -> None:
        # WARN: This is important because the registry definitions are static class
        # attributes, i.e. they persist across multiple instances of Registry. I may
        # move them to instance attributes, but for now I like to think that it's safer
        # like that in case we ever have multiple fever instances running in the same
        # code base. This would prevent redefining functions.
        self._FUNCTION_DEFS.clear()
        self._CLASS_METHOD_DEFS.clear()

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

    def find_class_by_name(self, name: str, module_name: str) -> FeverClass | None:
        for cls_ in self._callables[module_name].classes:
            if cls_.name == name:
                return cls_
        return None

    def add_function(self, module_name: str, callable: FeverFunction) -> None:
        if module_name not in self._callables:
            raise KeyError(f"'{module_name}' is not a tracked module")
        assert callable != generic_function, (
            "add_function(): Cannot register generic_function"
        )
        if isinstance(callable, FeverFunction):
            self._callables[module_name].functions.append(callable)
        for hook in self._hooks:
            hook.on_registry_add(self._callables[module_name])

    def add_method(
        self, module_name: str, class_: FeverClass, callable: FeverFunction
    ) -> None:
        if module_name not in self._callables:
            raise KeyError(f"'{module_name}' is not a tracked module")
        assert callable != generic_function, (
            "add_function(): Cannot register generic_function"
        )
        if isinstance(callable, FeverFunction):
            self._callables[module_name].methods[class_].append(callable)
        for hook in self._hooks:
            hook.on_registry_add(self._callables[module_name])

    def on_module_load(self, module_name: str, code_str: str) -> None:
        self._console.print(
            f"Analyzing AST for module '{module_name}'", style="blue on black"
        )
        module = sys.modules[module_name]
        self._callables[module_name] = self._ast_analyzer.analyze(
            module_name, module, show_ast=False
        )
        assert self._callables[module_name].obj == module
        for hook in self._hooks:
            hook.on_registry_add(self._callables[module_name])
