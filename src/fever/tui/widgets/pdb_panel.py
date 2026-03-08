import asyncio
import fcntl
import os
import pty

import pyte
from textual.containers import Vertical
from textual.widget import Widget


class PDBDisplay(pyte.Screen):
    def __rich_console__(self, console, options):
        yield from self.display


class PDBWidget(Widget):
    """Simple widget to display PDB content."""

    def __init__(self):
        super().__init__()
        self._display = PDBDisplay(80, 24)
        self._out_stream = pyte.ByteStream(self._display)
        self.process_task = None
        self._ctrld_flag = False
        self.has_sent = False
        self._child_pid, self._child_fd = None, None

    def on_mount(self) -> None:
        self._spawn_repl()

    def _spawn_repl(self):
        pid, fd = pty.fork()
        if pid == 0:
            # In child process: execute PDB++
            # os.execvp("python", ["python", "-m", "pdbpp"])
            os.execvp("python3", ["python3", "-i"])

        self._child_pid, self._child_fd = pid, fd
        # Make the file descriptor non-blocking:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Add reader callback to the event loop:
        loop = asyncio.get_running_loop()
        loop.add_reader(fd, self._read_ready)

    def _read_ready(self):
        assert self._child_fd is not None
        try:
            data = os.read(self._child_fd, 1024)
        except BlockingIOError:
            return
        except OSError:
            self._shutdown()
            return

        if not data:
            self._shutdown()
            return

        self._out_stream.feed(data)
        self.refresh()

        if not self.has_sent and self._prompt_visible():
            os.write(self._child_fd, b'print("hello world")\n')
            self.has_sent = True

    def _shutdown(self):
        loop = asyncio.get_running_loop()

        if self._child_fd:
            loop.remove_reader(self._child_fd)
            os.close(self.fchild_d)
            self.fd = None

        if self._child_pid:
            try:
                os.kill(self._child_pid, 9)  # Force kill the child process
            except ProcessLookupError:
                pass
            self._child_pid = None

    def render(self):
        return self._display

    def terminate(self) -> None:
        self._shutdown()

    def _prompt_visible(self):
        for line in self._display.display:
            if line.rstrip().endswith(">>>"):
                return True
        return False


class PDBPanel(Vertical):
    """Container for the Debugger interface."""

    def compose(self):
        yield PDBWidget()

    def on_mount(self) -> None:
        self.border_title = "Debugger (PDB++)"

    def terminate(self) -> None:
        widget = self.query_one(PDBWidget)
        widget.terminate()
