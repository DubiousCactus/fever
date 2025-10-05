#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-05 13:06:07 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import inspect
import sys
from collections import defaultdict
from importlib.abc import MetaPathFinder
from typing import Dict, List, Optional, Sequence

from rich.console import Console

console = Console()


class ImportHook(MetaPathFinder):
    def __init__(self):
        self._dependencies: Dict[str, List[str]] = defaultdict(list)

    def setup(self):
        self.cleanup()
        console.print("Seting up the import hook", style="green on black")
        sys.meta_path.insert(0, self)

    def cleanup(self):
        console.print("Cleaning up the import hook", style="green on black")
        for finder in sys.meta_path.copy():
            if isinstance(finder, self.__class__):
                sys.meta_path.remove(finder)

    def find_spec(
        self, fullname: str, import_path: Optional[Sequence[str]] = None, target=None
    ):
        """
        For top-level imports, import_path will be None. Otherwise, this is a search for
        a subpackage or module and path will be the value of __path__ from the parent
        package. When passed in, target is a module object that the finder may use to
        make a more educated guess about what spec to return.
        """
        caller_module = None
        for frame in inspect.stack():
            if frame.code_context is None:
                continue
            for context in frame.code_context:
                if fullname in context and "import" in context:
                    caller_module = inspect.getmodulename(frame.filename)
        console.print(
            f"Importing '{fullname}' from module '{caller_module}'",
            style="green on black",
        )
        if caller_module is not None:
            self._dependencies[caller_module].append(fullname)
        return None  # Fallback to other finders (default behaviour of import())
