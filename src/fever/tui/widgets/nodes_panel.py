import networkx as nx
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Label, Select, Static


class TraceNodesPanel(Static):
    def __init__(self, call_graph: nx.DiGraph, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._call_graph = call_graph

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="trace_nodes")
        yield Horizontal(
            Label("Start node:"),
            Select([(n, n) for n in self._call_graph.nodes], id="start_node"),
        )
        yield Horizontal(
            Label("End node:"),
            Select([], id="end_node", disabled=True, allow_blank=True),
        )

    @on(Select.Changed)
    def select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "start_node":
            end_node = self.query_one("#end_node", Select)
            end_node.clear()
            end_node.set_options(
                [(n, n) for n in nx.descendants(self._call_graph, event.value)]
            )
            end_node.disabled = False
        self.due()

    def on_mount(self):
        self.ready()

    def due(self) -> None:
        # TODO: Blink the border
        self.styles.border = ("dashed", "yellow")
        self.styles.opacity = 0.8
        self.border_title = "Frozen modules: due for reloading"

    def hang(self, threw: bool) -> None:
        if threw:
            self.styles.border = ("dashed", "red")
            self.border_title = "Frozen modules: exception was thrown"
        else:
            self.due()

    def ready(self) -> None:
        self.loading = False
        self.styles.border = ("solid", "green")
        self.styles.opacity = 1.0
        self.border_title = "Frozen modules: active"
