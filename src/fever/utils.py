#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:24:32 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import os
from typing import Callable, Optional

from rich.console import Console


def parse_verbosity() -> int:
    v = os.getenv("FEVER_VERBOSITY", "").lower()
    if v in ("v", "1"):
        return 1
    elif v in ("vv", "2"):
        return 2
    elif v in ("vvv", "3"):
        return 3
    elif v in ("vvvv", "4"):
        return 4
    return 0


class ConsoleInterface:
    def __init__(
        self,
        console: Optional[Console] = None,
        ui_logger: Optional[Callable] = None,
    ):
        self.console = console
        self.ui_logger = ui_logger
        if console is not None:
            self._print = console.print
        elif ui_logger is not None:
            self._print = ui_logger
        else:
            self._print = lambda *a, **k: None

    def print(self, *args, **kwargs):
        self._print(*args, **kwargs)
