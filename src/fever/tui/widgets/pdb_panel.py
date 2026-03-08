import asyncio
import fcntl
import os
import pty
import struct
import termios

import pyte
from textual.containers import Vertical
from textual.widget import Widget

ESCAPE_SEQUENCES = {
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "backspace": b"\x7f",
    "tab": b"\t",
    "enter": b"\n",
}


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
        self.has_sent = False
        self._child_pid, self._child_fd = None, None

    def on_mount(self) -> None:
        self._spawn_repl()

    def _spawn_repl(self):
        pid, fd = pty.fork()
        if pid == 0:
            # In child process: execute PDB++
            # os.execvp("python", ["python", "-m", "pdbpp"])
            os.execvpe(
                "python3",
                ["python3", "-i"],
                {**os.environ, "TERM": "xterm-256color"},
            )

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
            os.close(self._child_fd)
            self._child_fd = None

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

    def send_user_input(self, input_str: str) -> None:
        if self._child_fd is not None:
            os.write(self._child_fd, input_str.encode())

    def send_escape_seq(self, seq: bytes) -> None:
        if self._child_fd is not None:
            os.write(self._child_fd, seq)


class PDBPanel(Vertical, can_focus=True):
    """Container for the Debugger interface."""

    def compose(self):
        yield PDBWidget()

    def on_mount(self) -> None:
        self.widget = self.query_one(PDBWidget)
        self.border_title = "Debugger (PDB++)"
        self.focus()

    def on_key(self, event) -> None:
        if event.key == "ctrl+d":
            self.terminate()
        else:
            self._handle_user_input(event)
        event.stop()

    def on_paste(self, event) -> None:
        self.widget.send_user_input(event.text)
        event.stop()

    def _handle_user_input(self, event) -> None:
        if event.key == "escape":
            self.blur()
            self.styles.border = ("solid", "gray")
        elif event.is_printable:
            self.widget.send_user_input(event.character)
        elif event.key in ESCAPE_SEQUENCES:
            # Non printable characters: up/down arrows, etc. Is that handled by the terminal emulator or by the program??
            self.widget.send_escape_seq(ESCAPE_SEQUENCES[event.key])
        else:
            self.blink()

    def blink(self):
        self.styles.animate(
            "opacity",
            value=0.0,
            duration=0.05,
            on_complete=lambda: self.styles.animate(
                "opacity", value=1.0, duration=0.05
            ),
        )

    def on_resize(self, event) -> None:
        new_size = event.size
        child_fd = self.widget._child_fd
        if child_fd is None:
            return
        cols, rows = new_size.width, new_size.height

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(child_fd, termios.TIOCSWINSZ, winsize)
        self.widget._display.resize(rows, cols)
        self.refresh()

    def on_focus(self, event) -> None:
        self.styles.border = ("solid", "green")

    def terminate(self) -> None:
        self.widget.terminate()
        self.widget.remove()
        self.mount(PDBWidget())
        self.widget = self.query_one(PDBWidget)
