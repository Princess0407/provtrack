from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import networkx as nx
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from provtrack.graph.builder import LineageGraph
from provtrack.tui.theme import BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from provtrack.tui.utils.formatter import format_duration, format_timestamp, truncate_hash
from provtrack.tui.widgets.status_bar import StatusBar


class OperationScreen(Screen):
    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("b", "go_back", "Back"),
        Binding("a", "focus_ancestors", "Ancestors"),
        Binding("d", "focus_descendants", "Descendants"),
    ]

    def __init__(
        self,
        node: Dict[str, Any],
        graph: Optional[LineageGraph] = None,
        session_file: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.node: Dict[str, Any] = node
        self.graph: Optional[LineageGraph] = graph
        self.session_file: str = session_file

    def compose(self) -> ComposeResult:
        with Vertical(id="operation-screen-container"):
            yield Static(id="op-header")
            with Horizontal(id="op-middle"):
                with Vertical(id="op-ancestors-panel"):
                    yield Static("Ancestors (operations that fed in):", classes="text-secondary")
                    yield OptionList(id="op-ancestors-list")
                with Vertical(id="op-descendants-panel"):
                    yield Static("Descendants (operations that consumed output):", classes="text-secondary")
                    yield OptionList(id="op-descendants-list")
            yield Static(id="op-metadata-panel")
        yield StatusBar(
            screen_name="operation",
            session_file=self.session_file,
            hints="Esc / b back  a ancestors  d descendants  Enter jump  ? help",
            id="status-bar",
        )

    def on_mount(self) -> None:
        self._populate_view()

    def _populate_view(self) -> None:
        op_name = self.node.get("op_name") or "unknown"
        src_file = self.node.get("source_file") or self.node.get("caller_file") or ""
        src_line = self.node.get("source_line") or self.node.get("caller_line") or 0
        src_str = f"{os.path.basename(src_file)}:{src_line}" if src_file else "-"
        ts_str = format_timestamp(self.node.get("timestamp"))
        dur_str = format_duration(self.node.get("duration_ms", 0.0))

        header_text = Text()
        header_text.append(f"{op_name}", style=f"bold {TEXT_PRIMARY}")
        header_text.append("  |  ", style=BORDER)
        header_text.append(src_str, style=TEXT_SECONDARY)
        header_text.append("  |  ", style=BORDER)
        header_text.append(ts_str if ts_str else "--:--:--", style=TEXT_MUTED)
        header_text.append("  |  ", style=BORDER)
        header_text.append(dur_str, style=TEXT_PRIMARY)
        self.query_one("#op-header", Static).update(header_text)

        ancestors_list = self.query_one("#op-ancestors-list", OptionList)
        descendants_list = self.query_one("#op-descendants-list", OptionList)
        ancestors_list.clear_options()
        descendants_list.clear_options()

        node_id = self.node.get("id") or self.node.get("op_id", "")
        raw_g = self.graph.raw_graph if self.graph else None

        if raw_g and node_id in raw_g:
            anc_ids: List[str] = list(nx.ancestors(raw_g, node_id))
            desc_ids: List[str] = list(nx.descendants(raw_g, node_id))

            for anc_id in anc_ids:
                attrs = raw_g.nodes[anc_id]
                name = attrs.get("op_name") or "op"
                h = truncate_hash(attrs.get("output_hash") or attrs.get("input_hash"))
                ancestors_list.add_option(Option(f"{name} [{h}]", id=anc_id))

            for desc_id in desc_ids:
                attrs = raw_g.nodes[desc_id]
                name = attrs.get("op_name") or "op"
                h = truncate_hash(attrs.get("output_hash") or attrs.get("input_hash"))
                descendants_list.add_option(Option(f"{name} [{h}]", id=desc_id))

        in_h = self.node.get("input_hash") or "-"
        out_h = self.node.get("output_hash") or "-"
        tags = self.node.get("tags") or ()
        tags_str = ", ".join(tags) if isinstance(tags, (list, tuple)) else str(tags)
        args_repr = self.node.get("args_repr") or self.node.get("kwargs_repr") or "-"

        meta_table = Table.grid(padding=(0, 2))
        meta_table.add_column(style=TEXT_SECONDARY, justify="left", width=14)
        meta_table.add_column(style=TEXT_MUTED, justify="left")

        meta_table.add_row("Input hash", Text(str(in_h), style=TEXT_MUTED))
        meta_table.add_row("Output hash", Text(str(out_h), style=TEXT_MUTED))
        meta_table.add_row("Tags", Text(tags_str if tags_str else "-", style=TEXT_PRIMARY))
        meta_table.add_row("Args", Text(str(args_repr), style=TEXT_PRIMARY))

        self.query_one("#op-metadata-panel", Static).update(meta_table)

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_focus_ancestors(self) -> None:
        self.query_one("#op-ancestors-list", OptionList).focus()

    def action_focus_descendants(self) -> None:
        self.query_one("#op-descendants-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id and self.graph:
            raw_g = self.graph.raw_graph
            if event.option_id in raw_g:
                self.node = raw_g.nodes[event.option_id]
                self._populate_view()
