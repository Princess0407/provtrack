from __future__ import annotations

from typing import Optional

from provtrack.graph.builder import LineageGraph, ProvenanceGraph
from provtrack.proxies.base import BaseProxy
from provtrack.proxies.dataframe import DataFrameProxy
from provtrack.proxies.estimator import EstimatorProxy

_graph: Optional[ProvenanceGraph] = None


def get_graph() -> ProvenanceGraph:
    global _graph
    if _graph is None:
        _graph = ProvenanceGraph()
    return _graph


def reset_graph() -> None:
    global _graph
    _graph = ProvenanceGraph()


__all__ = [
    "BaseProxy",
    "DataFrameProxy",
    "EstimatorProxy",
    "get_graph",
    "reset_graph",
    "ProvenanceGraph",
    "LineageGraph",
]