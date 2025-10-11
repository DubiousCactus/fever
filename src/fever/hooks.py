#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 23:31:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import abc
from types import ModuleType

from fever.ast_analysis import FeverModule


class NewImportHook(metaclass=abc.ABCMeta):
    def on_new_import(self, module_name: str, module: ModuleType) -> ModuleType:
        raise NotImplementedError


class ModuleLoadHook(metaclass=abc.ABCMeta):
    def on_module_load(self, module_name: str, code_str: str) -> None:
        raise NotImplementedError


class RegistryAddHook(metaclass=abc.ABCMeta):
    def on_registry_add(self, module: FeverModule) -> None:
        raise NotImplementedError
