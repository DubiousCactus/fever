#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:24:32 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import os
from typing import List, Optional, Tuple

from rich.console import Console


class ConsoleInterface:
    def __init__(self, console: Optional[Console]):
        self.console = console
        self._print = console.print if console else lambda *a, **k: None

    def print(self, *args, **kwargs):
        self._print(*args, **kwargs)


def is_user_module(
    module_name: str, ignore_dirs: List[str], module_path: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    # FIXME: This current solution is kinda fragile. I need something robust.
    if module_name == "":
        return False, None
    module_dir = os.path.dirname(module_path) if module_path is not None else None
    for root, dirs, files in os.walk(os.path.curdir):
        try:
            for ignore_dir in ignore_dirs:
                dirs[:] = [d for d in dirs if d == ignore_dir]
        except Exception:
            pass
        if module_dir is not None and os.path.basename(module_dir) == root:
            return True, module_path
        for f in files:
            if f.split(".")[0] == module_name:
                return True, os.path.join(root, f)
            elif module_path is not None and os.path.basename(module_path) == f:
                return True, module_path
        for d in dirs:
            if module_name == d:
                return True, os.path.join(root, d, "__init__.py")
            elif module_dir == d:
                return True, module_path
    return False, None
