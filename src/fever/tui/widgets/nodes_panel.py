from collections import defaultdict
from typing import List, Tuple

import networkx as nx
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Label, Select, Static

from fever.types import TraceNode


def _grouped_options(
    nodes,
) -> List[Tuple[Text, TraceNode | None]]:
    """Build Select options grouped by module, with styled labels.

    Each module group is visually separated by a header-style entry
    identifiable by a `None` value. These entries are intended to be
    non-selectable by the user.
    """
    by_module: dict[str, list[TraceNode]] = defaultdict(list)
    for n in nodes:
        by_module[n.module].append(n)

    options: List[Tuple[Text, TraceNode | None]] = []
    for module in sorted(by_module.keys()):
        # Add a visual module header with None as a value
        header = Text(f"── {module} ──", style="bold dim cyan")
        options.append((header, None))
        for node in sorted(by_module[module], key=lambda n: str(n.func)):
            label = Text()
            label.append("  ")
            label.append(str(node.func), style="bold white")
            if node.params_hash is not None:
                label.append(f" (0x{hex(node.params_hash)[-5:]})", style="dim")
            options.append((label, node))
    return options


class TraceNodesPanel(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._call_graph = nx.DiGraph()

    def set_call_graph(self, graph: nx.DiGraph) -> None:
        self._call_graph = graph
        self._refresh()

    def _refresh(self):
        options = _grouped_options(self._call_graph.nodes)
        self.query_one("#start_node", Select).set_options(options)
        self.ready()

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label("Start node:"),
            Select([], id="start_node"),
        )
        yield Horizontal(
            Label("End node:"),
            Select([], id="end_node", disabled=True),
        )
        yield Label("Select a start node first.", id="hint")
        no_descendants_label = Label(
            "This start node has no descendants!",
            id="no_descendants_hint",
        )
        no_descendants_label.visible = False
        yield no_descendants_label

    @on(Select.Changed)
    def select_changed(self, event: Select.Changed) -> None:
        hint_label = self.query_one("#hint", Label)
        if event.value is None:
            # A module header was selected; revert the selection
            event.select.value = Select.NULL
            hint_label.update("⚠️ [bold red]Please select a function, not a module header.[/]")
            hint_label.markup = True
            hint_label.visible = True
            return
        if event.select.value is Select.NULL:
            return

        hint_label.markup = False  # Reset for standard messages
        if event.select.id == "start_node":
            hint_label.visible = False
            end_node = self.query_one("#end_node", Select)
            end_node.clear()
            descendants = nx.descendants(self._call_graph, event.value)
            if len(descendants) == 0:
                end_node.disabled = True
                self.query_one("#no_descendants_hint", Label).visible = True
                return
            self.query_one("#no_descendants_hint", Label).visible = False
            end_node.set_options(_grouped_options(descendants))
            end_node.disabled = False

    def on_mount(self):
        self.loading = True

    def hang(self, threw: bool) -> None:
        if threw:
            self.styles.border = ("dashed", "red")
            self.border_title = "Trace nodes: exception was thrown"
            self.query_one("#start_node", Select).disabled = True
            self.query_one("#end_node", Select).disabled = True
        else:
            self.ready()

    def ready(self) -> None:
        self.loading = False
        self.styles.border = ("solid", "green")
        self.styles.opacity = 1.0
        self.border_title = "Trace nodes: active"
        self.query_one("#start_node", Select).disabled = False
        self.query_one("#end_node", Select).disabled = False

    @property
    def trace_nodes(self) -> Tuple[TraceNode, TraceNode]:
        return (
            self.query_one("#start_node", Select).value,
            self.query_one("#end_node", Select).value,
        )
