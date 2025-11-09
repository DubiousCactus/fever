#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:24:32 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


from typing import Dict, Optional

from rich.console import Console


class ConsoleInterface:
    def __init__(self, console: Optional[Console]):
        self.console = console
        self._print = console.print if console else lambda *a, **k: None

    def print(self, *args, **kwargs):
        self._print(*args, **kwargs)


def compile_code_in_namespace(
    code: str, callable_name: str, module_namespace: Dict, registry_namespace: Dict
) -> None:
    """
    Execute the given code string in the provided registry namespace, such that the
    function/class/method object pointer is stored in the registry. To do this, we copy
    the module namespace and the registry namespace in a temporary namespace so that
    exec() can access the globals during execution. We then update the registry
    namespace with the new code definition. This seems like the most robust solution
    right now, but I will think about it again and implement loads of tests.
    """
    exec_namespace = module_namespace | registry_namespace
    exec(code, exec_namespace)
    registry_namespace.update(
        {
            k: v
            for k, v in exec_namespace.items()
            if k in registry_namespace or k == callable_name
        }
    )
