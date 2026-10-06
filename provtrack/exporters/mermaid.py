from __future__ import annotations

from provtrack.graph.builder import LineageGraph


def export_mermaid(graph: LineageGraph) -> str:
    return graph.to_mermaid()
