from __future__ import annotations

import os
from typing import Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from provtrack.graph.builder import LineageGraph
from provtrack.tui.theme import ACCENT_BRIGHT, BORDER, TEXT_MUTED, TEXT_SECONDARY
from provtrack.tui.widgets.diff_panel import DiffPanel
from provtrack.tui.widgets.status_bar import StatusBar


class DiffScreen(Screen):
    BINDINGS = [
        Binding("n", "next_diff", "Next diff"),
        Binding("p", "prev_diff", "Prev diff"),
        Binding("enter", "inspect_current_row", "Inspect"),
    ]

    def __init__(
        self,
        graph_a: Optional[LineageGraph] = None,
        graph_b: Optional[LineageGraph] = None,
        file_a: str = "",
        file_b: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.graph_a: Optional[LineageGraph] = graph_a
        self.graph_b: Optional[LineageGraph] = graph_b
        self.file_a: str = file_a
        self.file_b: str = file_b

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-container"):
            yield Static(id="diff-summary-bar")
            with Horizontal(id="diff-headers"):
                yield Static(id="diff-header-a")
                yield Static(id="diff-header-b")
            yield DiffPanel(id="diff-panel")
        session_label = f"{os.path.basename(self.file_a)} vs {os.path.basename(self.file_b)}" if self.file_a else ""
        yield StatusBar(
            screen_name="diff",
            session_file=session_label,
            hints="q quit  1 dag  2 diff  3 inspect  n next  p prev  Enter inspect  ? help",
            id="status-bar",
        )

    def on_mount(self) -> None:
        self.set_diff_data(self.graph_a, self.graph_b, self.file_a, self.file_b)
        self.query_one(DiffPanel).focus()

    def set_diff_data(
        self,
        graph_a: Optional[LineageGraph],
        graph_b: Optional[LineageGraph],
        file_a: str = "",
        file_b: str = "",
    ) -> None:
        self.graph_a = graph_a
        self.graph_b = graph_b
        self.file_a = file_a
        self.file_b = file_b

        if not self.is_mounted:
            return

        diff_panel = self.query_one(DiffPanel)
        raw_a = graph_a.raw_graph if graph_a else None
        raw_b = graph_b.raw_graph if graph_b else None
        diff_panel.set_data(raw_a, raw_b)

        summary_bar = self.query_one("#diff-summary-bar", Static)
        if not graph_a and not graph_b:
            summary_bar.update(Text("  No diff sessions loaded. Run with --a and --b.", style=TEXT_MUTED))
            return

        unchanged, changed, added, removed = diff_panel.get_summary_stats()
        summary_text = Text()
        summary_text.append(f"  {unchanged} ops unchanged", style=TEXT_SECONDARY)
        summary_text.append("  |  ", style=BORDER)
        summary_text.append(f"{changed} ops changed", style=ACCENT_BRIGHT)
        summary_text.append("  |  ", style=BORDER)
        summary_text.append(f"{added} added", style=ACCENT_BRIGHT)
        summary_text.append("  |  ", style=BORDER)
        summary_text.append(f"{removed} removed", style=TEXT_MUTED)
        summary_bar.update(summary_text)

        header_a = self.query_one("#diff-header-a", Static)
        header_b = self.query_one("#diff-header-b", Static)
        ops_a = graph_a.node_count if graph_a else 0
        ops_b = graph_b.node_count if graph_b else 0
        name_a = os.path.basename(file_a) if file_a else "Session A"
        name_b = os.path.basename(file_b) if file_b else "Session B"

        header_a.update(Text(f" {name_a} ({ops_a} ops)", style=ACCENT_BRIGHT))
        header_b.update(Text(f" {name_b} ({ops_b} ops)", style=ACCENT_BRIGHT))

        status_bar = self.query_one(StatusBar)
        status_bar.session_file = f"{name_a} vs {name_b}"

    def action_next_diff(self) -> None:
        self.query_one(DiffPanel).action_next_diff()

    def action_prev_diff(self) -> None:
        self.query_one(DiffPanel).action_prev_diff()

    def action_inspect_current_row(self) -> None:
        self.query_one(DiffPanel).action_activate_row()

    @on(DiffPanel.RowActivated)
    def handle_row_activated(self, message: DiffPanel.RowActivated) -> None:
        from provtrack.tui.screens.inspector import InspectorScreen

        target_h = ""
        if message.row.node_b:
            target_h = message.row.node_b.get("output_hash") or message.row.node_b.get("input_hash") or ""
        elif message.row.node_a:
            target_h = message.row.node_a.get("output_hash") or message.row.node_a.get("input_hash") or ""

        target_graph = self.graph_b or self.graph_a
        session_name = self.file_b or self.file_a

        alt_h = ""
        if message.row.node_a and message.row.node_b:
            alt_h = message.row.node_a.get("output_hash") or ""

        self.app.push_screen(
            InspectorScreen(
                target_hash=target_h,
                graph=target_graph,
                session_file=session_name,
                alt_hash=alt_h,
            )
        )
