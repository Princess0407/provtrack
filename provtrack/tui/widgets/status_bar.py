from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from provtrack.tui.theme import ACCENT, BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY


class StatusBar(Widget):
    screen_name: reactive[str] = reactive("dag")
    session_file: reactive[str] = reactive("")
    hints: reactive[str] = reactive("q quit  1 dag  2 diff  3 inspect  ? help")

    def __init__(
        self,
        screen_name: str = "dag",
        session_file: str = "",
        hints: str = "q quit  1 dag  2 diff  3 inspect  ? help",
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.screen_name = screen_name
        self.session_file = session_file
        self.hints = hints

    def render(self) -> Text:
        t = Text()
        t.append(" provtrack", style=TEXT_PRIMARY)
        t.append("  |  ", style=BORDER)
        t.append(self.screen_name, style=ACCENT)
        if self.session_file:
            t.append("  |  ", style=BORDER)
            t.append(self.session_file, style=TEXT_SECONDARY)

        right = Text(f"{self.hints} ", style=TEXT_MUTED)
        width = self.size.width if self.size.width > 0 else 80
        padding = max(1, width - len(t.plain) - len(right.plain))
        t.append(" " * padding)
        t.append_text(right)
        return t
