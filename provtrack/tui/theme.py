from __future__ import annotations

from typing import Dict

BACKGROUND = "#1a1a1a"
SURFACE = "#2d2d2d"
BORDER = "#3d3d3d"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#9e9e9e"
TEXT_MUTED = "#616161"
ACCENT = "#78909c"
ACCENT_BRIGHT = "#b0bec5"
SUCCESS = "#546e7a"
WARNING = "#78716c"
ERROR = "#6d4c4c"

COLOR_MAP: Dict[str, str] = {
    "background": BACKGROUND,
    "surface": SURFACE,
    "border": BORDER,
    "text-primary": TEXT_PRIMARY,
    "text-secondary": TEXT_SECONDARY,
    "text-muted": TEXT_MUTED,
    "text-accent": ACCENT,
    "accent": ACCENT,
    "text-highlight": ACCENT_BRIGHT,
    "accent-bright": ACCENT_BRIGHT,
    "success": SUCCESS,
    "warning": WARNING,
    "error": ERROR,
    "same": TEXT_SECONDARY,
    "changed": ACCENT_BRIGHT,
    "added": ACCENT,
    "removed": ERROR,
    "selected": ACCENT,
}

DEFAULT_CSS = f"""
$background: {BACKGROUND};
$surface: {SURFACE};
$border: {BORDER};
$text-primary: {TEXT_PRIMARY};
$text-secondary: {TEXT_SECONDARY};
$text-muted: {TEXT_MUTED};
$accent: {ACCENT};
$accent-bright: {ACCENT_BRIGHT};
$success: {SUCCESS};
$warning: {WARNING};
$error: {ERROR};

Screen {{
    background: $background;
    color: $text-primary;
}}

ProvtrackApp {{
    background: $background;
    color: $text-primary;
}}

.panel {{
    background: $surface;
    border: solid $border;
}}

.text-primary {{
    color: $text-primary;
}}

.text-secondary {{
    color: $text-secondary;
}}

.text-muted {{
    color: $text-muted;
}}

.text-accent {{
    color: $accent;
}}

.text-highlight {{
    color: $accent-bright;
}}

.text-success {{
    color: $success;
}}

.text-warning {{
    color: $warning;
}}

.text-error {{
    color: $error;
}}

.selected {{
    background: $accent;
    color: $background;
}}

StatusBar {{
    dock: bottom;
    height: 1;
    background: $surface;
    color: $text-secondary;
}}

#dag-screen-container {{
    layout: horizontal;
    height: 1fr;
    width: 100%;
}}

#dag-left-panel {{
    width: 6fr;
    height: 100%;
    border-right: solid $border;
    layout: vertical;
}}

#dag-right-panel {{
    width: 4fr;
    height: 100%;
    layout: vertical;
}}

#dag-search-input {{
    dock: top;
    height: 3;
    background: $surface;
    border: solid $border;
    color: $text-primary;
    display: none;
}}

#dag-search-input.visible {{
    display: block;
}}

DAGWidget {{
    height: 1fr;
    width: 100%;
    overflow-y: auto;
    overflow-x: auto;
}}

OpCard {{
    background: $surface;
    border: solid $border;
    height: 100%;
    width: 100%;
    padding: 1;
    overflow-y: auto;
}}

#operation-screen-container {{
    layout: vertical;
    height: 1fr;
    width: 100%;
}}

#op-header {{
    height: auto;
    background: $surface;
    border-bottom: solid $border;
    padding: 1 2;
}}

#op-middle {{
    layout: horizontal;
    height: 1fr;
}}

#op-ancestors-panel {{
    width: 1fr;
    height: 100%;
    border-right: solid $border;
    padding: 1;
    overflow-y: auto;
}}

#op-descendants-panel {{
    width: 1fr;
    height: 100%;
    padding: 1;
    overflow-y: auto;
}}

#op-metadata-panel {{
    height: auto;
    min-height: 8;
    background: $surface;
    border-top: solid $border;
    padding: 1 2;
    overflow-y: auto;
}}

DiffPanel {{
    height: 1fr;
    width: 100%;
    layout: vertical;
}}

#diff-summary-bar {{
    height: 1;
    background: $surface;
    color: $text-secondary;
    border-bottom: solid $border;
    padding: 0 1;
}}

#diff-headers {{
    layout: horizontal;
    height: 1;
    background: $surface;
    color: $accent-bright;
    border-bottom: solid $border;
}}

#diff-header-a {{
    width: 1fr;
    border-right: solid $border;
    padding: 0 1;
}}

#diff-header-b {{
    width: 1fr;
    padding: 0 1;
}}

#diff-content {{
    height: 1fr;
    width: 100%;
    overflow-y: auto;
}}

HashTable {{
    height: 1fr;
    width: 100%;
    background: $surface;
}}

#inspector-screen-container {{
    layout: vertical;
    height: 1fr;
    width: 100%;
}}

#inspector-hash-display {{
    height: auto;
    background: $surface;
    border-bottom: solid $border;
    padding: 1 2;
}}

#inspector-table-container {{
    height: 1fr;
    width: 100%;
}}

#inspector-graph-container {{
    height: 12;
    background: $surface;
    border-top: solid $border;
    padding: 1 2;
    overflow-y: auto;
}}

ModalScreen {{
    align: center middle;
    background: rgba(26, 26, 26, 0.75);
}}

.modal-dialog {{
    width: 64;
    height: auto;
    background: $surface;
    border: solid $border;
    padding: 1 2;
}}
"""
