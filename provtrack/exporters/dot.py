from __future__ import annotations

from provtrack.graph.builder import LineageGraph


def export_dot(graph: LineageGraph) -> str:
    return graph.to_dot()
