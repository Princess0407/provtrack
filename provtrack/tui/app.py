from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rich.panel import Panel
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from provtrack.graph.builder import LineageGraph
from provtrack.logger import OperationRecord
from provtrack.tui.screens.dag import DAGScreen
from provtrack.tui.screens.diff import DiffScreen
from provtrack.tui.screens.inspector import InspectorScreen
from provtrack.tui.widgets.dag_graph import DAGWidget
from provtrack.tui.theme import (
    ACCENT_BRIGHT,
    BORDER,
    DEFAULT_CSS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class HelpModal(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        content = Text()
        content.append("provtrack keyboard reference\n\n", style=f"bold {TEXT_PRIMARY}")

        content.append("Global:\n", style=TEXT_SECONDARY)
        content.append("  1              ", style=ACCENT_BRIGHT)
        content.append("DAG screen\n", style=TEXT_PRIMARY)
        content.append("  2              ", style=ACCENT_BRIGHT)
        content.append("Diff screen\n", style=TEXT_PRIMARY)
        content.append("  3              ", style=ACCENT_BRIGHT)
        content.append("Inspector screen\n", style=TEXT_PRIMARY)
        content.append("  ?              ", style=ACCENT_BRIGHT)
        content.append("Show this help\n", style=TEXT_PRIMARY)
        content.append("  q              ", style=ACCENT_BRIGHT)
        content.append("Quit provtrack\n\n", style=TEXT_PRIMARY)

        content.append("DAG Screen:\n", style=TEXT_SECONDARY)
        content.append("  j / k, Arrows  ", style=ACCENT_BRIGHT)
        content.append("Navigate operations\n", style=TEXT_PRIMARY)
        content.append("  Enter          ", style=ACCENT_BRIGHT)
        content.append("View operation details\n", style=TEXT_PRIMARY)
        content.append("  /              ", style=ACCENT_BRIGHT)
        content.append("Filter operations by name\n", style=TEXT_PRIMARY)
        content.append("  e              ", style=ACCENT_BRIGHT)
        content.append("Export graph (JSON/Mermaid/DOT)\n\n", style=TEXT_PRIMARY)

        content.append("Operation Screen:\n", style=TEXT_SECONDARY)
        content.append("  Esc / b        ", style=ACCENT_BRIGHT)
        content.append("Back to previous screen\n", style=TEXT_PRIMARY)
        content.append("  a / d          ", style=ACCENT_BRIGHT)
        content.append("Jump to ancestors / descendants\n", style=TEXT_PRIMARY)
        content.append("  Enter          ", style=ACCENT_BRIGHT)
        content.append("Navigate to selected node\n\n", style=TEXT_PRIMARY)

        content.append("Diff Screen:\n", style=TEXT_SECONDARY)
        content.append("  n / p          ", style=ACCENT_BRIGHT)
        content.append("Next / previous diff\n", style=TEXT_PRIMARY)
        content.append("  Enter          ", style=ACCENT_BRIGHT)
        content.append("Inspect changed state\n\n", style=TEXT_PRIMARY)

        content.append("Inspector Screen:\n", style=TEXT_SECONDARY)
        content.append("  c              ", style=ACCENT_BRIGHT)
        content.append("Copy SHA-256 to clipboard\n", style=TEXT_PRIMARY)
        content.append("  Esc / b        ", style=ACCENT_BRIGHT)
        content.append("Back to previous screen\n\n", style=TEXT_PRIMARY)

        content.append("Press Esc to close", style=TEXT_MUTED)

        yield Vertical(Static(Panel(content, border_style=BORDER)), classes="modal-dialog")


class ProvtrackApp(App):
    TITLE = "provtrack"
    CSS = DEFAULT_CSS

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("1", "switch_screen('dag')", "DAG"),
        ("2", "switch_screen('diff')", "Diff"),
        ("3", "switch_screen('inspector')", "Inspector"),
        ("?", "show_help", "Help"),
    ]

    def __init__(
        self,
        session_file: Optional[Union[Path, str]] = None,
        diff_a: Optional[Union[Path, str]] = None,
        diff_b: Optional[Union[Path, str]] = None,
    ) -> None:
        super().__init__()
        self.session_file_path: Optional[Path] = Path(session_file).resolve() if session_file else None
        self.diff_a_path: Optional[Path] = Path(diff_a).resolve() if diff_a else None
        self.diff_b_path: Optional[Path] = Path(diff_b).resolve() if diff_b else None

        self.graph: Optional[LineageGraph] = None
        self.graph_a: Optional[LineageGraph] = None
        self.graph_b: Optional[LineageGraph] = None

        self.dag_screen = DAGScreen(session_file=str(self.session_file_path) if self.session_file_path else "")
        self.diff_screen = DiffScreen(
            file_a=str(self.diff_a_path) if self.diff_a_path else "",
            file_b=str(self.diff_b_path) if self.diff_b_path else "",
        )
        self.inspector_screen = InspectorScreen(session_file=str(self.session_file_path) if self.session_file_path else "")

    def on_mount(self) -> None:
        self.install_screen(self.dag_screen, name="dag")
        self.install_screen(self.diff_screen, name="diff")
        self.install_screen(self.inspector_screen, name="inspector")

        if self.diff_a_path and self.diff_b_path:
            self.push_screen("diff")
        else:
            self.push_screen("dag")

        self._load_session_data_worker()

    @work(thread=True)
    def _load_session_data_worker(self) -> None:
        graph = self._safe_load_session(self.session_file_path) if self.session_file_path else None
        graph_a = self._safe_load_session(self.diff_a_path) if self.diff_a_path else None
        graph_b = self._safe_load_session(self.diff_b_path) if self.diff_b_path else None

        self.call_from_thread(self._apply_loaded_data, graph, graph_a, graph_b)

    def _apply_loaded_data(
        self,
        graph: Optional[LineageGraph],
        graph_a: Optional[LineageGraph],
        graph_b: Optional[LineageGraph],
    ) -> None:
        self.graph = graph
        self.graph_a = graph_a
        self.graph_b = graph_b

        if graph:
            self.dag_screen.set_graph(graph, str(self.session_file_path or ""))
            first_hash = ""
            for node_attrs in graph.nodes():
                h = node_attrs.get("output_hash") or node_attrs.get("input_hash")
                if h:
                    first_hash = h
                    break
            self.inspector_screen.inspect_hash(first_hash, graph, str(self.session_file_path or ""))

        if graph_a or graph_b:
            self.diff_screen.set_diff_data(
                graph_a,
                graph_b,
                str(self.diff_a_path or ""),
                str(self.diff_b_path or ""),
            )
            if not graph:
                target_g = graph_b or graph_a
                target_file = str(self.diff_b_path or self.diff_a_path or "")
                first_h = ""
                if target_g:
                    for node_attrs in target_g.nodes():
                        h = node_attrs.get("output_hash") or node_attrs.get("input_hash")
                        if h:
                            first_h = h
                            break
                self.inspector_screen.inspect_hash(first_h, target_g, target_file)

    @staticmethod
    def _safe_load_session(path: Optional[Path]) -> Optional[LineageGraph]:
        if not path or not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            nodes = data.get("nodes", [])
            if not isinstance(nodes, list):
                return None

            records: List[OperationRecord] = []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                try:
                    raw_tags = node.get("tags", ())
                    tags_tuple: tuple[str, ...] = tuple(raw_tags) if isinstance(raw_tags, (list, tuple)) else ()
                    rec = OperationRecord(
                        id=node.get("id") or node.get("op_id"),
                        op_name=str(node.get("op_name", "unknown")),
                        obj_type=str(node.get("obj_type", "")),
                        input_hash=node.get("input_hash"),
                        output_hash=str(node.get("output_hash", "")),
                        args_repr=str(node.get("args_repr", "")),
                        kwargs_repr=str(node.get("kwargs_repr", "")),
                        source_file=str(node.get("source_file") or node.get("caller_file", "")),
                        source_line=int(node.get("source_line") or node.get("caller_line", 0)),
                        caller_func=str(node.get("caller_func", "")),
                        timestamp=node.get("timestamp"),
                        duration_ms=float(node.get("duration_ms", 0.0)),
                        tags=tags_tuple,
                    )
                    records.append(rec)
                except Exception:
                    continue

            return LineageGraph.from_records(records)
        except Exception:
            return None

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    async def action_switch_screen(self, screen: str) -> None:
        if screen == "inspector" and self.graph:
            dag_selected = self.dag_screen.query_one(DAGWidget).selected_node_id
            if dag_selected and dag_selected in self.graph.raw_graph.nodes:
                attrs = self.graph.raw_graph.nodes[dag_selected]
                h = attrs.get("output_hash") or attrs.get("input_hash")
                if h:
                    self.inspector_screen.inspect_hash(h, self.graph, str(self.session_file_path or ""))
        await super().action_switch_screen(screen)
