import os
import runpy
import sys
from typing import List

import typer
from rich.console import Console
from typing_extensions import Annotated

from .watcher import FeverWatcher

app = typer.Typer()
console = Console()


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def watch(
    script: Annotated[str, typer.Argument(..., help="The script to run and watch.")],
    extra_args: List[str] = typer.Argument(None),
):
    """
    Watch for file changes and hot-reload as necessary.
    """
    console.print(f"Watching script: {script} ", style="bold green")
    watcher = FeverWatcher(rich_console=console)
    watcher.watch()
    command = [script] + (extra_args or [])
    sys.argv = command
    script_dir = os.path.dirname(script)
    script_path = os.path.abspath(script)
    os.chdir(script_dir)
    # Ensure relative imports (from file import func) work
    # Python normally inserts '' (the current directory) as position 0
    sys.path.insert(0, script_dir)
    try:
        # Option A: use the same globals as this module
        runpy.run_path(script_path, run_name="__main__")
        # Option B: fully isolate the script
        # runpy.run_path(script, init_globals={"__name__": "__main__"})
    except KeyboardInterrupt:
        console.print("Terminating watcher...", style="bold red")
    watcher.stop()

    if os.getenv("VIZ", "0").lower() in ["1", "true"]:
        watcher.fever.plot_call_graph()


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
    print(f"Debugging script: {script} ")


if __name__ == "__main__":
    app()
