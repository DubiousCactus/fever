import asyncio
import os
import pty

import pyte
from textual.containers import Vertical
from textual.widget import Widget


class PDBDisplay(pyte.Screen):
    def __init__(self, width, height):
        super().__init__(width, height)

    def __rich_console__(self, console, options):
        yield from self.display


class PDBWidget(Widget):
    """Simple widget to display PDB content."""

    def __init__(self):
        super().__init__()
        self._display = PDBDisplay(width=80, height=24)
        self._out_stream = pyte.ByteStream(self._display)
        self.process_task = None
        self._ctrld_flag = False
        self.has_sent = False
        self._child_pid, self._child_fd = None, None

    def on_mount(self) -> None:
        asyncio.create_task(self._spawn_process_in_thread())

    async def _spawn_process_in_thread(self):
        self.process_task = asyncio.create_task(
            asyncio.to_thread(self._fork_process_in_tty)
        )
        await self.process_task

    def _fork_process_in_tty(self):
        child_pid, child_fd = pty.fork()
        if child_pid == 0:
            # In child process: execute PDB++
            # os.execvp("python", ["python", "-m", "pdbpp"])
            os.execvp("python3", ["python3", "-i"])
        else:
            self._child_pid, self._child_fd = child_pid, child_fd
            while True:
                try:
                    self._read_pdb_output(child_fd)
                    self._send_pdb_input(child_fd)
                except OSError:
                    break
                if self._ctrld_flag:
                    break

    def render(self):
        return self._display

    def terminate(self) -> None:
        self._ctrld_flag = True
        if self._child_fd:
            try:
                os.close(self._child_fd)  # Close the file descriptor to signal EOF
            except OSError:
                pass
        if self._child_pid:
            try:
                os.kill(self._child_pid, 9)  # Force kill the child process
            except ProcessLookupError:
                pass

        if self.process_task and not self.process_task.done():
            self.process_task.cancel()

    def _prompt_visible(self):
        for line in self._display.display:
            if line.rstrip().endswith(">>>"):
                return True
        return False

    def _read_pdb_output(self, fd) -> None:
        data = os.read(fd, 1024)
        if not data:
            return
        self._out_stream.feed(data)
        self.refresh()

    def _send_pdb_input(self, fd) -> None:
        if self._ctrld_flag:
            os.write(fd, b"\x04")  # Ctrl+D to signal EOF
        elif not self.has_sent and self._prompt_visible():
            os.write(fd, b'print("hello, world!")\n')
            self.has_sent = True


class PDBPanel(Vertical):
    """Container for the Debugger interface."""

    def compose(self):
        yield PDBWidget()

    def on_mount(self) -> None:
        self.border_title = "Debugger (PDB++)"

    def terminate(self) -> None:
        widget = self.query_one(PDBWidget)
        widget.terminate()
