from typing import Optional

from rich.console import Console

from .call_tracker import CallTracker
from .dependency_tracker import DependencyTracker
from .utils import ConsoleInterface


class Fever:
    def __init__(self, debug: bool = False, rich_console: Optional[Console] = None):
        self._debug = debug
        console = None if not debug else (rich_console or Console())
        self._console_if = ConsoleInterface(console)
        self.dependency_tracker = DependencyTracker(self._console_if)
        self.call_tracker = CallTracker(self._console_if)

    def setup(self):
        self.dependency_tracker.setup(show_skips=self._debug)
        self.call_tracker.track(self.dependency_tracker)

    def cleanup(self):
        self.dependency_tracker.cleanup()

    def plot_dependency_graph(self):
        self.dependency_tracker.plot()

    def plot_call_graph(self):
        self.call_tracker.plot()
