import asyncio
import logging
import pickle
import runpy
import sys
import threading
from collections import namedtuple
from pathlib import Path
from traceback import StackSummary, format_exception_only, walk_stack
from types import FrameType
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Tuple,
)

from rich.console import RenderableType
from rich.pretty import Pretty
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import (
    Footer,
    Header,
    RichLog,
)

from fever.core import FeverCore
from fever.tui.widgets.call_graph import CallGraph
from fever.types import FeverEntryPoint

from .widgets.checkbox_panel import CheckboxPanel
from .widgets.files_tree import FilesTree
from .widgets.locals_panel import LocalsPanel
from .widgets.logger import Logger
from .widgets.tracer import Tracer

# logging.basicConfig(
#     level=logging.DEBUG,
#     handlers=[RichHandler()],
# )
#

logging.basicConfig(
    filename="fever_debug.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("fever")
log.debug("Engine initialized")

Node = namedtuple("Node", ["module", "name"])


class BuilderUI(App):
    TITLE = "Fever Builder TUI"
    CSS_PATH = "styles/builder_ui.css"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle dark mode"),
        ("r", "forward_reload", "Hot reload (thrown only)"),
        ("R", "reload", "Hot reload (all)"),
    ]

    def __init__(self, engine: FeverCore, script_path: str, trace_path: str):
        super().__init__()
        self._module_chain: List[FeverEntryPoint] = []
        self._runner_task = None
        self._engine = engine
        self._engine.set_on_new_call_callback(self.tracker_callback)
        self._engine.set_on_exception_callback(self.exception_callback)
        # sys.settrace(self.exception_callback(self._engine._call_tracker._resume_event))
        # INFO: Here's the plan: during watch phase we can export the call graph. During
        # debug phase, we hook up fever, import main script which will have a chain
        # reaction of monkey-patching every callable, then load the call graph. With the
        # call graph and recorded parameters, we can then re-run the exact same trace.
        # But we cache every result ofc. Then the user selects entry/exit nodes, and
        # the debugger can just rerun through the set circuit. Voila.
        self._script_path = script_path
        # FIXME: We seem to be dealing with the same issue of pickling arbitrary call
        # parameters. To go around this, we can skip them for now.
        self._call_graph = self._load_trace(trace_path)
        self._reload_on_throw_only = True  # NOTE: Leave this to true for the first run or it will attempt to reload on the first run, which is not really desireable
        self._entry_node, self._exit_node = (
            Node("footprinting", "compute_footprints_by_differentials_DEBUG"),
            Node("footprinting", "test"),
        )
        self._has_run = False
        log.debug(
            f"BuilderUI initialized with script_path={script_path} and trace_path={trace_path}"
        )

    def _load_trace(self, path: str):
        # NOTE: For now let's use pickle, but I'll use blosc2 for compression.
        with open(path, "rb") as f:
            return pickle.load(f)

    async def on_mount(self):
        # await self._chain_up()
        # self.run_chain()
        # runpy.run_path(self.script, run_name="__main__")
        pass

    # async def _chain_up(self) -> None:
    #     """
    #     Prepare the UI by adding checkboxes for each module in the chain.
    #     """
    #     keys = []
    #     for module in self._module_chain:
    #         if not isinstance(module, FeverEntryPoint):
    #             self.exit(1)
    #             raise TypeError(f"Expected FeverEntryPoint, got {type(module)}")
    #         await self.query_one(CheckboxPanel).add_checkbox(str(module), module.uid)
    #         if module.uid in keys:
    #             raise ValueError(f"Duplicate module '{module}' with uid {module.uid}")
    #         keys.append(module.uid)
    #     self.query_one(CheckboxPanel).ready()

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
        self.log_tracer("Running the chain...")
        log.debug("Starting to run the chain of modules...")
        if len(self._module_chain) == 0:
            self.log_tracer(Text("The chain is empty!", style="bold red"))
        self.log_tracer(Text(f"Running {self._script_path}...", style="yellow"))
        log.debug(f"Running script at path: {self._script_path}")
        # NOTE: The user script runs in a separate thread, allowing to keep the UI async
        # and responsive. But in addition, it allows us to use threading events to
        # coordinate hanging and resuming execution, which is neat.
        # the registry with those parameters.
        if not self._has_run:
            # NOTE: Compute a part of the path untll end node, and fill up the cache.
            self._has_run = True
            await asyncio.to_thread(
                runpy.run_path,
                self._script_path,
                run_name="__main__",
            )
        else:
            # NOTE: The cache should be filled up to end node, we can just call entry node
            # with cached parameters, and it will run through to end node.
            self.log_tracer(
                f"Second run: running with cached results from {self._entry_node} to {self._exit_node}..."
            )
            params = await asyncio.to_thread(
                self._engine.get_cached_params,
                self._entry_node.module,
                self._entry_node.name,
            )
            # Use the first cached params for now, ignore the caller:
            params = params[0][1]
            await asyncio.to_thread(
                self._engine.registry.invoke,
                self._entry_node.module,
                self._entry_node.name,
                params,
            )
        log.debug("Script run completed.")

        # for module in self._module_chain:
        #     await self.query_one(LocalsPanel).clear()
        #     self.query_one(Tracer).clear()
        #     if module.is_frozen:
        #         self.log_tracer(Text(f"Skipping frozen module {module}", style="green"))
        #         continue
        #     if module.to_reload or not self._reload_on_throw_only:
        #         self.log_tracer(Text(f"Reloading module: {module}", style="yellow"))
        #         await self._engine.reload_module(module)
        #     self.log_tracer(Text(f"Running module: {module}", style="yellow"))
        #     module.result = await self._engine.catch_and_hang(
        #         module, self._module_chain
        #     )
        #     self.log_tracer(Text(f"{module} ran sucessfully!", style="bold green"))
        #     self.print_info("Hanged.")
        #     self.query_one("#traceback", RichLog).clear()
        #     await self.hang(threw=False)

    def run_chain(self) -> None:
        """
        Run the chain of modules in a separate task. If a task is already running,
        cancel it first. This can happen if the user triggers a reload while the chain
        has hung.
        """
        if self._runner_task is not None:
            self._runner_task.cancel()
            self._runner_task = None
        self._runner_task = asyncio.create_task(self._run_chain(), name="run_chain")

    def compose(self) -> ComposeResult:
        yield Header()
        checkboxes = CheckboxPanel(classes="box")
        checkboxes.loading = True
        yield checkboxes
        yield CallGraph(self._call_graph, classes="box", id="graph")
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

    def tracker_callback(
        self, resume_event: threading.Event, k: object, v: object
    ) -> None:
        sys.settrace(None)
        self.log_tracer(f"CALL: {k} -> {v}")
        log.debug(f"Tracker callback called with k={k}, v={v}")
        if v == self._exit_node.name:
            self.log_tracer(f"Hanging on {v}...")
            resume_event.wait()
            # self.query_one(CallGraph).highlight(v)
            # self.hang(False)

    def exception_callback(
        self, resume_event: threading.Event
    ) -> Callable[[FrameType, str, Any], Any]:
        def handler(
            frame: FrameType, event: str, arg: Any
        ) -> Callable[[FrameType, str, Any], Any]:
            if event == "exception":
                try:
                    fpath = Path(frame.f_code.co_filename).relative_to(Path.cwd())
                except Exception:
                    try:
                        fpath = Path(frame.f_code.co_filename).relative_to(
                            Path.cwd(), walk_up=True
                        )
                    except Exception:
                        fpath = Path(frame.f_code.co_filename)
                exception: Exception = Exception()
                exception, value, tb = arg
                frames = []
                f = frame
                while f:
                    frames.append(f)
                    f = f.f_back
                log.debug(
                    f"Exception callback called with exception: {exception}. Value: {value}"
                )
                stack = StackSummary.extract(walk_stack(frame))
                formatted = "".join(reversed(stack.format()))

                self.log_tracer(
                    Text(
                        "".join(format_exception_only(exception, value)).strip()
                        + f" (<-- {fpath}@L{frame.f_lineno})",
                        style="bold red",
                    )
                )
                self.query_one("#traceback", RichLog).write(formatted)
                self.hang(True)
                resume_event.wait()
                return handler
            return handler

        # self.query_one("#traceback", RichLog).write_exception(exception)
        return handler

    def _reload(self) -> None:
        self.query_one(Tracer).clear()
        self.log_tracer("Reloading hot code...")
        self.query_one(CheckboxPanel).ready()
        self.query_one(Tracer).ready()
        self.query_one("#traceback", RichLog).clear()
        self.run_chain()

    def action_reload(self) -> None:
        self._reload_on_throw_only = False
        self._reload()

    def action_forward_reload(self) -> None:
        self._reload_on_throw_only = True
        self._reload()

    # def on_checkbox_changed(self, message: Checkbox.Changed):
    #     assert message.checkbox.id is not None
    #     for module in self._module_chain:
    #         if module.uid == message.checkbox.id:
    #             module.is_frozen = bool(message.value)

    def set_start_epoch(self, *args, **kwargs):
        _ = args
        _ = kwargs
        pass

    def track_training(self, iterable, total: int) -> Tuple[Iterable, Callable]:
        _ = total

        def noop(*args, **kwargs):
            _ = args
            _ = kwargs
            pass

        return iterable, noop

    def track_validation(self, iterable, total: int) -> Tuple[Iterable, Callable]:
        _ = total

        def noop(*args, **kwargs):
            _ = args
            _ = kwargs
            pass

        return iterable, noop

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
