from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import networkx as nx
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from provtrack.tui.theme import (
    ACCENT,
    ACCENT_BRIGHT,
    BACKGROUND,
    BORDER,
    ERROR,
    TEXT_MUTED,
    TEXT_SECONDARY,
)
from provtrack.tui.utils.formatter import truncate_hash


@dataclass(frozen=True)
class DiffRow:
    state: str  # SAME, CHANGED, ADDED, REMOVED
    op_name: str
    node_a: Optional[Dict[str, Any]]
    node_b: Optional[Dict[str, Any]]


class DiffPanel(Widget):
    can_focus = True

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("n", "next_diff", "Next diff"),
        Binding("p", "prev_diff", "Prev diff"),
        Binding("enter", "activate_row", "Inspect"),
    ]

    selected_index: reactive[int] = reactive(0)

    class RowActivated(Message):
        def __init__(self, row: DiffRow) -> None:
            super().__init__()
            self.row = row

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.rows: List[DiffRow] = []

    def set_data(
        self,
        graph_a: Optional[nx.DiGraph],
        graph_b: Optional[nx.DiGraph],
    ) -> None:
        self.rows = self._compute_diff_rows(graph_a, graph_b)
        self.selected_index = 0
        self.refresh()

    @staticmethod
    def _compute_diff_rows(
        graph_a: Optional[nx.DiGraph],
        graph_b: Optional[nx.DiGraph],
    ) -> List[DiffRow]:
        if not graph_a and not graph_b:
            return []

        nodes_a: List[Dict[str, Any]] = []
        if graph_a:
            try:
                order_a = list(nx.topological_sort(graph_a))
            except (nx.NetworkXUnfeasible, nx.NetworkXError):
                order_a = list(graph_a.nodes)
            nodes_a = [graph_a.nodes[n] for n in order_a]

        nodes_b: List[Dict[str, Any]] = []
        if graph_b:
            try:
                order_b = list(nx.topological_sort(graph_b))
            except (nx.NetworkXUnfeasible, nx.NetworkXError):
                order_b = list(graph_b.nodes)
            nodes_b = [graph_b.nodes[n] for n in order_b]

        names_a = [n.get("op_name", "") for n in nodes_a]
        names_b = [n.get("op_name", "") for n in nodes_b]

        matcher = difflib.SequenceMatcher(None, names_a, names_b)
        rows: List[DiffRow] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for a_idx, b_idx in zip(range(i1, i2), range(j1, j2)):
                    na = nodes_a[a_idx]
                    nb = nodes_b[b_idx]
                    h_a = na.get("output_hash") or ""
                    h_b = nb.get("output_hash") or ""
                    in_a = na.get("input_hash") or ""
                    in_b = nb.get("input_hash") or ""
                    if h_a == h_b and in_a == in_b:
                        rows.append(DiffRow("SAME", na.get("op_name", ""), na, nb))
                    else:
                        rows.append(DiffRow("CHANGED", na.get("op_name", ""), na, nb))
            elif tag == "replace":
                len_a = i2 - i1
                len_b = j2 - j1
                min_len = min(len_a, len_b)
                for off in range(min_len):
                    na = nodes_a[i1 + off]
                    nb = nodes_b[j1 + off]
                    if na.get("op_name") == nb.get("op_name"):
                        rows.append(DiffRow("CHANGED", na.get("op_name", ""), na, nb))
                    else:
                        rows.append(DiffRow("REMOVED", na.get("op_name", ""), na, None))
                        rows.append(DiffRow("ADDED", nb.get("op_name", ""), None, nb))
                if len_a > min_len:
                    for a_idx in range(i1 + min_len, i2):
                        rows.append(DiffRow("REMOVED", nodes_a[a_idx].get("op_name", ""), nodes_a[a_idx], None))
                elif len_b > min_len:
                    for b_idx in range(j1 + min_len, j2):
                        rows.append(DiffRow("ADDED", nodes_b[b_idx].get("op_name", ""), None, nodes_b[b_idx]))
            elif tag == "delete":
                for a_idx in range(i1, i2):
                    rows.append(DiffRow("REMOVED", nodes_a[a_idx].get("op_name", ""), nodes_a[a_idx], None))
            elif tag == "insert":
                for b_idx in range(j1, j2):
                    rows.append(DiffRow("ADDED", nodes_b[b_idx].get("op_name", ""), None, nodes_b[b_idx]))

        return rows

    def get_summary_stats(self) -> Tuple[int, int, int, int]:
        unchanged = sum(1 for r in self.rows if r.state == "SAME")
        changed = sum(1 for r in self.rows if r.state == "CHANGED")
        added = sum(1 for r in self.rows if r.state == "ADDED")
        removed = sum(1 for r in self.rows if r.state == "REMOVED")
        return unchanged, changed, added, removed

    def watch_selected_index(self, old_val: int, new_val: int) -> None:
        self.refresh()

    def action_cursor_down(self) -> None:
        if self.rows and self.selected_index < len(self.rows) - 1:
            self.selected_index += 1

    def action_cursor_up(self) -> None:
        if self.rows and self.selected_index > 0:
            self.selected_index -= 1

    def action_next_diff(self) -> None:
        for idx in range(self.selected_index + 1, len(self.rows)):
            if self.rows[idx].state != "SAME":
                self.selected_index = idx
                return

    def action_prev_diff(self) -> None:
        for idx in range(self.selected_index - 1, -1, -1):
            if self.rows[idx].state != "SAME":
                self.selected_index = idx
                return

    def action_activate_row(self) -> None:
        if 0 <= self.selected_index < len(self.rows):
            row = self.rows[self.selected_index]
            if row.state == "CHANGED":
                self.post_message(self.RowActivated(row))

    def render(self) -> Text:
        if not self.rows:
            return Text("  No diff data loaded.", style=TEXT_MUTED)

        total_width = self.size.width if self.size.width > 0 else 80
        col_width = max(10, (total_width - 3) // 2)

        output = Text()
        for idx, row in enumerate(self.rows):
            is_selected = idx == self.selected_index

            left_str = ""
            right_str = ""

            if row.state == "SAME":
                h = truncate_hash(row.node_a.get("output_hash") if row.node_a else "")
                left_str = f"    {row.op_name} [{h}]"
                right_str = f"    {row.op_name} [{h}]"
                color = TEXT_SECONDARY
            elif row.state == "CHANGED":
                ha = truncate_hash(row.node_a.get("output_hash") if row.node_a else "")
                hb = truncate_hash(row.node_b.get("output_hash") if row.node_b else "")
                left_str = f"  ~ {row.op_name} [{ha}]"
                right_str = f"  ~ {row.op_name} [{hb}]"
                color = ACCENT_BRIGHT
            elif row.state == "ADDED":
                hb = truncate_hash(row.node_b.get("output_hash") if row.node_b else "")
                left_str = "    -"
                right_str = f"  + {row.op_name} [{hb}]"
                color = ACCENT
            else:  # REMOVED
                ha = truncate_hash(row.node_a.get("output_hash") if row.node_a else "")
                left_str = f"  - {row.op_name} [{ha}]"
                right_str = "    -"
                color = ERROR

            left_formatted = left_str[:col_width].ljust(col_width)
            right_formatted = right_str[:col_width].ljust(col_width)

            if is_selected:
                row_text = Text(f"{left_formatted} │ {right_formatted}\n", style=f"{BACKGROUND} on {ACCENT}")
            else:
                row_text = Text()
                row_text.append(left_formatted, style=color)
                row_text.append(" │ ", style=BORDER)
                row_text.append(f"{right_formatted}\n", style=color)

            output.append_text(row_text)

        return output
