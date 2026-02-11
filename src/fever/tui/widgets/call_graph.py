import networkx as nx
from netext.edge_rendering.arrow_tips import ArrowTip
from netext.edge_rendering.modes import EdgeSegmentDrawingMode
from netext.edge_routing.modes import EdgeRoutingMode
from netext.textual_widget.widget import GraphView
from textual.app import ComposeResult
from textual.widgets import Static


class CallGraph(Static):
    def compose(self) -> ComposeResult:
        yield GraphView(nx.DiGraph())

    def on_mount(self):
        self.loading = True

    def _style(self):
        g = self.query_one(GraphView).graph
        for u, v in g.edges():
            g[u][v]["$arrow-tip"] = ArrowTip.ARROW
            g[u][v]["$edge-routing-mode"] = (EdgeRoutingMode.ORTHOGONAL,)
            g[u][v]["$color"] = "blue"
            g[u][v]["$edge-segment-drawing-mode"] = EdgeSegmentDrawingMode.BOX_ROUNDED

    async def set_call_graph(self, graph: nx.DiGraph) -> None:
        self.ready()
        await self.query_one(GraphView).remove()
        await self.mount(GraphView(graph))
        self._style()

    def update(self, k: object, v: object) -> None:
        self.query_one(GraphView).add_edge(k, v)
        self.ready()

    def hilight(self, k: object) -> None:
        # TODO:Update style of specific node
        # self.query_one(GraphView).update(k)
        # for u, v in self.graph.edges():
        # self.ready()
        pass

    def due(self) -> None:
        # TODO: Blink the border
        self.styles.border = ("dashed", "yellow")
        self.styles.opacity = 0.8
        self.border_title = "Call graph: due for reloading"

    def ready(self) -> None:
        self.loading = False
        self.styles.border = ("solid", "blue")
        self.styles.opacity = 1.0
        self.border_title = "Call graph"
