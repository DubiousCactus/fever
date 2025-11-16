import os
import sys
import threading
from pathlib import Path
from typing import Optional

import pywatchman
from rich.console import Console

from fever.utils import ConsoleInterface, parse_verbosity

from .core import FeverCore


class FeverWatcher:
    def __init__(
        self, rich_console: Optional[Console] = None, root_dir: Optional[str] = None
    ):
        self._root_dir = root_dir or str(Path.cwd())
        self._verbosity = parse_verbosity()
        console = None if self._verbosity == 0 else (rich_console or Console())
        self._console_if: ConsoleInterface = ConsoleInterface(console)
        self.fever = FeverCore(self._console_if.console)
        self._running = False

    def watch(self):
        self._running = True
        client = pywatchman.client(timeout=10.0)
        res = client.query("watch-project", self._root_dir)
        watch_root = res["watch"]

        client.query(
            "subscribe",
            watch_root,
            "watcher_sub",
            {
                "expression": ["type", "f"],
                "fields": ["name", "mtime_ms"],
            },
        )

        # Drain initial event
        try:
            client.receive()
        except pywatchman.SocketTimeout:
            pass

        def run_blocking():
            while self._running:
                try:
                    msg = client.receive()
                except pywatchman.SocketTimeout:
                    continue

                if (
                    msg
                    and msg.get("subscription") == "watcher_sub"
                    and not msg.get("is_fresh_instance")
                ):
                    files = msg.get("files", [])
                    if files:
                        # Call async callback safely
                        self._console_if.print(
                            f"Changed files: {[os.path.basename(f['name']) for f in files]}",
                            style="green on black",
                        )
                        self.fever.reload(
                            [
                                os.path.basename(f["name"]).replace(".py", "")
                                for f in files
                            ]
                        )

        self.fever.setup(caller_frame=sys._getframe(1))
        t = threading.Thread(target=run_blocking, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        self.fever.cleanup()
