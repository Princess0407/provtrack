from __future__ import annotations

import os
from typing import Any, Dict, List

from rich.text import Text
from textual.widgets import DataTable

from provtrack.tui.theme import ACCENT, ACCENT_BRIGHT, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from provtrack.tui.utils.formatter import format_timestamp


class HashTable(DataTable):
    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id, cursor_type="row", zebra_stripes=False)
        self._columns_initialized = False

    def on_mount(self) -> None:
        if not self._columns_initialized:
            self.add_columns("Op Name", "Direction", "Timestamp", "Source")
            self._columns_initialized = True
        if hasattr(self, "_pending_records") and self._pending_records:
            recs, th = self._pending_records
            self.populate(recs, th)

    def populate(self, records: List[Dict[str, Any]], target_hash: str) -> None:
        self._pending_records = (records, target_hash)
        if not self.is_mounted:
            return
        self.clear()
        if not self._columns_initialized:
            self.add_columns("Op Name", "Direction", "Timestamp", "Source")
            self._columns_initialized = True

        for rec in records:
            op_name = rec.get("op_name") or "unknown"
            is_out = rec.get("output_hash") == target_hash
            direction = "OUT" if is_out else "IN"
            dir_style = ACCENT_BRIGHT if is_out else ACCENT

            ts_str = format_timestamp(rec.get("timestamp"))
            src_file = rec.get("source_file") or rec.get("caller_file") or ""
            src_line = rec.get("source_line") or rec.get("caller_line") or 0
            src_str = f"{os.path.basename(src_file)}:{src_line}" if src_file else "-"

            self.add_row(
                Text(op_name, style=TEXT_PRIMARY),
                Text(direction, style=dir_style),
                Text(ts_str, style=TEXT_MUTED),
                Text(src_str, style=TEXT_SECONDARY),
            )
