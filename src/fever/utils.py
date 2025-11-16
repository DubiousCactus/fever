#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-11 17:24:32 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


from typing import Optional

from rich.console import Console


class FeverWarning(Warning):
    pass


class ConsoleInterface:
    def __init__(self, console: Optional[Console]):
        self.console = console
        self._print = console.print if console else lambda *a, **k: None

    def print(self, *args, **kwargs):
        self._print(*args, **kwargs)
