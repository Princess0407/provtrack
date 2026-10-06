from __future__ import annotations

from typing import Any, Dict, List, Optional

from .builder import LineageGraph


def ops_by_name(graph: LineageGraph, op_name: str) -> List[Dict[str, Any]]:
    return graph.ops_by_name(op_name)


def ops_touching_data(graph: LineageGraph, data_hash: str) -> List[Dict[str, Any]]:
    return graph.ops_touching_data(data_hash)


def path_between(graph: LineageGraph, src_op_id: str, dst_op_id: str) -> Optional[List[str]]:
    return graph.path_between(src_op_id, dst_op_id)


def ancestors_of(graph: LineageGraph, op_id: str) -> List[str]:
    return graph.ancestors_of(op_id)


def descendants_of(graph: LineageGraph, op_id: str) -> List[str]:
    return graph.descendants_of(op_id)


def roots(graph: LineageGraph) -> List[str]:
    return graph.roots()


def leaves(graph: LineageGraph) -> List[str]:
    return graph.leaves()
