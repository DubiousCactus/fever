import importlib
import os
import runpy
import sys
from typing import List

import typer
from rich.console import Console
from typing_extensions import Annotated

from .core import FeverCore
from .tui.builder_ui import BuilderUI
from .watcher import FeverWatcher

app = typer.Typer()
console = Console()


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def watch(
    script: Annotated[str, typer.Argument(..., help="The script to run and watch.")],
    extra_args: List[str] = typer.Argument(None),
    no_cache: Annotated[bool, typer.Option("--no-cache")] = False,
):
    """
    Watch for file changes and hot-reload as necessary.
    """
    console.print(
        f"Watching script: {script} " + ("with caching" if not no_cache else ""),
        style="bold green",
    )
    watcher = FeverWatcher(rich_console=console, with_cache=not no_cache)
    watcher.watch()
    command = [script] + (extra_args or [])
    sys.argv = command
    script_path = os.path.abspath(script)
    script_dir = os.path.dirname(script_path)
    os.chdir(script_dir)
    # Ensure relative imports (from file import func) work
    # Python normally inserts '' (the current directory) as position 0
    sys.path.insert(0, script_dir)
    # NOTE: We manually import the script module so that we can track it.
    importlib.import_module(script.split(".py")[0])

    def cleanup():
        watcher.fever.export_trace("program_trace.pkl")
        watcher.stop()
        if os.getenv("FEVER_PLOT_TRACE", "0").lower() in ["1", "true"]:
            watcher.fever.plot_call_graph()
        if os.getenv("FEVER_PLOT_DEPS", "0").lower() in ["1", "true"]:
            watcher.fever.plot_dependency_graph()
            print(
                f"Dependencies tracked: {watcher.fever.dependency_tracker.all_imports}"
            )

    try:
        # Option A: use the same globals as this module
        runpy.run_path(script_path, run_name="__main__")
        # Option B: fully isolate the script
        # runpy.run_path(script, init_globals={"__name__": "__main__"})
    except KeyboardInterrupt:
        console.print("Terminating watcher...", style="bold red")
    finally:
        cleanup()


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def debug(
    script: Annotated[str, typer.Argument(..., help="The script to run and watch.")],
    extra_args: List[str] = typer.Argument(None),
):
    """
    Debug a program with the TUI.
    """
    save_file = "program_trace.pkl"
    if not os.path.isfile(save_file):
        raise FileNotFoundError(
            f"{save_file} not found. Please run the script with 'watch' command first to generate the program trace."
        )
    fever_engine = FeverCore(
        cache_size="1GB"
    )  # TODO: Unlimited cache with disk swapping
    fever_engine.setup()
    command = [script] + (extra_args or [])
    sys.argv = command
    script_path = os.path.abspath(script)
    script_dir = os.path.dirname(script_path)
    os.chdir(script_dir)
    # Ensure relative imports (from file import func) work
    # Python normally inserts '' (the current directory) as position 0
    sys.path.insert(0, script_dir)
    # NOTE: We manually import the script module so that we can track it.
    importlib.import_module(script.split(".py")[0])

    BuilderUI(fever_engine, script_path, save_file).run()
    fever_engine.cleanup()


if __name__ == "__main__":
    app()
