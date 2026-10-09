from __future__ import annotations

import os
from typing import Any, Dict, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from provtrack.tui.theme import BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from provtrack.tui.utils.formatter import format_duration, truncate_hash


class OpCard(Widget):
    node: reactive[Optional[Dict[str, Any]]] = reactive(None)

    def __init__(self, node: Optional[Dict[str, Any]] = None, id: str | None = None) -> None:
        super().__init__(id=id)
        self.node = node

    def update_node(self, node: Optional[Dict[str, Any]]) -> None:
        self.node = node

    def render(self) -> Panel:
        if not self.node:
            content = Text("No operation selected", style=TEXT_MUTED)
            return Panel(content, title="Operation", border_style=BORDER)

        op_name = self.node.get("op_name") or "unknown"
        input_hash = self.node.get("input_hash")
        output_hash = self.node.get("output_hash") or ""
        src_file = self.node.get("source_file") or self.node.get("caller_file") or ""
        src_line = self.node.get("source_line") or self.node.get("caller_line") or 0
        src_str = f"{os.path.basename(src_file)}:{src_line}" if src_file else "-"
        duration_ms = self.node.get("duration_ms", 0.0)
        tags = self.node.get("tags") or ()
        tags_str = ", ".join(tags) if isinstance(tags, (list, tuple)) else str(tags)
        args_repr = self.node.get("args_repr") or self.node.get("kwargs_repr") or "-"

        in_h_str = f"{truncate_hash(input_hash, 8)}..." if input_hash else "-"
        out_h_str = f"{truncate_hash(output_hash, 8)}..." if output_hash else "-"

        table = Table.grid(padding=(0, 2))
        table.add_column(style=TEXT_SECONDARY, justify="left", width=14)
        table.add_column(style=TEXT_PRIMARY, justify="left")

        table.add_row("Input hash", Text(in_h_str, style=TEXT_MUTED))
        table.add_row("Output hash", Text(out_h_str, style=TEXT_MUTED))
        table.add_row("Source", src_str)
        table.add_row("Duration", format_duration(duration_ms))
        table.add_row("Tags", tags_str if tags_str else "-")
        table.add_row("Args", str(args_repr))

        card_text = Text()
        card_text.append(f"{op_name}\n\n", style=f"bold {TEXT_PRIMARY}")

        body = Table.grid()
        body.add_row(card_text)
        body.add_row(table)

        return Panel(body, title="Operation", border_style=BORDER)
