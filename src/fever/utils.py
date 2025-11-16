#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:24:32 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import os
from typing import Optional

from rich.console import Console


class FeverWarning(Warning):
    pass


def parse_verbosity() -> int:
    v = os.getenv("VERBOSITY", "").lower()
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
    def __init__(self, console: Optional[Console]):
        self.console = console
        self._print = console.print if console else lambda *a, **k: None

    def print(self, *args, **kwargs):
        self._print(*args, **kwargs)
