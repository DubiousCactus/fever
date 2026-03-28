import asyncio
import fcntl
import logging
import math
import os
import pty
import struct
import termios
from collections import deque
from types import FrameType, ModuleType, TracebackType
from typing import Any, Callable, List, Optional

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


class HistoryScreen(pyte.Screen):
    """A :class:`~pyte.screens.Screen` subclass, which keeps track
    of screen history and allows pagination. This is not linux-specific,
    but still useful; see page 462 of VT520 User's Manual.

    :param int history: total number of history lines to keep; is split
                        between top and bottom queues.
    :param int ratio: defines how much lines to scroll on :meth:`next_page`
                      and :meth:`prev_page` calls.

    .. attribute:: history

       A pair of history queues for top and bottom margins accordingly;
       here's the overall screen structure::

            [ 1: .......]
            [ 2: .......]  <- top history
            [ 3: .......]
            ------------
            [ 4: .......]  s
            [ 5: .......]  c
            [ 6: .......]  r
            [ 7: .......]  e
            [ 8: .......]  e
            [ 9: .......]  n
            ------------
            [10: .......]
            [11: .......]  <- bottom history
            [12: .......]

    .. note::

       Don't forget to update :class:`~pyte.streams.Stream` class with
       appropriate escape sequences -- you can use any, since pagination
       protocol is not standardized, for example::

           Stream.escape["N"] = "next_page"
           Stream.escape["P"] = "prev_page"
    """

    _wrapped = set(pyte.Stream.events)
    _wrapped.update(["next_page", "prev_page"])

    def __init__(
        self, columns: int, lines: int, history: int = 100, ratio: float = 0.5
    ) -> None:
        self.history = pyte.History(
            deque(maxlen=history), deque(maxlen=history), float(ratio), history, history
        )

        super().__init__(columns, lines)

    def _make_wrapper(
        self, event: str, handler: Callable[..., Any]
    ) -> Callable[..., Any]:
        def inner(*args: Any, **kwargs: Any) -> Any:
            self.before_event(event)
            result = handler(*args, **kwargs)
            self.after_event(event)
            return result

        return inner

    def __getattribute__(self, attr: str) -> Callable[..., Any]:
        value = super().__getattribute__(attr)
        if attr in HistoryScreen._wrapped:
            return HistoryScreen._make_wrapper(self, attr, value)
        else:
            return value  # type: ignore[no-any-return]

    def before_event(self, event: str) -> None:
        """Ensure a screen is at the bottom of the history buffer.

        :param str event: event name, for example ``"linefeed"``.
        """
        if event not in ["prev_page", "next_page"]:
            while self.history.position < self.history.size:
                self.next_page()

    def after_event(self, event: str) -> None:
        """Ensure all lines on a screen have proper width (:attr:`columns`).

        Extra characters are truncated, missing characters are filled
        with whitespace.

        :param str event: event name, for example ``"linefeed"``.
        """
        if event in ["prev_page", "next_page"]:
            for line in self.buffer.values():
                for x in line:
                    if x > self.columns:
                        line.pop(x)

        # If we're at the bottom of the history buffer and `DECTCEM`
        # mode is set -- show the cursor.
        self.cursor.hidden = not (
            self.history.position == self.history.size
            and pyte.modes.DECTCEM in self.mode
        )

    def _reset_history(self) -> None:
        self.history.top.clear()
        self.history.bottom.clear()
        self.history = self.history._replace(position=self.history.size)

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

    def index(self) -> None:
        """Overloaded to update top history with the removed lines."""
        top, bottom = self.margins or pyte.Margins(0, self.lines - 1)

        if self.cursor.y == bottom:
            self.history.top.append(self.buffer[top])

        super().index()

    def reverse_index(self) -> None:
        """Overloaded to update bottom history with the removed lines."""
        top, bottom = self.margins or pyte.Margins(0, self.lines - 1)

        if self.cursor.y == top:
            self.history.bottom.append(self.buffer[bottom])

        super().reverse_index()

    def prev_page(self) -> None:
        """Move the screen page up through the history buffer. Page
        size is defined by ``history.ratio``, so for instance
        ``ratio = .5`` means that half the screen is restored from
        history on page switch.
        """
        if self.history.position > self.lines and self.history.top:
            mid = min(
                len(self.history.top), int(math.ceil(self.lines * self.history.ratio))
            )

            self.history.bottom.extendleft(
                self.buffer[y] for y in range(self.lines - 1, self.lines - mid - 1, -1)
            )
            self.history = self.history._replace(position=self.history.position - mid)

            for y in range(self.lines - 1, mid - 1, -1):
                self.buffer[y] = self.buffer[y - mid]
            for y in range(mid - 1, -1, -1):
                self.buffer[y] = self.history.top.pop()

            self.dirty = set(range(self.lines))

    def next_page(self) -> None:
        """Move the screen page down through the history buffer."""
        if self.history.position < self.history.size and self.history.bottom:
            mid = min(
                len(self.history.bottom),
                int(math.ceil(self.lines * self.history.ratio)),
            )

            self.history.top.extend(self.buffer[y] for y in range(mid))
            self.history = self.history._replace(position=self.history.position + mid)

            for y in range(self.lines - mid):
                self.buffer[y] = self.buffer[y + mid]
            for y in range(self.lines - mid, self.lines):
                self.buffer[y] = self.history.bottom.popleft()

            self.dirty = set(range(self.lines))


class RichPyteDisplay(pyte.Screen):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cursor_char = "_"
        self._history_len = 1000
        self.history = [] * args[1]
        self.head_pointer = 0
        self.n_rows_displayable = args[1]
        self.initialized = False
        self.parent = parent

    def resize(self, lines: int, columns: int):
        super().resize(lines, columns)
        self.n_rows_displayable = lines - 1
        if len(self.history) < lines:
            self.expand_columns((lines - len(self.history)))
        self.initialized = True

    async def blink(self, interval_sec: float):
        while True:
            await asyncio.sleep(interval_sec)
            self._cursor_char = " " if self._cursor_char == "_" else "_"

    @property
    def virtual_size(self) -> Size:
        return Size(self.columns, len(self.history))

    def expand_columns(self, extra_lines: int):
        self.history.extend([" " * self.columns] * extra_lines)
        self.parent.virtual_size = self.virtual_size

    # TODO: To enable scrolling, the simplest  way would be to obtain the raw buffer
    # with all history in side it. But does pyte provide that? If not, we need a
    # history buffer to be stored in here, and we need to fill it up with pyte's
    # buffer when necessary, and to draw that one instead of the current buffer.

    # There is a HistoryScreen from pyte, but it wouldn't allow smooth scrolling. So
    # I could have a history buffer that stores every line, and let the widget
    # handle scrolling. On render, we would render the entire history with
    # autoscroll to the bottom. We need to let pyte believe the size is the widget's
    # virtual size, but then we need to strip the buffer to update the history with
    # only new lines, no pading.
    # WARN: When the widget is resized, we actually tell the vterm and pyte's screen
    # that they have one more row than can be displayed. This allows us to detect
    # scrolling down, when the cursor.y is greater than the widget's actual size.
    # if len(self.dirty) > 0:
    #     # print("Updating history with dirty lines:", self.dirty)
    #     print(
    #         f"Cursor y: {self.cursor.y}, line pointer: {self.head_pointer}, displayable rows: {self.n_rows_displayable}"
    #     )
    #     if self.cursor.y > self.n_rows_displayable - 1:
    def render_line(self, y: int) -> Strip:
        # WARN: When the widget is resized, we actually tell the vterm and pyte's screen
        # that they have one more row than can be displayed. This allows us to detect
        # overflow, when the cursor.y is greater than the widget's actual size.
        if len(self.dirty) > 0:
            print(
                f"Cursor y: {self.cursor.y}, line pointer: {self.head_pointer}, displayable rows: {self.n_rows_displayable}"
            )
            if self.cursor.y > self.n_rows_displayable - 1:
                # INFO: We are overflowing! We need to increment the head pointer by the
                # difference between the cursor y and the displayable rows, to keep
                # track of where the buffer starts in the history buffer.
                self.head_pointer += self.cursor.y - (self.n_rows_displayable - 1)
                print(f"Overflow detected! New head pointer: {self.head_pointer}")
                self.expand_columns((self.cursor.y - (self.n_rows_displayable - 1)))
            # TODO: Use a diff display instead of copying the entire buffer into the
            # history buffer!
            for i, line in enumerate(self.display):
                self.history[self.head_pointer + i] = line
            self.dirty.clear()
        buffer = self.history
        # FIXME: The blinking cursor mechanic should be updated such that only the
        # returned Strip that corresponds to the cursor line is updated with the cursor
        # character, not the entire buffer.
        buffer[self.head_pointer + self.cursor.y] = (
            buffer[self.head_pointer + self.cursor.y][: self.cursor.x]
            + self._cursor_char
            + buffer[self.head_pointer + self.cursor.y][self.cursor.x + 1 :]
        )
        # TODO: Add style to the segment?
        return Strip([Segment(buffer[y])])


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
        _ = loop.create_task(self._refresh_display(0.016))
        _ = loop.create_task(self._display.blink(0.5))
        loop.add_reader(fd, self._read_ready)

    async def _refresh_display(self, interval_sec: float):
        # Refresh at ~60fps to ensure the display updates even if no new data is
        # received (e.g., for cursor blinking)
        while True:
            await asyncio.sleep(interval_sec)
            self.refresh()

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
        self.scroll_end(animate=False, immediate=True, x_axis=False)
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
        if y >= self._display.lines or not self._display.initialized:
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
        _ = loop.create_task(self._refresh_display(0.016))
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
        _ = loop.create_task(self._refresh_display(0.016))
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

        winsize = struct.pack("HHHH", rows + 1, cols, 0, 0)
        fcntl.ioctl(child_fd, termios.TIOCSWINSZ, winsize)
        self.widget._display.resize(rows + 1, cols)
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
