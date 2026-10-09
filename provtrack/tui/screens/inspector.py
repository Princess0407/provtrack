from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from provtrack.graph.builder import LineageGraph
from provtrack.tui.theme import ACCENT_BRIGHT, BORDER, TEXT_MUTED, TEXT_SECONDARY
from provtrack.tui.utils.dag_layout import render_ascii_dag
from provtrack.tui.widgets.hash_table import HashTable
from provtrack.tui.widgets.status_bar import StatusBar


class InspectorScreen(Screen):
    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("b", "go_back", "Back"),
        Binding("c", "copy_hash", "Copy hash"),
    ]

    def __init__(
        self,
        target_hash: str = "",
        graph: Optional[LineageGraph] = None,
        session_file: str = "",
        alt_hash: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.target_hash: str = target_hash
        self.graph: Optional[LineageGraph] = graph
        self.session_file: str = session_file
        self.alt_hash: str = alt_hash

    def compose(self) -> ComposeResult:
        with Vertical(id="inspector-screen-container"):
            yield Static(id="inspector-hash-display")
            with Vertical(id="inspector-table-container"):
                yield HashTable(id="inspector-table")
            yield Static(id="inspector-graph-container")
        yield StatusBar(
            screen_name="inspector",
            session_file=self.session_file,
            hints="Esc / b back  c copy hash  q quit  1 dag  2 diff  3 inspect  ? help",
            id="status-bar",
        )

    def on_mount(self) -> None:
        if not self.target_hash and self.graph:
            for node_attrs in self.graph.nodes():
                h = node_attrs.get("output_hash") or node_attrs.get("input_hash")
                if h:
                    self.target_hash = h
                    break

        self.inspect_hash(self.target_hash, self.graph, self.session_file, self.alt_hash)

    def inspect_hash(
        self,
        target_hash: str,
        graph: Optional[LineageGraph],
        session_file: str = "",
        alt_hash: str = "",
    ) -> None:
        self.target_hash = target_hash
        self.graph = graph
        self.session_file = session_file
        self.alt_hash = alt_hash

        if not self.is_mounted:
            return

        status_bar = self.query_one(StatusBar)
        status_bar.session_file = session_file

        display_static = self.query_one("#inspector-hash-display", Static)
        if not target_hash:
            display_static.update(Text("No hash selected for inspection.", style=TEXT_MUTED))
            return

        top_text = Text()
        top_text.append("SHA-256 State Hash:\n", style=TEXT_SECONDARY)
        top_text.append(f"{target_hash}\n", style=f"bold {TEXT_SECONDARY}")
        if alt_hash and alt_hash != target_hash:
            top_text.append("Comparison Session Hash:\n", style=TEXT_MUTED)
            top_text.append(f"{alt_hash}\n", style=ACCENT_BRIGHT)
        display_static.update(top_text)

        hash_table = self.query_one(HashTable)
        records: List[Dict[str, Any]] = []
        if graph:
            records = graph.ops_touching_data(target_hash)
        hash_table.populate(records, target_hash)

        context_static = self.query_one("#inspector-graph-container", Static)
        if not graph or not graph.node_count:
            context_static.update(Panel(Text("No graph context available.", style=TEXT_MUTED), title="Graph Context (±2 levels)", border_style=BORDER))
            return

        raw_g = graph.raw_graph
        producing_nodes = [
            n for n in raw_g.nodes
            if raw_g.nodes[n].get("output_hash") == target_hash
        ]
        if not producing_nodes:
            producing_nodes = [
                n for n in raw_g.nodes
                if raw_g.nodes[n].get("input_hash") == target_hash
            ]

        neighborhood: Set[str] = set(producing_nodes)
        for node_id in producing_nodes:
            preds_1 = list(raw_g.predecessors(node_id))
            preds_2 = [p for p1 in preds_1 for p in raw_g.predecessors(p1)]
            succs_1 = list(raw_g.successors(node_id))
            succs_2 = [s for s1 in succs_1 for s in raw_g.successors(s1)]
            neighborhood.update(preds_1)
            neighborhood.update(preds_2)
            neighborhood.update(succs_1)
            neighborhood.update(succs_2)

        sub_g = raw_g.subgraph(neighborhood).copy()
        selected_root = producing_nodes[0] if producing_nodes else None
        rendered_subgraph, _ = render_ascii_dag(sub_g, selected_id=selected_root)

        context_static.update(Panel(rendered_subgraph, title="Graph Context (±2 levels)", border_style=BORDER))

    def action_go_back(self) -> None:
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        else:
            self.app.switch_screen("dag")

    def action_copy_hash(self) -> None:
        if not self.target_hash:
            self.notify("No hash to copy")
            return
        try:
            import pyperclip
            pyperclip.copy(self.target_hash)
            self.notify("Hash copied to clipboard")
        except Exception:
            self.notify("Clipboard unavailable", severity="warning")
