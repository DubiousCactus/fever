import asyncio
import pickle
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Tuple,
)

from rich.console import RenderableType
from rich.pretty import Pretty
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import (
    Checkbox,
    Footer,
    Header,
    RichLog,
)

from fever.core import FeverCore
from fever.tui.widgets.call_graph import CallGraph
from fever.types import FeverEntryPoint

from .widgets.checkbox_panel import CheckboxPanel
from .widgets.editor import CodeEditor
from .widgets.files_tree import FilesTree
from .widgets.locals_panel import LocalsPanel
from .widgets.logger import Logger
from .widgets.tracer import Tracer


class BuilderUI(App):
    TITLE = "Fever Builder TUI"
    CSS_PATH = "styles/builder_ui.css"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle dark mode"),
        ("r", "forward_reload", "Hot reload (thrown only)"),
        ("R", "reload", "Hot reload (all)"),
    ]

    def __init__(self, engine: FeverCore, trace_path: str):
        super().__init__()
        # self._module_chain: List[FeverEntryPoint] = chain
        self._runner_task = None
        self._engine = engine
        self._engine.set_on_new_call_callback(self.update_call_graph)
        # INFO: Here's the plan: during watch phase we can export the call graph. During
        # debug phase, we hook up fever, import main script which will have a chain
        # reaction of monkey-patching every callable, then load the call graph. With the
        # call graph and recorded parameters, we can then re-run the exact same trace.
        # But we cache every result ofc. Then the user selects entry/exit nodes, and
        # the debugger can just rerun through the set circuit. Voila.
        # FIXME: We seem to be dealing with the same issue of pickling arbitrary call
        # parameters. To go around this, we can skip them for now.
        self._call_graph = self._load_trace(trace_path)
        self._reload_on_throw_only = True  # NOTE: Leave this to true for the first run or it will attempt to reload on the first run, which is not really desireable

    def _load_trace(self, path: str):
        # NOTE: For now let's use pickle, but I'll use blosc2 for compression.
        with open(path, "rb") as f:
            return pickle.load(f)

    async def on_mount(self):
        # await self._chain_up()
        # self.run_chain()
        # runpy.run_path(self.script, run_name="__main__")
        pass

    async def _chain_up(self) -> None:
        """
        Prepare the UI by adding checkboxes for each module in the chain.
        """
        keys = []
        for module in self._module_chain:
            if not isinstance(module, FeverEntryPoint):
                self.exit(1)
                raise TypeError(f"Expected FeverEntryPoint, got {type(module)}")
            await self.query_one(CheckboxPanel).add_checkbox(str(module), module.uid)
            if module.uid in keys:
                raise ValueError(f"Duplicate module '{module}' with uid {module.uid}")
            keys.append(module.uid)
        self.query_one(CheckboxPanel).ready()

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
        if len(self._module_chain) == 0:
            self.log_tracer(Text("The chain is empty!", style="bold red"))
        # TODO: Figure out how to call functions from the call graph! Right now they are
        # just text :( We probably need to also know which module they're from!
        #
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

    def update_call_graph(self, k: object, v: object) -> None:
        self.query_one(CallGraph).update(k, v)

    def _reload(self) -> None:
        self.query_one(Tracer).clear()
        self.log_tracer("Reloading hot code...")
        self.query_one(CheckboxPanel).ready()
        self.query_one(Tracer).ready()
        # self.query_one(CheckboxPanel).hang(threw)
        # self.query_one(CodeEditor).ready()
        self.run_chain()

    def action_reload(self) -> None:
        self._reload_on_throw_only = False
        self._reload()

    def action_forward_reload(self) -> None:
        self._reload_on_throw_only = True
        self._reload()

    def on_checkbox_changed(self, message: Checkbox.Changed):
        assert message.checkbox.id is not None
        for module in self._module_chain:
            if module.uid == message.checkbox.id:
                module.is_frozen = bool(message.value)

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

    async def hang(self, threw: bool) -> None:
        """
        Give visual signal that the builder is hung, either due to an exception or
        because the function ran successfully.
        """
        self.query_one(Tracer).hang(threw)
        self.query_one(CodeEditor).hang(threw)
        while self.is_running:
            await asyncio.sleep(1)

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
