import asyncio
import fcntl
import logging
import os
import pty
import struct
import termios
from types import FrameType, ModuleType, TracebackType
from typing import List, Optional

import pyte
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label

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


class RichDisplay(pyte.Screen):
    def __rich_console__(self, console, options):
        buffer = self.display
        buffer[self.cursor.y] = (
            buffer[self.cursor.y][: self.cursor.x]
            + "_"
            + buffer[self.cursor.y][self.cursor.x + 1 :]
        )
        yield from buffer


class BasicTerminalWidget(Widget):
    def __init__(self, executable: Optional[str] = None, args: List[str] = []):
        super().__init__()
        self._display = RichDisplay(80, 24)
        self._out_stream = pyte.ByteStream(self._display)
        self.process_task = None
        self.has_sent = False
        self._child_pid, self._child_fd = None, None
        self.executable = executable
        self.args = args

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
            # IPython.embed()
            # ipshell = InteractiveShellEmbed(
            #     config=Config(),
            #     banner1="Dropping into IPython",
            #     exit_msg="Leaving Interpreter, back to program.",
            # )

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

            shell = IPython.terminal.embed.InteractiveShellEmbed()
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
        loop.add_reader(fd, self._read_ready)


class TerminalPanel(Vertical, can_focus=True):
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

    async def _embed_pdb(self, tb: Optional[TracebackType] = None) -> None:
        await self.query_one(Label).remove()
        self.widget = PDBWidget(tb)
        await self.mount(self.widget)
        self.focus()

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
        if self.widget is None:
            self.widget.send_user_input(event.text)
        event.stop()

    def _handle_user_input(self, event) -> None:
        if self.widget is None:
            return
        if event.is_printable:
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
        if self.widget is None:
            return
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
