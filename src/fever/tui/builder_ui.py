import asyncio
import logging
import pickle
import runpy
from pathlib import Path
from traceback import StackSummary, format_exception_only, walk_tb
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
from textual.widgets import Footer, Header, RichLog, Select

from fever.core import FeverCore
from fever.tui.widgets.call_graph import CallGraph
from fever.tui.widgets.nodes_panel import TraceNodesPanel
from fever.types import TraceNode

from .widgets.files_tree import FilesTree
from .widgets.locals_panel import LocalsPanel
from .widgets.logger import Logger
from .widgets.tracer import Tracer

logging.basicConfig(
    filename="fever_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("fever")
log.debug("Engine initialized")


def _run_user_script(path: str) -> Tuple[str, Optional[Exception | Any]]:
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as e:
        return ("exit", e.code)
    except Exception as e:
        return ("error", e)
    return ("ok", None)


def _run_thread(func, *args, **kwargs) -> Tuple[Optional[Exception], Optional[Any]]:
    try:
        result = func(*args, **kwargs)
    except Exception as e:
        return e, None
    return None, result


class BuilderUI(App):
    TITLE = "Fever Builder TUI"
    CSS_PATH = "styles/builder_ui.css"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle dark mode"),
        ("r", "forward_reload", "Hot reload (thrown only)"),
        ("R", "reload", "Hot reload (all)"),
    ]

    def __init__(self, engine: FeverCore, script_path: str):
        super().__init__()
        self._runner_task = None
        self._engine = engine
        self._engine.set_on_new_call_callback(self.tracker_callback)
        self._engine.set_on_exception_callback(self.exception_callback)
        # INFO: Here's the plan: during watch phase we can export the call graph. During
        # debug phase, we hook up fever, import main script which will have a chain
        # reaction of monkey-patching every callable, then load the call graph. With the
        # call graph and recorded parameters, we can then re-run the exact same trace.
        # But we cache every result ofc. Then the user selects start/end nodes, and
        # the debugger can just rerun through the set circuit. Voila.
        self._script_path = script_path
        # FIXME: We seem to be dealing with the same issue of pickling arbitrary call
        # parameters. To go around this, we can skip them for now.
        self._reload_on_throw_only = True  # NOTE: Leave this to true for the first run or it will attempt to reload on the first run, which is not really desireable
        self._start_node, self._end_node = None, None
        self._has_run = False
        self._user_task: Optional[asyncio.Task] = None
        log.debug(f"BuilderUI initialized with script_path={script_path}")

    def _load_trace(self, path: str):
        # NOTE: For now let's use pickle, but I'll use blosc2 for compression.
        with open(path, "rb") as f:
            return pickle.load(f)

    async def _run_chain(self) -> None:
        """
        Run the chain of modules, reloading them if necessary. For each module, run it
        and catch exceptions, hanging the UI if an exception is thrown. If no exception
        is thrown, hang the UI to indicate success and cache the result such that the
        module can be frozen by the user. If a module is frozen, retrieve its cached
        result and skip execution. Since a module's input may depend on the output of
        previous modules, if a module is frozen, ensure that all previous modules are
        also frozen and their outputs are cached.
        When a module throws, the UI should hang and display the traceback in the
        traceback panel. The user can then fix the code and reload the chain, which
        marks the current module for reloading. When we run the chain again, marked
        modules will be reloaded and re-executed.
        """
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
                    _run_user_script,
                    self._script_path,
                )
            )
            status, exception = await self._user_task
            if status == "error":
                log.debug(f"Script raised an exception: {exception}")
                self.exception_callback(exception)
                return
            elif status == "exit":
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
                return
            # FIXME: How do we kill the thread upon exit or quick rerun?
        else:
            # NOTE: The cache should be filled up to end node, we can just call start node
            # with cached parameters, and it will run through to end node.
            self.log_tracer(
                f"Second run: running with cached results from {self._start_node} to {self._end_node}..."
            )
            self._start_node, self._end_node = self.query_one(
                TraceNodesPanel
            ).trace_nodes
            if self._start_node is None or self._end_node is None:
                self.log_tracer(
                    Text(
                        "Please select start and end nodes from the dropdowns above.",
                        style="bold red",
                    )
                )
                return
            self._user_task = asyncio.create_task(
                asyncio.to_thread(
                    _run_thread,
                    self._engine.get_cached_params,
                    self._start_node.module,
                    self._start_node.func,
                )
            )
            exception, params = await self._user_task
            if exception is not None:
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
                    _run_thread,
                    self._engine.registry.invoke_wrapped,
                    self._start_node.module,
                    self._start_node.func,
                    params,
                )
            )
            exception, _ = await self._user_task
            if exception is not None:
                self.exception_callback(exception)
            # FIXME: How do we kill the thread upon exit or quick rerun?
        log.debug("Script run completed.")

    def run_chain(self) -> None:
        """
        Run the chain of modules in a separate task. If a task is already running,
        cancel it first. This can happen if the user triggers a reload while the chain
        has hung.
        """
        if self._user_task:
            self._engine._call_tracker.resume_event.clear()
            self._engine._call_tracker.stop_event.set()
            log.debug("User task cancelled.")
            self._user_task.cancel()
        if self._runner_task is not None:
            self._runner_task.cancel()
            self._runner_task = None
        self._runner_task = asyncio.create_task(self._run_chain(), name="run_chain")

    async def action_quit(self) -> None:
        log.debug(
            "Quitting application, cancelling runner task and user task if they exist..."
        )
        if self._user_task:
            self._engine._call_tracker.resume_event.clear()
            self._engine._call_tracker.stop_event.set()
            log.debug("User task cancelled.")
            await self._user_task
            self._user_task.cancel()
        if self._runner_task is not None:
            self._runner_task.cancel()
            self._runner_task = None
            log.debug("Runner task cancelled.")
        self.app.exit()

    def compose(self) -> ComposeResult:
        yield Header()
        yield TraceNodesPanel(classes="box", id="trace_nodes")
        yield CallGraph(classes="box", id="graph")
        logs = Logger(classes="box", id="logger")
        logs.border_title = "User logs"
        logs.styles.border = ("solid", "gray")
        yield logs
        ftree = FilesTree(classes="box")
        ftree.border_title = "Project tree"
        ftree.styles.border = ("solid", "gray")
        yield ftree
        lcls = LocalsPanel(classes="box")
        lcls.styles.border = ("solid", "gray")
        yield lcls
        yield Tracer(classes="box")
        traceback = RichLog(
            classes="box", id="traceback", highlight=True, markup=True, wrap=False
        )
        traceback.border_title = "Exception traceback"
        traceback.styles.border = ("solid", "gray")
        yield traceback
        yield Footer()

    def tracker_callback(self, k: TraceNode, v: TraceNode) -> None:
        try:
            self.log_tracer(f"CALL: {k} -> {v}")
        except Exception:
            self.log_tracer(f"CALL: {k.module}.{k.func} -> {v.module}{v.func}")
        log.debug(f"Tracker callback called with k={k}, v={v}")
        if not self._has_run:
            return
        assert self._end_node is not None, (
            "End node should not be None when tracker callback is called after the first run."
        )
        if v.equals_ignore_params(self._end_node):
            self.log_tracer(f"Hanging on {v.module}.{v.func}...")
            self._engine._call_tracker.resume_event.wait()
            self.hang(False)

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

            self.log_tracer(
                Text(
                    "".join(format_exception_only(exception)).strip()
                    + f" (<-- {fpath}@L{lineno})",
                    style="bold red",
                )
            )
        self.query_one("#traceback", RichLog).write(formatted)
        self.hang(True)

    def _reload(self) -> None:
        self.query_one(Tracer).clear()
        self.log_tracer("Reloading hot code...")
        self.query_one(Tracer).ready()
        self.query_one("#traceback", RichLog).clear()
        self.run_chain()

    def action_reload(self) -> None:
        self._reload_on_throw_only = False
        self._reload()

    def action_forward_reload(self) -> None:
        self._reload_on_throw_only = True
        self._reload()

    def on_select_changed(self, event: Select.Changed):
        if event.select.id == "start_node":
            self._start_node, self._end_node = None, None
        if event.select.id == "end_node":
            self._start_node, self._end_node = self.query_one(
                TraceNodesPanel
            ).trace_nodes
            log.debug(
                f"Select changed: start_node={self._start_node}, end_node={self._end_node}"
            )

    def log_tracer(self, message: str | RenderableType) -> None:
        self.query_one(Tracer).write(message)

    async def set_locals(self, locals: Dict[str, Any], frame_name: str) -> None:
        self.query_one(LocalsPanel).set_frame_name(frame_name)
        await self.query_one(LocalsPanel).add_locals(locals)

    def hang(self, threw: bool) -> None:
        """
        Give visual signal that the builder is hung, either due to an exception or
        because the function ran successfully.
        """
        self.query_one(Tracer).hang(threw)
        # self.query_one(CallGraph).hang(threw)

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
