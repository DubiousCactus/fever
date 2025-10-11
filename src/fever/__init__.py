import os
from typing import Optional

from rich.console import Console

from fever.registry import Registry

from .call_tracker import CallTracker
from .dependency_tracker import DependencyTracker
from .utils import ConsoleInterface


def parse_verbosity() -> int:
    v = os.getenv("VERBOSITY", "").lower()
    if v in ("v", "1"):
        return 1
    elif v in ("vv", "2"):
        return 2
    elif v in ("vvv", "3"):
        return 3
    return 0


class Fever:
    def __init__(self, rich_console: Optional[Console] = None):
        self._verbosity = parse_verbosity()
        console = None if self._verbosity == 0 else (rich_console or Console())
        self._console_if = ConsoleInterface(console)
        self.dependency_tracker = DependencyTracker(
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None)
        )
        self.call_tracker = CallTracker(
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None)
        )
        self.registry = Registry(
            self._console_if if self._verbosity >= 1 else ConsoleInterface(None)
        )

    def setup(self):
        self.dependency_tracker.setup(show_skips=self._verbosity == 3)
        self.call_tracker.track(self.dependency_tracker)

    def cleanup(self):
        self.dependency_tracker.cleanup()

    def plot_dependency_graph(self):
        self.dependency_tracker.plot()

    def plot_call_graph(self):
        self.call_tracker.plot()
