from textual.app import ComposeResult
from textual.widgets import Static


class FunctionStatsPanel(Static):
    """Placeholder widget for displaying stats about the selected call graph node.

    TODO: Implement with actual function stats (call count, execution time, etc.)
    """

    DEFAULT_CSS = """
    FunctionStatsPanel {
        height: 1fr;
        border: solid gray;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim italic]Select a function node in the call graph to view stats here.[/dim italic]",
            markup=True,
        )

    def on_mount(self) -> None:
        self.border_title = "Function stats"
