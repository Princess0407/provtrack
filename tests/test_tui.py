from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest
from rich.text import Text

from provtrack.cli import main
from provtrack.graph.builder import LineageGraph
from provtrack.logger import OperationRecord
from provtrack.tui.app import ProvtrackApp
from provtrack.tui.screens.dag import DAGScreen, ExportModal
from provtrack.tui.screens.diff import DiffScreen
from provtrack.tui.screens.inspector import InspectorScreen
from provtrack.tui.screens.operation import OperationScreen
from provtrack.tui.utils.dag_layout import layout_dag, render_ascii_dag
from provtrack.tui.utils.formatter import (
    color_span,
    format_duration,
    format_timestamp,
    truncate_hash,
)
from provtrack.tui.widgets.dag_graph import DAGWidget
from provtrack.tui.widgets.diff_panel import DiffPanel
from provtrack.tui.widgets.hash_table import HashTable
from provtrack.tui.widgets.op_card import OpCard
from provtrack.tui.widgets.status_bar import StatusBar


def _make_sessions(tmp_path: Path) -> tuple[Path, Path]:
    rec1 = OperationRecord(id="op-1", op_name="read_csv", output_hash="79fdb5c31234", source_file="train.py", source_line=10)
    rec2 = OperationRecord(id="op-2", op_name="dropna", input_hash="79fdb5c31234", output_hash="e3ac0ecc5678", source_file="train.py", source_line=14)
    rec3 = OperationRecord(id="op-3", op_name="filter", input_hash="e3ac0ecc5678", output_hash="e2cf87209012", source_file="train.py", source_line=20)
    g1 = LineageGraph.from_records([rec1, rec2, rec3])

    p1 = tmp_path / "session_1.json"
    p1.write_text(g1.to_json(), encoding="utf-8")

    rec2_mod = OperationRecord(id="op-2", op_name="dropna", input_hash="79fdb5c31234", output_hash="different_hash", source_file="train.py", source_line=14)
    rec4 = OperationRecord(id="op-4", op_name="rename", input_hash="different_hash", output_hash="rename_h", source_file="train.py", source_line=25)
    g2 = LineageGraph.from_records([rec1, rec2_mod, rec4])

    p2 = tmp_path / "session_2.json"
    p2.write_text(g2.to_json(), encoding="utf-8")

    return p1, p2


def test_formatter():
    assert truncate_hash("1234567890", 8) == "12345678"
    assert truncate_hash("abc", 8) == "abc"
    assert truncate_hash(None) == ""

    assert format_duration(0.5) == "< 1 ms"
    assert format_duration(3.7) == "3.7 ms"
    assert format_duration(1200.0) == "1.2 s"
    assert format_duration(None) == "< 1 ms"

    assert format_timestamp(1600000000.0) != ""
    assert format_timestamp(None) == ""

    span = color_span("test", "text-primary")
    assert isinstance(span, Text)
    assert span.plain == "test"


def test_dag_layout():
    g = nx.DiGraph()
    g.add_node("1", op_name="read_csv", output_hash="79fdb5c31234")
    g.add_node("2", op_name="dropna", output_hash="e3ac0ecc5678")
    g.add_edge("1", "2")

    items = layout_dag(g)
    assert len(items) == 2
    assert items[0][0] == "1"
    assert items[0][1] == 0
    assert items[0][2] == 0
    assert items[1][0] == "2"
    assert items[1][2] == 1

    text_wide, ordered = render_ascii_dag(g, fallback_plain=False)
    assert "│" in text_wide.plain
    assert "▼" in text_wide.plain
    assert ordered == ["1", "2"]

    text_narrow, _ = render_ascii_dag(g, fallback_plain=True)
    assert "•" in text_narrow.plain
    assert "│" not in text_narrow.plain


def test_widgets():
    status = StatusBar(screen_name="dag", session_file="test.json")
    rendered_status = status.render()
    assert "provtrack" in rendered_status.plain
    assert "dag" in rendered_status.plain
    assert "test.json" in rendered_status.plain

    card = OpCard()
    assert "No operation selected" in card.render().renderable.plain
    card.update_node({"op_name": "dropna", "output_hash": "e3ac0ecc", "duration_ms": 3.7})
    card_render = card.render()
    assert card.node is not None and card.node["op_name"] == "dropna"
    assert card_render.title == "Operation"

    g_a = nx.DiGraph()
    g_a.add_node("1", op_name="read_csv", output_hash="h1")
    g_a.add_node("2", op_name="dropna", output_hash="h2")

    g_b = nx.DiGraph()
    g_b.add_node("1", op_name="read_csv", output_hash="h1")
    g_b.add_node("2", op_name="dropna", output_hash="h9")
    g_b.add_node("3", op_name="filter", output_hash="h3")

    panel = DiffPanel()
    panel.set_data(g_a, g_b)
    unchanged, changed, added, removed = panel.get_summary_stats()
    assert unchanged == 1
    assert changed == 1
    assert added == 1
    assert removed == 0

    table = HashTable()
    table.populate([{"op_name": "read_csv", "output_hash": "h1", "input_hash": None}], "h1")
    assert table._pending_records[1] == "h1"


def test_app_dag_and_operation_screens(tmp_path: Path):
    import asyncio

    async def _run():
        p1, _ = _make_sessions(tmp_path)
        app = ProvtrackApp(session_file=p1)

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause(0.1)
            dag_widget = app.screen.query_one(DAGWidget)
            dag_widget.focus()
            assert isinstance(app.screen, DAGScreen)

            await pilot.press("j")
            await pilot.pause(0.05)
            await pilot.press("k")
            await pilot.pause(0.05)

            # View operation screen
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert isinstance(app.screen, OperationScreen)

            # Navigate within operation screen
            await pilot.press("a")
            await pilot.pause(0.05)
            await pilot.press("d")
            await pilot.pause(0.05)

            # Back to DAG
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert isinstance(app.screen, DAGScreen)

            # Test search filter
            await pilot.press("slash")
            await pilot.pause(0.1)
            await pilot.press("d", "r", "o", "p")
            await pilot.pause(0.1)
            await pilot.press("enter")
            await pilot.pause(0.1)

            # Test export modal
            await pilot.press("e")
            await pilot.pause(0.2)
            assert isinstance(app.screen, ExportModal)
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert isinstance(app.screen, DAGScreen)

            # Test switch to Diff
            await pilot.press("2")
            await pilot.pause(0.2)
            assert isinstance(app.screen, DiffScreen)

            # Test switch to Inspector
            await pilot.press("3")
            await pilot.pause(0.2)
            assert isinstance(app.screen, InspectorScreen)

            # Test help modal
            await pilot.press("question_mark")
            await pilot.pause(0.2)
            await pilot.press("escape")
            await pilot.pause(0.2)

    asyncio.run(_run())


def test_app_diff_screen(tmp_path: Path):
    import asyncio

    async def _run():
        p1, p2 = _make_sessions(tmp_path)
        app = ProvtrackApp(diff_a=p1, diff_b=p2)

        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause(0.1)
            diff_panel = app.screen.query_one(DiffPanel)
            diff_panel.focus()
            assert isinstance(app.screen, DiffScreen)

            # Jump to next diff
            await pilot.press("n")
            await pilot.pause(0.1)

            # Enter to inspect
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert isinstance(app.screen, InspectorScreen)

            # Copy hash
            await pilot.press("c")
            await pilot.pause(0.1)

            # Back to diff screen
            await pilot.press("b")
            await pilot.pause(0.2)
            assert isinstance(app.screen, DiffScreen)

    asyncio.run(_run())


def test_cli_tui_args(tmp_path: Path):
    p1, p2 = _make_sessions(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["tui"])
    assert exc_info.value.code == 1

    with patch("provtrack.tui.app.ProvtrackApp.run") as mock_run:
        main(["tui", "--file", str(p1)])
        assert mock_run.called

    with patch("provtrack.tui.app.ProvtrackApp.run") as mock_run_diff:
        main(["tui", "--a", str(p1), "--b", str(p2)])
        assert mock_run_diff.called
