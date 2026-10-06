from __future__ import annotations

import json
from typing import Any, Dict, List

from provtrack.graph.builder import LineageGraph
from provtrack.logger import OperationRecord


def export_json(graph: LineageGraph, indent: int = 2) -> str:
    return graph.to_json(indent=indent)


def import_json(json_str: str) -> LineageGraph:
    data: Dict[str, Any] = json.loads(json_str)
    nodes: List[Dict[str, Any]] = data.get("nodes", [])

    records: List[OperationRecord] = []
    for node in nodes:
        rec = OperationRecord(
            id=node.get("id") or node.get("op_id"),
            op_name=node.get("op_name", ""),
            input_hash=node.get("input_hash"),
            output_hash=node.get("output_hash", ""),
            timestamp=node.get("timestamp"),
            source_line=node.get("source_line") or node.get("caller_line", 0),
            source_file=node.get("source_file") or node.get("caller_file", ""),
            tags=tuple(node.get("tags", [])),
            args_repr=node.get("args_repr", ""),
            kwargs_repr=node.get("kwargs_repr", ""),
            obj_type=node.get("obj_type", ""),
            caller_func=node.get("caller_func", ""),
            duration_ms=node.get("duration_ms", 0.0),
        )
        records.append(rec)

    return LineageGraph.from_records(records)
