#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:15:09 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import logging
import sys
from collections import defaultdict
from typing import Any, Dict, Optional

from fever.ast_analysis import (
    FeverClass,
    FeverFunction,
    FeverImport,
    FeverModule,
    GenericClass,
    generic_function,
)
from fever.types import FeverParameters

log = logging.getLogger("fever-registry")


class Registry:
    _FUNCTION_PTRS = defaultdict(dict)
    _CLASS_METHOD_PTRS = defaultdict(dict)
    _CLASS_PTRS = defaultdict(dict)

    def __init__(
        self,
    ) -> None:
        self._inventory: Dict[str, FeverModule] = {}

    def cleanup(self) -> None:
        # WARN: This is important because the registry definitions are static class
        # attributes, i.e. they persist across multiple instances of Registry. I may
        # move them to instance attributes, but for now I like to think that it's safer
        # like that in case we ever have multiple fever instances running in the same
        # code base. This would prevent redefining functions.
        self._FUNCTION_PTRS.clear()
        self._CLASS_METHOD_PTRS.clear()
        self._CLASS_PTRS.clear()

    def find_import_by_name_or_alias(
        self, name: str, module_name: str, alias: Optional[str] = None
    ) -> FeverImport | None:
        for import_ in self._inventory[module_name].imports:
            if import_.module == name or (alias is not None and import_.alias == alias):
                return import_
        return None

    def find_function_by_name(
        self, name: str, module_name: str
    ) -> FeverFunction | None:
        for func in self._inventory[module_name].functions:
            if func.name == name:
                return func
        return None

    def find_method_by_name(
        self, name: str, class_name: str, module_name: str
    ) -> FeverFunction | None:
        for cls_, methods in self._inventory[module_name].methods.items():
            if cls_.name != class_name:
                continue
            for method in methods:
                if method.name == name:
                    return method
        return None

    def find_class_by_name(self, name: str, module_name: str) -> FeverClass | None:
        for cls_ in self._inventory[module_name].classes:
            if cls_.name == name:
                return cls_
        return None

    def _add_function_code_pointer(self, module_name: str, func: FeverFunction) -> None:
        if func.name not in self._FUNCTION_PTRS[module_name]:
            self._FUNCTION_PTRS[module_name][func.name] = func.obj

    def add_function(self, module_name: str, func: FeverFunction) -> None:
        assert func is not generic_function, (
            "add_function(): Cannot register generic_function"
        )
        assert isinstance(func, FeverFunction), (
            "add_function(): 'callable' must be a FeverFunction"
        )
        self._inventory[module_name].functions.append(func)
        self._add_function_code_pointer(module_name, func)

    def _add_method_code_pointer(
        self, module_name: str, class_: FeverClass, method: FeverFunction
    ) -> None:
        if class_.name not in self._CLASS_METHOD_PTRS[module_name]:
            self._CLASS_METHOD_PTRS[module_name][class_.name] = {
                method.name: method.obj
            }
        elif method.name not in self._CLASS_METHOD_PTRS[module_name][class_.name]:
            self._CLASS_METHOD_PTRS[module_name][class_.name][method.name] = method.obj

    def add_method(
        self, module_name: str, class_: FeverClass, method: FeverFunction
    ) -> None:
        assert method is not generic_function, (
            "add_method(): Cannot register generic_function"
        )
        assert isinstance(method, FeverFunction), (
            "add_method(): 'callable' must be a FeverFunction"
        )
        self._inventory[module_name].methods[class_].append(method)
        self._add_method_code_pointer(module_name, class_, method)

    def _add_class_code_pointer(self, module_name: str, class_: FeverClass) -> None:
        if class_.name not in self._CLASS_METHOD_PTRS[module_name]:
            self._CLASS_METHOD_PTRS[module_name][class_.name] = {}
        if class_.name not in self._CLASS_PTRS[module_name]:
            self._CLASS_PTRS[module_name][class_.name] = class_.obj

    def add_class(self, module_name: str, class_: FeverClass) -> None:
        assert class_ is not GenericClass, "add_class(): Cannot register GenericClass"
        assert isinstance(class_, FeverClass), (
            "add_class(): 'class_' must be a FeverClass"
        )
        self._inventory[module_name].classes.append(class_)
        self._add_class_code_pointer(module_name, class_)

    def add_import(self, module_name: str, import_: FeverImport) -> None:
        self._inventory[module_name].imports.append(import_)

    def add_module(self, module_name: str, module: FeverModule) -> None:
        """
        Adds a fever module to the registry inventory, along with its callable code
        pointers.
        """
        self._inventory[module_name] = module
        for func in module.functions:
            self._add_function_code_pointer(module_name, func)
        for cls_ in module.classes:
            self._add_class_code_pointer(module_name, cls_)
            for method in module.methods[cls_]:
                self._add_method_code_pointer(module_name, cls_, method)

    def invoke(self, module_name: str, func_name: str, params: FeverParameters) -> Any:
        log.debug(f"invoking {func_name} with {len(params)} args")
        return getattr(sys.modules[module_name], func_name)(
            *params.args, **params.kwargs_dict
        )
