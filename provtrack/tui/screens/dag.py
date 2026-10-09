from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from rich.panel import Panel
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Static

from provtrack.graph.builder import LineageGraph
from provtrack.tui.theme import ACCENT_BRIGHT, BORDER, TEXT_MUTED, TEXT_PRIMARY
from provtrack.tui.widgets.dag_graph import DAGWidget
from provtrack.tui.widgets.op_card import OpCard
from provtrack.tui.widgets.status_bar import StatusBar


class ExportModal(ModalScreen[Optional[str]]):
    BINDINGS = [
        Binding("1", "select_fmt('json')", "JSON"),
        Binding("j", "select_fmt('json')", "JSON"),
        Binding("2", "select_fmt('mermaid')", "Mermaid"),
        Binding("m", "select_fmt('mermaid')", "Mermaid"),
        Binding("3", "select_fmt('dot')", "DOT"),
        Binding("d", "select_fmt('dot')", "DOT"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        content = Text()
        content.append("Export Pipeline Graph\n\n", style=f"bold {TEXT_PRIMARY}")
        content.append("Choose format:\n", style=TEXT_MUTED)
        content.append("  [1 / j]  JSON\n", style=ACCENT_BRIGHT)
        content.append("  [2 / m]  Mermaid\n", style=ACCENT_BRIGHT)
        content.append("  [3 / d]  DOT\n\n", style=ACCENT_BRIGHT)
        content.append("Press Esc to cancel", style=TEXT_MUTED)
        yield Vertical(Static(Panel(content, border_style=BORDER)), classes="modal-dialog")

    def action_select_fmt(self, fmt: str) -> None:
        self.dismiss(fmt)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DAGScreen(Screen):
    BINDINGS = [
        Binding("/", "focus_search", "Filter"),
        Binding("e", "export_graph", "Export"),
        Binding("escape", "cancel_search", "Cancel filter", show=False),
        Binding("enter", "open_selected_node", "View details"),
    ]

    def __init__(
        self,
        graph: Optional[LineageGraph] = None,
        session_file: str = "",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.graph: Optional[LineageGraph] = graph
        self.session_file: str = session_file

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter ops by name... (Enter/Esc to return)", id="dag-search-input")
        with Horizontal(id="dag-screen-container"):
            with Vertical(id="dag-left-panel"):
                yield DAGWidget(id="dag-widget")
            with Vertical(id="dag-right-panel"):
                yield OpCard(id="op-card")
        yield StatusBar(
            screen_name="dag",
            session_file=self.session_file,
            hints="q quit  1 dag  2 diff  3 inspect  / filter  e export  Enter view  ? help",
            id="status-bar",
        )

    def on_mount(self) -> None:
        if self.graph:
            self.set_graph(self.graph, self.session_file)
        self.query_one(DAGWidget).focus()

    def set_graph(self, graph: LineageGraph, session_file: str = "") -> None:
        self.graph = graph
        self.session_file = session_file
        if not self.is_mounted:
            return
        dag_widget = self.query_one(DAGWidget)
        dag_widget.set_graph(graph.raw_graph)
        status_bar = self.query_one(StatusBar)
        status_bar.session_file = session_file
        if dag_widget.selected_node_id and dag_widget.selected_node_id in graph.raw_graph.nodes:
            self.query_one(OpCard).update_node(graph.raw_graph.nodes[dag_widget.selected_node_id])

    @on(DAGWidget.NodeSelected)
    def handle_node_selected(self, message: DAGWidget.NodeSelected) -> None:
        self.query_one(OpCard).update_node(message.node)

    @on(DAGWidget.NodeActivated)
    def handle_node_activated(self, message: DAGWidget.NodeActivated) -> None:
        from provtrack.tui.screens.operation import OperationScreen

        self.app.push_screen(
            OperationScreen(
                node=message.node,
                graph=self.graph,
                session_file=self.session_file,
            )
        )

    @on(DAGWidget.RequestSearch)
    def handle_request_search(self, message: DAGWidget.RequestSearch) -> None:
        self.action_focus_search()

    @on(DAGWidget.RequestExport)
    def handle_request_export(self, message: DAGWidget.RequestExport) -> None:
        self.action_export_graph()

    def action_focus_search(self) -> None:
        search_input = self.query_one(Input)
        search_input.add_class("visible")
        search_input.focus()

    def action_export_graph(self) -> None:
        if not self.graph:
            return

        def handle_export(fmt: Optional[str]) -> None:
            if not fmt or not self.graph:
                return
            ext = "json" if fmt == "json" else ("mmd" if fmt == "mermaid" else "dot")
            stem = Path(self.session_file).stem if self.session_file else "export"
            out_file = Path(f"{stem}.{ext}")
            try:
                if fmt == "json":
                    content = self.graph.to_json()
                elif fmt == "dot":
                    content = self.graph.to_dot()
                else:
                    content = self.graph.to_mermaid()
                out_file.write_text(content, encoding="utf-8")
                self.notify(f"Exported graph to {out_file}")
            except OSError as err:
                self.notify(f"Export failed: {err}", severity="error")

        self.app.push_screen(ExportModal(), handle_export)

    def action_open_selected_node(self) -> None:
        self.query_one(DAGWidget).action_activate_node()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "dag-search-input":
            self.query_one(DAGWidget).set_search_query(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "dag-search-input":
            event.input.remove_class("visible")
            self.query_one(DAGWidget).focus()

    def action_cancel_search(self) -> None:
        search_input = self.query_one(Input)
        if search_input.has_class("visible"):
            search_input.value = ""
            search_input.remove_class("visible")
            self.query_one(DAGWidget).focus()
