import asyncio
import logging
import runpy
import sys
from pathlib import Path
from traceback import StackSummary, format_exception_only, walk_tb
from types import FrameType, TracebackType
from typing import (
    Any,
    Dict,
    Optional,
    Tuple,
)

from rich.console import RenderableType
from rich.pretty import Pretty
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    RichLog,
    Select,
    TabbedContent,
    TabPane,
)

from fever.core import FeverCore
from fever.tui.widgets.call_graph import CallGraph
from fever.tui.widgets.nodes_panel import TraceNodesPanel
from fever.tui.widgets.terminal_panel import TerminalPanel
from fever.types import TraceNode

from .widgets.function_stats import FunctionStatsPanel
from .widgets.locals_panel import LocalsPanel
from .widgets.logger import Logger
from .widgets.tracer import Tracer
from .widgets.welcome_modal import WelcomeModal, should_show_welcome

logging.basicConfig(
    filename="fever_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("fever")
log.debug("Engine initialized")


def _catch_exceptions_in_thread(
    func, *args, **kwargs
) -> Tuple[Optional[Exception | SystemExit], Optional[Any]]:
    try:
        result = func(*args, **kwargs)
    except Exception as e:
        return e, None
    except SystemExit as e:
        return e, None
    return None, result


class TraceReplayUI(App):
    TITLE = "Fever Trace Replayer"
    CSS_PATH = "styles/ui.css"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle dark mode"),
        ("r", "replay", "Replay trace"),
    ]

    def __init__(self, engine: FeverCore, script_path: str):
        super().__init__()
        self._runner_task = None
        self._engine = engine
        self._engine.set_on_new_call_callback(self.tracker_callback)
        self._engine.set_on_exception_callback(self.exception_callback)
        self._script_path = script_path
        self._start_node, self._end_node = None, None
        self._has_run = False
        self._user_task: Optional[asyncio.Task] = None
        log.debug(f"TraceDebugger initialized with script_path={script_path}")

    async def _run_trace_threaded(self) -> None:
        """
        Run the execution trace from start to end node, with Fever hot reloading. For
        each node, run it and catch exceptions, hanging the UI if an exception is
        thrown. If no exception is thrown at the end of the trace, hang the UI to
        indicate success. When a module throws, the UI should hang and display the
        traceback in the traceback panel. The user can then fix the code and reload the
        trace.
        """
        await self.query_one(LocalsPanel).clear()
        log.debug("Starting to run the chain of modules...")
        self._engine._call_tracker.stop_event.clear()
        self.log_tracer(Text(f"Running {self._script_path}...", style="yellow"))
        log.debug(f"Running script at path: {self._script_path}")
        # NOTE: The user script runs in a separate thread, allowing to keep the UI async
        # and responsive. But in addition, it allows us to use threading events to
        # coordinate hanging and resuming execution, which is neat.
        # the registry with those parameters.
        if not self._has_run:
            # NOTE: We can't hang on end node on first run, otherwise we won't
            # collect the full graph and we can't hang on re-run. So here we compute the
            # entire call graph lazily and fill up the cache.
            self._user_task = asyncio.create_task(
                asyncio.to_thread(
                    _catch_exceptions_in_thread,
                    runpy.run_path,
                    self._script_path,
                    run_name="__main__",
                )
            )
            exception, _ = await self._user_task
            if exception is not None and isinstance(exception, Exception):
                log.debug(f"Script raised an exception: {exception}")
                self.exception_callback(exception)
                return
            elif exception is None or isinstance(exception, SystemExit):
                log.debug(
                    f"Script called sys.exit() with code {exception}, treating as normal termination."
                )
                self.log_tracer(
                    Text(f"Script exited with code {exception}.", style="green")
                )
                self._has_run = True
                graph = self._engine._call_tracker.single_edge_call_graph
                self.query_one(TraceNodesPanel).set_call_graph(graph)
                await self.query_one(CallGraph).set_call_graph(graph)
        else:
            # NOTE: The cache should be filled up to end node, we can just call start node
            # with cached parameters, and it will run through to end node.
            self._start_node, self._end_node = self.query_one(
                TraceNodesPanel
            ).trace_nodes
            if self._start_node is Select.BLANK or self._end_node is Select.BLANK:
                self.log_tracer(
                    Text(
                        "Please select start and end nodes from the dropdowns above.",
                        style="bold red",
                    )
                )
                return
            self.log_tracer(
                f"Second run: running with cached results from {self._start_node} to {self._end_node}..."
            )
            self._user_task = asyncio.create_task(
                asyncio.to_thread(
                    _catch_exceptions_in_thread,
                    self._engine.get_cached_params,
                    self._start_node.module,
                    self._start_node.func,
                )
            )
            exception, params = await self._user_task
            if exception is not None and isinstance(exception, Exception):
                self.exception_callback(exception)
            # TODO: Allow user to select the parameters from the trace
            # Use the first cached params for now, ignore the caller:
            if len(params) == 0:
                self.log_tracer(
                    Text(
                        "No cached parameters found for the selected start node.",
                        style="bold red",
                    )
                )
                return
            params = params[0][1]
            self._user_task = asyncio.create_task(
                asyncio.to_thread(
                    _catch_exceptions_in_thread,
                    self._engine.registry.invoke_wrapped,
                    self._start_node.module,
                    self._start_node.func,
                    params,
                )
            )
            exception, _ = await self._user_task
            if exception is not None and isinstance(exception, Exception):
                self.exception_callback(exception)
            # NOTE: Thread termination is now handled by stop_event checks in call_tracker
        log.debug("Script run completed.")
        self.hang(False)

    def _start_runner(self):
        if self._runner_task is not None:
            self._runner_task.cancel()
            self._runner_task = None

        self._runner_task = asyncio.create_task(
            self._run_trace_threaded(),
            name="run_chain",
        )

    async def _wait_cancel_then_start(self) -> None:
        while self._engine._call_tracker.stop_event.is_set():
            # Wait for the user task to acknowledge the stop request by clearing the stop event
            await asyncio.sleep(0.1)
        if self._user_task and not self._user_task.done():
            self._user_task.cancel()
        self._start_runner()

    def run_trace(self) -> None:
        """
        Run the trace from start node to end node in a separate task. If a task is already running,
        cancel it first. This can happen if the user triggers a reload while the chain
        has hung.
        """
        if self._user_task and not self._user_task.done():
            # Signal the user thread to stop
            self._engine._call_tracker.stop_event.set()
            # Unblock any waiting threads
            self._engine._call_tracker.resume_event.set()
            log.debug("Stop and resume events set, cancelling user task...")
            # Now we must wait for the rendez-vous! Because the task is being resumed
            # and it must reach the stop event on the next wrapper call
            asyncio.create_task(self._wait_cancel_then_start())
        else:
            self._start_runner()

    def on_mount(self):
        if should_show_welcome():
            self.push_screen(WelcomeModal())
        self.run_trace()

    async def action_quit(self) -> None:
        log.debug(
            "Quitting application, cancelling runner task and user task if they exist..."
        )
        if self._user_task and not self._user_task.done():
            # Signal the user thread to stop
            self._engine._call_tracker.stop_event.set()
            # Unblock any waiting threads
            self._engine._call_tracker.resume_event.set()
            log.debug("Stop and resume events set to terminate user task")
            while self._engine._call_tracker.stop_event.is_set():
                # Wait for the user task to acknowledge the stop request by clearing the stop event
                await asyncio.sleep(0.1)
            # Cancel the task
            self._user_task.cancel()
            # Wait briefly for graceful termination, then force if needed
            try:
                await asyncio.wait_for(self._user_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                log.debug("User task cancelled or timed out")
        if self._runner_task is not None:
            self._runner_task.cancel()
            self._runner_task = None
            log.debug("Runner task cancelled.")
        self.app.exit()

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="tab-graph", id="tracer-tabs"):
            with TabPane("Trace Graph", id="tab-graph"):
                with Vertical(id="left-panel"):
                    yield TraceNodesPanel(classes="box", id="nodes_panel")
                    yield FunctionStatsPanel(id="func_stats")
                    yield Button(
                        "▶ Play",
                        id="play_btn",
                        variant="success",
                    )
                yield CallGraph(classes="box", id="graph")
            with TabPane("Logs & Execution", id="tab-logs"):
                fever_logs = RichLog(
                    classes="box",
                    id="fever_logs",
                    highlight=True,
                    markup=True,
                    wrap=True,
                )
                fever_logs.border_title = "Fever logs"
                fever_logs.styles.border = ("solid", "gray")
                yield fever_logs

                logs = Logger(classes="box", id="logger")
                logs.border_title = "User logs"
                logs.styles.border = ("solid", "gray")
                yield logs

                traceback = RichLog(
                    classes="box",
                    id="traceback",
                    highlight=True,
                    markup=True,
                    wrap=False,
                )
                traceback.border_title = "Exception traceback"
                traceback.styles.border = ("solid", "gray")
                yield traceback

                lcls = LocalsPanel(classes="box", id="lcls")
                lcls.styles.border = ("solid", "gray")
                yield lcls

                with TabbedContent(initial="tab-tracer", id="sub-tracer-tabs"):
                    with TabPane("Tracer logs", id="tab-tracer"):
                        yield Tracer(classes="box", id="tracer")
                    with TabPane("Debugger", id="tab-debugger"):
                        yield TerminalPanel("Debugger (PDB++)", id="debugger_panel")
                    with TabPane("IPython", id="tab-terminal"):
                        yield TerminalPanel("IPython", id="terminal_panel")

        yield Footer()

    def tracker_callback(
        self, k: TraceNode, v: TraceNode, frame: FrameType, module_name: str
    ) -> None:
        try:
            self.log_tracer(f"CALL: {k} -> {v}")
        except Exception:
            self.log_tracer(f"CALL: {k.module}.{k.func} -> {v.module}{v.func}")
        log.debug(f"Tracker callback called with k={k}, v={v}")
        if not self._has_run:
            # self.query_one("#graph", CallGraph).update(k, v)
            self.hang(False)
            return
        assert self._end_node is not None, (
            "End node should not be None when tracker callback is called after the first run."
        )
        if v.equals_ignore_params(self._end_node):
            self.log_tracer(f"Hanging on {v.module}.{v.func}...")
            self.call_from_thread(self.set_locals, frame.f_locals, frame.f_code.co_name)
            self.hang(False, frame=frame, module_name=module_name)
            while True:
                if self._engine._call_tracker.stop_event.is_set():
                    self._engine._call_tracker.stop_event.clear()  # This will signal the TUI that we have acknowledged the stop request
                    log.debug("Stop event detected in tracker callback, exiting")
                    raise SystemExit("Thread termination requested")
                self._engine._call_tracker.resume_event.wait(timeout=0.1)

    def exception_callback(self, exception: Exception) -> None:
        if exception.__traceback__ is None:
            # INFO: Simple exception most likley raised by Fever
            self.log_tracer(
                Text(
                    "FeverError: ",
                    str(exception),
                    style="bold red",
                )
            )
            formatted = "No traceback available."
            tb = None
        else:
            tb = exception.__traceback__.tb_next
            if tb is None:
                fpath = "?"
                lineno = "?"
                formatted = "Could not find traceback."
            else:
                frame = tb.tb_frame
                lineno = tb.tb_lineno
                try:
                    fpath = Path(frame.f_code.co_filename).relative_to(Path.cwd())
                except Exception:
                    try:
                        fpath = Path(frame.f_code.co_filename).relative_to(
                            Path.cwd(), walk_up=True
                        )
                    except Exception:
                        try:
                            fpath = Path(frame.f_code.co_filename)
                        except Exception:
                            fpath = "?"
                try:
                    stack = StackSummary.extract(walk_tb(tb))
                    formatted = "".join(reversed(stack.format()))
                except Exception:
                    formatted = "Could not format stack trace."

                # Call the async set_locals method from the worker thread.
                # We use call_from_thread to ensure it runs on the main event loop.
                # FIXME: breaks when it's a FeverRegistryException (why?)
                self.call_from_thread(
                    self.set_locals, frame.f_locals, frame.f_code.co_name
                )
            self.log_tracer(
                Text(
                    "".join(format_exception_only(exception)).strip()
                    + f" (<-- {fpath}@L{lineno})",
                    style="bold red",
                )
            )
        self.query_one("#traceback", RichLog).write(formatted)
        self.hang(True, tb=tb)

    async def action_replay(self) -> None:
        self.query_one(Tracer).clear()
        self.query_one(Logger).clear()
        self.query_one("#debugger_panel", TerminalPanel).terminate()
        self.query_one("#fever_logs", RichLog).clear()
        self.query_one("#traceback", RichLog).clear()
        self.query_one(Tracer).ready()
        tabs = self.query_one("#tracer-tabs", TabbedContent)
        tabs.active = "tab-logs"
        tabs = self.query_one("#sub-tracer-tabs", TabbedContent)
        tabs.active = "tab-tracer"
        self.run_trace()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "play_btn":
            await self.action_replay()

    def log_tracer(self, message: str | RenderableType) -> None:
        if self.is_mounted:
            try:
                self.query_one(Tracer).write(message)
            except Exception:
                pass

    def log_fever_event(self, message: str, style: str = "bold magenta") -> None:
        if self.is_mounted:
            try:
                self.query_one("#fever_logs", RichLog).write(Text(message, style=style))
            except Exception:
                pass
        log.debug(f"Fever event: {message}")

    async def set_locals(self, locals: Dict[str, Any], frame_name: str) -> None:
        panel = self.query_one(LocalsPanel)
        panel.set_frame_name(frame_name)
        await panel.add_locals(locals)

    def hang(
        self,
        threw: bool,
        tb: Optional[TracebackType] = None,
        frame: Optional[FrameType] = None,
        module_name: Optional[str] = None,
    ) -> None:
        """
        Give visual signal that the builder is hung, either due to an exception or
        because the function ran successfully.
        """
        if self.is_mounted:
            try:
                self.query_one(Tracer).hang(threw)
                self.query_one(TraceNodesPanel).hang(threw)
                # self.query_one(CallGraph).hang(threw)
                if tb is not None:
                    debug_panel = self.query_one("#debugger_panel", TerminalPanel)
                    self.call_from_thread(debug_panel.embed_pdb, tb)
                elif frame is not None:
                    terminal_panel = self.query_one("#terminal_panel", TerminalPanel)
                    self.call_from_thread(
                        terminal_panel.embed_ipython,
                        frame,
                        sys.modules.get(module_name) if module_name else None,
                    )
            except Exception:
                pass

    def print_err(self, msg: str | Exception) -> None:
        self.log_tracer(
            Text("[!] " + msg, style="bold red")
            if isinstance(msg, str)
            else Pretty(msg)
        )

    def print_warn(self, msg: str) -> None:
        self.log_tracer(Text("[!] " + msg, style="bold yellow"))

    def print_info(self, msg: str) -> None:
        self.log_tracer(Text(msg, style="bold blue"))

    def print_pretty(self, msg: Any) -> None:
        self.log_tracer(Pretty(msg))
