import networkx as nx
from netext.edge_rendering.arrow_tips import ArrowTip
from netext.edge_rendering.modes import EdgeSegmentDrawingMode
from netext.edge_routing.modes import EdgeRoutingMode
from netext.textual_widget.widget import GraphView
from textual.app import ComposeResult
from textual.widgets import Static


class CallGraph(Static):
    def __init__(self, graph: nx.DiGraph, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.graph = nx.DiGraph()
        self.graph = graph
        # nx.set_node_attributes(
        #     self.graph, EdgeSegmentDrawingMode.BOX_ROUNDED, "$edge-segment-drawing-mode"
        # )
        # nx.set_node_attributes(
        #     self.graph, EdgeRoutingMode.ORTHOGONAL, "$edge-routing-mode"
        # )
        # nx.set_node_attributes(self.graph, ArrowTip.ARROW, "$arrow-tip")
        for u, v in self.graph.edges():
            self.graph[u][v]["$arrow-tip"] = ArrowTip.ARROW
            self.graph[u][v]["$edge-routing-mode"] = (EdgeRoutingMode.ORTHOGONAL,)
            self.graph[u][v]["$color"] = "blue"
            self.graph[u][v]["$edge-segment-drawing-mode"] = (
                EdgeSegmentDrawingMode.BOX_ROUNDED
            )

    def compose(self) -> ComposeResult:
        self.widget = GraphView(self.graph)
        yield self.widget

    def update(self, k: object, v: object) -> None:
        self.query_one(GraphView).add_edge(k, v)
        self.ready()

    def on_mount(self):
        self.ready()
        # self.loading = True

    # def on_checkbox_changed(self, message: Checkbox.Changed):
    #     _ = message
    #     self.due()
    #
    # def due(self) -> None:
    #     # TODO: Blink the border
    #     self.styles.border = ("dashed", "yellow")
    #     self.styles.opacity = 0.8
    #     self.border_title = "Call graph: due for reloading"
    #
    # def hang(self, threw: bool) -> None:
    #     if threw:
    #         self.styles.border = ("dashed", "red")
    #         self.border_title = "Call graph: exception was thrown"
    #     else:
    #         self.due()
    #
    def ready(self) -> None:
        self.loading = False
        self.styles.border = ("solid", "blue")
        self.styles.opacity = 1.0
        self.border_title = "Call graph"
