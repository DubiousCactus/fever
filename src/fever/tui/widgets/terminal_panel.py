import asyncio
import fcntl
import logging
import os
import pty
import struct
import termios
from collections import deque
from types import FrameType, ModuleType, TracebackType
from typing import Any, List, Optional

import pyte
from rich.segment import Segment
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Label, Static

ESCAPE_SEQUENCES = {
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "backspace": b"\x7f",
    "tab": b"\t",
    "enter": b"\n",
}

logging.basicConfig(
    filename="fever_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("fever")


class RichPyteDisplay(pyte.Screen):
    def __init__(self, parent, columns: int, lines: int, history_size: int = 300):
        self.history = deque(maxlen=history_size)
        self._cursor_char = "_"
        self.initialized = False
        self.parent = parent
        super().__init__(columns, lines)

    def _reset_history(self) -> None:
        self.history.clear()

    def reset(self) -> None:
        """Overloaded to reset screen history state: history position
        is reset to bottom of both queues;  queues themselves are
        emptied.
        """
        super().reset()
        self._reset_history()

    def erase_in_display(self, how: int = 0, *args: Any, **kwargs: Any) -> None:
        """Overloaded to reset history state."""
        super().erase_in_display(how, *args, **kwargs)

        if how == 3:
            self._reset_history()

    def _scroll_end(self) -> None:
        if self.parent.is_vertical_scrollbar_grabbed:
            return
        self.parent.scroll_end(animate=False, immediate=True, x_axis=False)

    def index(self) -> None:
        """Overloaded to update top history with the removed lines."""
        top, bottom = self.margins or pyte.screens.Margins(0, self.lines - 1)

        if self.cursor.y == bottom:
            self.history.append(str(self.display[top]))
            self.parent.virtual_size = self.virtual_size
            self.parent.call_after_refresh(self._scroll_end)

        super().index()

    def resize(self, lines: int, columns: int):
        super().resize(lines, columns)
        self.parent.virtual_size = self.virtual_size
        self.initialized = True

    async def blink(self, interval_sec: float):
        while True:
            await asyncio.sleep(interval_sec)
            self._cursor_char = " " if self._cursor_char == "_" else "_"
            self.parent.refresh()

    @property
    def virtual_size(self) -> Size:
        return Size(self.columns - 2, len(self.history) + self.lines)

    def _buffer_line_with_cursor(self, buffer_y: int) -> str:
        buffer_line = self.display[buffer_y]
        if buffer_y == self.cursor.y:
            buffer_line = (
                buffer_line[: self.cursor.x]
                + self._cursor_char
                + buffer_line[self.cursor.x + 1 :]
            )
        return buffer_line

    def render_line(self, y: int) -> Strip:
        total_lines = len(self.history) + self.lines
        if y < 0 or y >= total_lines:
            return Strip.blank(self.parent.size.width)

        if len(self.history) == 0:
            return (
                Strip([Segment(self._buffer_line_with_cursor(y))])
                if y < self.lines
                else Strip.blank(self.parent.size.width)
            )
        elif y < len(self.history):
            return Strip([Segment(self.history[y])])
        else:
            return Strip(
                [Segment(self._buffer_line_with_cursor(y - len(self.history)))]
            )


class BasicTerminalWidget(ScrollView):
    def __init__(self, executable: Optional[str] = None, args: List[str] = []):
        super().__init__()
        self._display = RichPyteDisplay(self, 80, 1)
        self._out_stream = pyte.ByteStream(self._display)
        self.process_task = None
        self.has_sent = False
        self._child_pid, self._child_fd = None, None
        self.executable = executable
        self.args = args
        self.virtual_size = self._display.virtual_size

    def on_mount(self) -> None:
        self._spawn_repl()

    def _spawn_repl(self):
        assert self.executable is not None, "Executable must be provided to spawn REPL"
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe(
                self.executable,
                [self.executable] + self.args,
                {**os.environ, "TERM": "xterm-256color"},
            )

        self._child_pid, self._child_fd = pid, fd
        # Make the file descriptor non-blocking:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Add reader callback to the event loop:
        loop = asyncio.get_running_loop()
        _ = loop.create_task(self._display.blink(0.5))
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

    def render_line(self, y: int) -> Strip:
        """Render a line of the widget. y is relative to the top of the widget."""
        _, scroll_y = self.scroll_offset  # The current scroll position
        y += scroll_y  # The line at the top of the widget is now `scroll_y`, not zero!
        if not self._display.initialized:
            return Strip.blank(self.size.width)
        return self._display.render_line(y)

    def terminate(self) -> None:
        self._shutdown()

    def send_user_input(self, input_str: str) -> None:
        if self._child_fd is not None:
            os.write(self._child_fd, input_str.encode())

    def send_escape_seq(self, seq: bytes) -> None:
        if self._child_fd is not None:
            os.write(self._child_fd, seq)


class PDBWidget(BasicTerminalWidget):
    def __init__(self, tb: Optional[TracebackType] = None):
        super().__init__(None, [])
        self.traceback: Optional[TracebackType] = tb

    def _spawn_repl(self):
        pid, fd = pty.fork()
        if pid == 0:
            import pdb
            import sys

            # First we must use the slave TTY by reopening the file descriptors for
            # stdin, stdout, and stderr. This is because pdb somehow manages to grab the
            # master's TTY file descriptors.
            sys.stdin = os.fdopen(0, "r", buffering=1)
            sys.stdout = os.fdopen(1, "w", buffering=1)
            sys.stderr = os.fdopen(2, "w", buffering=1)
            sys.stdout.flush()
            sys.stderr.flush()

            pdb.post_mortem(self.traceback)

            os._exit(0)  # Ensure the child process exits after pdb finishes

        self._child_pid, self._child_fd = pid, fd
        # Make the file descriptor non-blocking:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Add reader callback to the event loop:
        loop = asyncio.get_running_loop()
        _ = loop.create_task(self._display.blink(1.0))
        loop.add_reader(fd, self._read_ready)


class IPythonWidget(BasicTerminalWidget):
    def __init__(
        self, frame: Optional[FrameType] = None, module: Optional[ModuleType] = None
    ):
        super().__init__(None, [])
        self.frame: Optional[FrameType] = frame
        self.module: Optional[ModuleType] = module

    def _spawn_repl(self):
        pid, fd = pty.fork()
        if pid == 0:
            import sys

            import IPython

            # First we must use the slave TTY by reopening the file descriptors for
            # stdin, stdout, and stderr. This is because pdb somehow manages to grab the
            # master's TTY file descriptors.
            sys.stdin = os.fdopen(0, "r", buffering=1)
            sys.stdout = os.fdopen(1, "w", buffering=1)
            sys.stderr = os.fdopen(2, "w", buffering=1)
            sys.stdout.flush()
            sys.stderr.flush()

            shell = IPython.terminal.embed.InteractiveShellEmbed(
                banner1="IPython session for the currently hanged frame",
            )
            shell.mainloop(
                local_ns=self.frame.f_locals if self.frame else None,
                module=self.module,
                stack_depth=6,
            )

            os._exit(0)  # Ensure the child process exits after pdb finishes

        self._child_pid, self._child_fd = pid, fd
        # Make the file descriptor non-blocking:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Add reader callback to the event loop:
        loop = asyncio.get_running_loop()
        _ = loop.create_task(self._display.blink(1.0))
        loop.add_reader(fd, self._read_ready)


class TerminalPanel(Static, can_focus=True):
    def __init__(
        self,
        title: str,
        executable: Optional[str] = None,
        args: List[str] = [],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.executable = executable
        self.args = args
        self.border_title = title
        self.widget = None

    def compose(self):
        if self.executable is not None:
            self.widget = BasicTerminalWidget(self.executable, self.args)
            yield self.widget
        else:
            yield Label("Terminal not available for this frame.")

    def embed_pdb(self, tb: Optional[TracebackType] = None) -> None:
        asyncio.create_task(self._embed_pdb(tb))

    async def _embed_pdb(self, tb: Optional[TracebackType] = None) -> None:
        await self.query_one(Label).remove()
        self.widget = PDBWidget(tb)
        await self.mount(self.widget)
        self.focus()

    def embed_ipython(
        self, frame: Optional[FrameType] = None, module: Optional[ModuleType] = None
    ) -> None:
        asyncio.create_task(self._embed_ipython(frame, module))

    async def _embed_ipython(
        self, frame: Optional[FrameType] = None, module: Optional[ModuleType] = None
    ) -> None:
        await self.query_one(Label).remove()
        self.widget = IPythonWidget(frame, module)
        await self.mount(self.widget)
        self.focus()

    def on_key(self, event) -> None:
        if event.key == "ctrl+d":
            self.terminate()
        elif event.key == "escape":
            self.blur()
            self.styles.border = ("solid", "gray")
        else:
            self._handle_user_input(event)
        event.stop()

    def on_paste(self, event) -> None:
        if self.widget is not None:
            self.widget.send_user_input(event.text)
        event.stop()

    def _handle_user_input(self, event) -> None:
        if self.widget is None:
            return
        if event.is_printable:
            self.widget.send_user_input(event.character)
        elif event.key in ESCAPE_SEQUENCES:
            # Non printable characters: up/down arrows, etc. Is that handled by the
            # terminal emulator or by the program??
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
        if self.widget is None:
            return
        new_size = event.virtual_size
        child_fd = self.widget._child_fd
        if child_fd is None:
            return
        cols, rows = new_size.width, new_size.height

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(child_fd, termios.TIOCSWINSZ, winsize)
        self.widget._display.resize(rows, cols)
        print(f"New virtual size: {self.virtual_size}")
        self.refresh()

    def on_focus(self, event) -> None:
        self.styles.border = ("solid", "green")

    def terminate(self) -> None:
        if self.widget is None:
            return
        self.widget.terminate()
        self.widget.remove()
        if self.executable is not None:
            self.widget = BasicTerminalWidget(self.executable, self.args)
            self.mount(self.widget)
        else:
            self.widget = None
            self.mount(Label("Terminal not available for this frame."))
