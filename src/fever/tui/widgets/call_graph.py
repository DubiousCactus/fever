import networkx as nx
from netext.edge_rendering.modes import EdgeSegmentDrawingMode
from netext.edge_routing.modes import EdgeRoutingMode
from netext.layout_engines import LayoutDirection, SugiyamaLayout
from netext.properties.arrow_tips import ArrowTip
from netext.textual_widget.widget import GraphView
from rich.style import Style
from textual.app import ComposeResult
from textual.widgets import Static


class CallGraph(Static):
    def compose(self) -> ComposeResult:
        yield GraphView(nx.DiGraph())

    def on_mount(self):
        self.loading = True

    def _style(self):
        g = self.query_one(GraphView).graph
        nx.set_node_attributes(g, Style(color="green"), "$style")
        nx.set_node_attributes(g, Style(color="white"), "$content-style")
        nx.set_edge_attributes(g, EdgeRoutingMode.ORTHOGONAL, "$edge-routing-mode")
        nx.set_edge_attributes(
            g, EdgeSegmentDrawingMode.BOX, "$edge-segment-drawing-mode"
        )
        nx.set_edge_attributes(g, ArrowTip.NONE, "$start-arrow-tip")
        nx.set_edge_attributes(g, ArrowTip.ARROW, "$end-arrow-tip")
        nx.set_edge_attributes(g, Style(color="blue"), "$style")

    async def set_call_graph(self, graph: nx.DiGraph) -> None:
        self.ready()
        await self.query_one(GraphView).remove()
        await self.mount(
            GraphView(
                graph,
                layout_engine=SugiyamaLayout(direction=LayoutDirection.LEFT_RIGHT),
            )
        )
        self._style()

    def update(self, k: object, v: object) -> None:
        graph = self.query_one(GraphView)
        graph.add_node(k)
        graph.add_node(v)
        graph.add_edge(k, v)
        self.ready()
        self._style()

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
