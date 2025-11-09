#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:15:09 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import sys
from collections import defaultdict
from typing import Dict

from fever.ast_analysis import (
    ASTAnalyzer,
    FeverClass,
    FeverFunction,
    FeverModule,
    GenericClass,
    generic_function,
)
from fever.utils import ConsoleInterface


class Registry:
    # FIXME: Get rid of these and instead place the code pointers in the _callables
    # attribute! Just simplify all these dicts, it's a mess seriously.
    _FUNCTION_DEFS = defaultdict(dict)
    _CLASS_METHOD_DEFS = defaultdict(dict)
    _CLASS_DEFS = defaultdict(dict)

    def __init__(
        self,
        ast_analyzer: ASTAnalyzer,
        console_if: ConsoleInterface,
        fever,
    ) -> None:
        self._console = console_if
        self._ast_analyzer = ast_analyzer
        self._callables: Dict[str, FeverModule] = {}
        self.fever = fever

    def cleanup(self) -> None:
        # WARN: This is important because the registry definitions are static class
        # attributes, i.e. they persist across multiple instances of Registry. I may
        # move them to instance attributes, but for now I like to think that it's safer
        # like that in case we ever have multiple fever instances running in the same
        # code base. This would prevent redefining functions.
        self._FUNCTION_DEFS.clear()
        self._CLASS_METHOD_DEFS.clear()
        self._CLASS_DEFS.clear()

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
        assert callable is not generic_function, (
            "add_function(): Cannot register generic_function"
        )
        assert isinstance(callable, FeverFunction), (
            "add_function(): 'callable' must be a FeverFunction"
        )
        self._callables[module_name].functions.append(callable)

    def add_method(
        self, module_name: str, class_: FeverClass, callable: FeverFunction
    ) -> None:
        if module_name not in self._callables:
            raise KeyError(f"'{module_name}' is not a tracked module")
        assert callable is not generic_function, (
            "add_function(): Cannot register generic_function"
        )
        assert isinstance(callable, FeverFunction), (
            "add_function(): 'callable' must be a FeverFunction"
        )
        self._callables[module_name].methods[class_].append(callable)

    def add_class(self, module_name: str, class_: FeverClass) -> None:
        if module_name not in self._callables:
            raise KeyError(f"'{module_name}' is not a tracked module")
        assert class_ is not GenericClass, "add_class(): Cannot register GenericClass"
        assert isinstance(class_, FeverClass), (
            "add_class(): 'class_' must be a FeverClass"
        )
        self._callables[module_name].classes.append(class_)

    def make_inventory(self, module_name: str) -> FeverModule:
        self._console.print(
            f"Analyzing AST for module '{module_name}'", style="blue on black"
        )
        module = sys.modules[module_name]
        self._callables[module_name] = self._ast_analyzer.analyze(
            module_name, module, show_ast=False
        )
        assert self._callables[module_name].obj == module
        return self._callables[module_name]
