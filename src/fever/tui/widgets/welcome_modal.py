import json
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Label, Static

PREFS_PATH = Path.home() / ".config" / "fever" / "prefs.json"

WELCOME_TEXT = """\
[bold]Welcome to the Fever Trace Replayer![/bold]

Fever is currently tracing your code to build the call graph. \
Once tracing is complete, you can:

  1. Select [bold]entry[/bold] and [bold]exit[/bold] nodes from the dropdowns
  2. Press [bold yellow]r[/bold yellow] or click the [bold green]▶ Play[/bold green] button to re-run

The [italic]Logs & Execution[/italic] tab will show trace output, \
exceptions, and local variables.
"""


def should_show_welcome() -> bool:
    """Check persisted preferences to see if the welcome modal should be shown."""
    try:
        prefs = json.loads(PREFS_PATH.read_text())
        return not prefs.get("hide_welcome", False)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return True


def _save_hide_welcome(hide: bool) -> None:
    """Persist the 'hide_welcome' preference."""
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    prefs: dict = {}
    try:
        prefs = json.loads(PREFS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    prefs["hide_welcome"] = hide
    PREFS_PATH.write_text(json.dumps(prefs, indent=2))


class WelcomeModal(ModalScreen[None]):
    """A modal welcome screen shown on first launch."""

    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    WelcomeModal {
        align: center middle;
    }

    #welcome-dialog {
        width: 64;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }

    #welcome-body {
        margin-bottom: 1;
    }

    #welcome-footer {
        height: auto;
        align-horizontal: right;
    }

    #welcome-dismiss {
        margin-left: 1;
    }

    #welcome-checkbox {
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome-dialog"):
            yield Static(WELCOME_TEXT, id="welcome-body", markup=True)
            yield Checkbox("Don't show this again", id="welcome-checkbox")
            with Horizontal(id="welcome-footer"):
                yield Button("Got it!", variant="primary", id="welcome-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "welcome-dismiss":
            checkbox = self.query_one("#welcome-checkbox", Checkbox)
            if checkbox.value:
                _save_hide_welcome(True)
            self.dismiss(None)
