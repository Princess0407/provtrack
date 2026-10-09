from __future__ import annotations

from typing import Any, Dict, List, Optional

import networkx as nx
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from provtrack.tui.theme import TEXT_MUTED
from provtrack.tui.utils.dag_layout import render_ascii_dag


class DAGWidget(Widget):
    can_focus = True

    BINDINGS = [
        Binding("j", "cursor_down", "Next", show=False),
        Binding("down", "cursor_down", "Next", show=False),
        Binding("k", "cursor_up", "Prev", show=False),
        Binding("up", "cursor_up", "Prev", show=False),
        Binding("enter", "activate_node", "Open"),
        Binding("/", "search", "Filter"),
        Binding("e", "export", "Export"),
    ]

    selected_node_id: reactive[Optional[str]] = reactive(None)
    search_query: reactive[str] = reactive("")

    class NodeSelected(Message):
        def __init__(self, node_id: str, node: Dict[str, Any]) -> None:
            super().__init__()
            self.node_id = node_id
            self.node = node

    class NodeActivated(Message):
        def __init__(self, node_id: str, node: Dict[str, Any]) -> None:
            super().__init__()
            self.node_id = node_id
            self.node = node

    class RequestSearch(Message):
        pass

    class RequestExport(Message):
        pass

    def __init__(self, graph: Optional[nx.DiGraph] = None, id: str | None = None) -> None:
        super().__init__(id=id)
        self.graph: nx.DiGraph = graph if graph is not None else nx.DiGraph()
        self._current_ordered_ids: List[str] = []

    def set_graph(self, graph: nx.DiGraph) -> None:
        self.graph = graph
        _, ordered = render_ascii_dag(self.graph, query_filter=self.search_query)
        self._current_ordered_ids = ordered
        if ordered and (self.selected_node_id not in ordered):
            self.selected_node_id = ordered[0]
        self.refresh()

    def set_search_query(self, query: str) -> None:
        self.search_query = query
        _, ordered = render_ascii_dag(self.graph, query_filter=self.search_query)
        self._current_ordered_ids = ordered
        if ordered and (self.selected_node_id not in ordered):
            self.selected_node_id = ordered[0]
        self.refresh()

    def watch_selected_node_id(self, old_val: Optional[str], new_val: Optional[str]) -> None:
        if new_val and new_val in self.graph.nodes:
            self.post_message(self.NodeSelected(new_val, self.graph.nodes[new_val]))
        self.refresh()

    def action_cursor_down(self) -> None:
        if not self._current_ordered_ids:
            return
        if self.selected_node_id not in self._current_ordered_ids:
            self.selected_node_id = self._current_ordered_ids[0]
            return
        idx = self._current_ordered_ids.index(self.selected_node_id)
        if idx < len(self._current_ordered_ids) - 1:
            self.selected_node_id = self._current_ordered_ids[idx + 1]

    def action_cursor_up(self) -> None:
        if not self._current_ordered_ids:
            return
        if self.selected_node_id not in self._current_ordered_ids:
            self.selected_node_id = self._current_ordered_ids[0]
            return
        idx = self._current_ordered_ids.index(self.selected_node_id)
        if idx > 0:
            self.selected_node_id = self._current_ordered_ids[idx - 1]

    def action_activate_node(self) -> None:
        if self.selected_node_id and self.selected_node_id in self.graph.nodes:
            self.post_message(self.NodeActivated(self.selected_node_id, self.graph.nodes[self.selected_node_id]))

    def action_search(self) -> None:
        self.post_message(self.RequestSearch())

    def action_export(self) -> None:
        self.post_message(self.RequestExport())

    def render(self) -> Text:
        if not self.graph.number_of_nodes():
            return Text("  No operations in graph.", style=TEXT_MUTED)

        fallback = 0 < self.size.width < 60
        text, ordered = render_ascii_dag(
            self.graph,
            selected_id=self.selected_node_id,
            fallback_plain=fallback,
            query_filter=self.search_query,
        )
        self._current_ordered_ids = ordered
        return text
