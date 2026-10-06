from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .builder import LineageGraph


@dataclass(frozen=True, slots=True)
class DiffResult:
    shared_ops: Tuple[str, ...]
    added_ops: Tuple[str, ...]
    removed_ops: Tuple[str, ...]
    has_structural_change: bool
    nodes_a: int
    nodes_b: int
    edges_a: int
    edges_b: int


def diff_graphs(graph_a: LineageGraph, graph_b: LineageGraph) -> DiffResult:
    ops_a = {str(n.get("op_name", "")) for n in graph_a.nodes()}
    ops_b = {str(n.get("op_name", "")) for n in graph_b.nodes()}

    shared = tuple(sorted(ops_a & ops_b))
    added = tuple(sorted(ops_b - ops_a))
    removed = tuple(sorted(ops_a - ops_b))
    structural = bool(added or removed or graph_a.edge_count != graph_b.edge_count)

    return DiffResult(
        shared_ops=shared,
        added_ops=added,
        removed_ops=removed,
        has_structural_change=structural,
        nodes_a=graph_a.node_count,
        nodes_b=graph_b.node_count,
        edges_a=graph_a.edge_count,
        edges_b=graph_b.edge_count,
    )
