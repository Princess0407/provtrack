from __future__ import annotations

from datetime import datetime
from typing import Optional

from rich.text import Text

from provtrack.tui.theme import ACCENT, BACKGROUND, COLOR_MAP, TEXT_PRIMARY


def truncate_hash(h: Optional[str], n: int = 8) -> str:
    if not h:
        return ""
    return str(h)[:n]


def format_duration(ms: Optional[float]) -> str:
    if ms is None or ms < 1.0:
        return "< 1 ms"
    if ms >= 1000.0:
        return f"{ms / 1000.0:.1f} s"
    return f"{ms:.1f} ms"


def format_timestamp(ts: Optional[float]) -> str:
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def color_span(text: str, css_class: str) -> Text:
    if css_class == "selected":
        return Text(text, style=f"{BACKGROUND} on {ACCENT}")
    color = COLOR_MAP.get(css_class, TEXT_PRIMARY)
    return Text(text, style=color)
