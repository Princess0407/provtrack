from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import networkx as nx
from rich.text import Text

from provtrack.tui.theme import ACCENT, BACKGROUND, BORDER, TEXT_MUTED, TEXT_PRIMARY


def layout_dag(graph: nx.DiGraph) -> List[Tuple[str, int, int, str]]:
    if not graph.number_of_nodes():
        return []

    try:
        order = list(nx.topological_sort(graph))
    except (nx.NetworkXUnfeasible, nx.NetworkXError):
        # Fallback to insertion order if cycles are present
        order = list(graph.nodes)

    insertion_idx: Dict[str, int] = {node_id: i for i, node_id in enumerate(graph.nodes)}
    layers: Dict[str, int] = {}

    for node_id in order:
        preds = list(graph.predecessors(node_id))
        if not preds:
            layers[node_id] = 0
        else:
            layers[node_id] = 1 + max((layers.get(p, 0) for p in preds), default=-1)

    by_layer: Dict[int, List[str]] = defaultdict(list)
    for node_id, layer_idx in layers.items():
        by_layer[layer_idx].append(node_id)

    for layer_idx in by_layer:
        by_layer[layer_idx].sort(key=lambda n: insertion_idx.get(n, 0))

    layout_items: List[Tuple[str, int, int, str]] = []
    for layer_idx in sorted(by_layer.keys()):
        for col_idx, node_id in enumerate(by_layer[layer_idx]):
            attrs = graph.nodes[node_id]
            op_name = attrs.get("op_name") or "op"
            h = (attrs.get("output_hash") or attrs.get("input_hash") or node_id)[:8]
            label = f"{op_name} [{h}]"
            layout_items.append((node_id, col_idx, layer_idx, label))

    return layout_items


compute_dag_layout = layout_dag


def render_ascii_dag(
    graph: nx.DiGraph,
    selected_id: Optional[str] = None,
    fallback_plain: bool = False,
    query_filter: Optional[str] = None,
) -> Tuple[Text, List[str]]:
    layout_items = layout_dag(graph)
    if not layout_items:
        return Text("  No operations recorded.", style=TEXT_MUTED), []

    ordered_node_ids = [item[0] for item in layout_items]
    if query_filter:
        q = query_filter.lower()
        matched = [
            item[0]
            for item in layout_items
            if q in str(graph.nodes[item[0]].get("op_name", "")).lower()
        ]
        if matched:
            ordered_node_ids = matched

    text = Text()

    if fallback_plain:
        for node_id in ordered_node_ids:
            attrs = graph.nodes[node_id]
            op_name = attrs.get("op_name") or "op"
            h = (attrs.get("output_hash") or attrs.get("input_hash") or node_id)[:8]
            is_selected = node_id == selected_id

            if is_selected:
                text.append(f"  • {op_name} [{h}]\n", style=f"{BACKGROUND} on {ACCENT}")
            else:
                text.append("  • ", style=BORDER)
                text.append(f"{op_name} ", style=TEXT_PRIMARY)
                text.append(f"[{h}]\n", style=TEXT_MUTED)
        return text, ordered_node_ids

    by_layer: Dict[int, List[Tuple[str, int, str]]] = defaultdict(list)
    for node_id, col, row, label in layout_items:
        if query_filter and node_id not in ordered_node_ids:
            continue
        by_layer[row].append((node_id, col, label))

    layer_indices = sorted(by_layer.keys())
    col_width = 30

    for idx, layer_idx in enumerate(layer_indices):
        nodes_in_row = by_layer[layer_idx]
        row_text = Text()
        center_positions: List[int] = []

        for node_id, col, label in nodes_in_row:
            target_col = col * col_width + 2
            current_len = len(row_text.plain)
            if current_len < target_col:
                row_text.append(" " * (target_col - current_len))

            attrs = graph.nodes[node_id]
            op_name = attrs.get("op_name") or "op"
            h = (attrs.get("output_hash") or attrs.get("input_hash") or node_id)[:8]
            node_label = f"{op_name} [{h}]"
            node_center = len(row_text.plain) + len(node_label) // 2
            center_positions.append(node_center)

            if node_id == selected_id:
                row_text.append(f" {node_label} ", style=f"{BACKGROUND} on {ACCENT}")
            else:
                row_text.append(f" {op_name} ", style=TEXT_PRIMARY)
                row_text.append(f"[{h}] ", style=TEXT_MUTED)

        row_text.append("\n")
        text.append_text(row_text)

        if idx < len(layer_indices) - 1:
            conn_line = Text()
            for c in center_positions:
                curr = len(conn_line.plain)
                if curr < c:
                    conn_line.append(" " * (c - curr))
                conn_line.append("│", style=BORDER)
            conn_line.append("\n")
            text.append_text(conn_line)

            arrow_line = Text()
            for c in center_positions:
                curr = len(arrow_line.plain)
                if curr < c:
                    arrow_line.append(" " * (c - curr))
                arrow_line.append("▼", style=BORDER)
            arrow_line.append("\n")
            text.append_text(arrow_line)

    return text, ordered_node_ids
