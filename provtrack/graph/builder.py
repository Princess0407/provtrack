from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, Generator, List, Optional, Tuple

import networkx as nx

from provtrack.logger import OperationRecord


class LineageGraph:
    __slots__ = ("_g", "_output_index", "_input_index", "_seen_ids")

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()
        self._output_index: Dict[str, List[str]] = defaultdict(list)
        self._input_index: Dict[str, List[str]] = defaultdict(list)
        self._seen_ids: set[str] = set()

    def add_record(self, rec: OperationRecord) -> None:
        if rec.id in self._seen_ids:
            return
        self._seen_ids.add(rec.id)

        attrs = rec.to_dict()
        self._g.add_node(rec.id, **attrs)

        if rec.input_hash:
            for parent_id in self._output_index.get(rec.input_hash, []):
                if parent_id != rec.id:
                    self._g.add_edge(parent_id, rec.id, data_hash=rec.input_hash)
            self._input_index[rec.input_hash].append(rec.id)

        if rec.output_hash:
            for child_id in self._input_index.get(rec.output_hash, []):
                if child_id != rec.id:
                    self._g.add_edge(rec.id, child_id, data_hash=rec.output_hash)
            self._output_index[rec.output_hash].append(rec.id)

    @classmethod
    def from_records(cls, records: List[OperationRecord]) -> LineageGraph:
        g = cls()
        for rec in records:
            g.add_record(rec)
        return g

    @property
    def node_count(self) -> int:
        return self._g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._g.number_of_edges()

    @property
    def raw_graph(self) -> nx.DiGraph:
        return self._g

    def nodes(self) -> List[Dict[str, Any]]:
        return [self._g.nodes[n] for n in self._g.nodes]

    def edges(self) -> List[Tuple[str, str, Dict[str, Any]]]:
        return list(self._g.edges(data=True))

    def ancestors_of(self, op_id: str) -> List[str]:
        return list(nx.ancestors(self._g, op_id))

    def descendants_of(self, op_id: str) -> List[str]:
        return list(nx.descendants(self._g, op_id))

    def roots(self) -> List[str]:
        return [n for n in self._g.nodes if self._g.in_degree(n) == 0]

    def leaves(self) -> List[str]:
        return [n for n in self._g.nodes if self._g.out_degree(n) == 0]

    def path_between(self, src_op_id: str, dst_op_id: str) -> Optional[List[str]]:
        try:
            return nx.shortest_path(self._g, src_op_id, dst_op_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def topological_order(self) -> Generator[str, None, None]:
        yield from nx.topological_sort(self._g)

    def ops_by_name(self, op_name: str) -> List[Dict[str, Any]]:
        return [
            self._g.nodes[n]
            for n in self._g.nodes
            if self._g.nodes[n].get("op_name") == op_name
        ]

    def ops_touching_data(self, data_hash: str) -> List[Dict[str, Any]]:
        results = []
        for n in self._g.nodes:
            attrs = self._g.nodes[n]
            if attrs.get("input_hash") == data_hash or attrs.get("output_hash") == data_hash:
                results.append(attrs)
        return results

    def is_valid_dag(self) -> bool:
        return nx.is_directed_acyclic_graph(self._g)

    def to_json(self, indent: int = 2) -> str:
        nodes = [self._g.nodes[n] for n in self._g.nodes]
        edges = [
            {"from": src, "to": dst, "data_hash": data.get("data_hash", "")}
            for src, dst, data in self._g.edges(data=True)
        ]
        return json.dumps({"nodes": nodes, "edges": edges}, indent=indent, default=str)

    def to_dot(self) -> str:
        lines = ["digraph provenance {", '  rankdir="LR";', '  node [shape=box];']
        for n in self._g.nodes:
            attrs = self._g.nodes[n]
            label = (
                f"{attrs.get('op_name', '?')}\\n"
                f"{attrs.get('obj_type', '')}\\n"
                f"{attrs.get('short_op_id', n[:8])}"
            )
            lines.append(f'  "{n}" [label="{label}"];')
        for src, dst, data in self._g.edges(data=True):
            h = (data.get("data_hash") or "")[:8]
            lines.append(f'  "{src}" -> "{dst}" [label="{h}"];')
        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        lines = ["flowchart LR"]

        def _nid(full_id: str) -> str:
            return "n" + full_id.replace("-", "")[:12]

        for n in self._g.nodes:
            attrs = self._g.nodes[n]
            op = attrs.get("op_name", "?")
            line = attrs.get("caller_line") or attrs.get("source_line", "")
            tags = attrs.get("tags", [])
            label = op + (f"\\nline {line}" if line else "")
            nid = _nid(n)
            if "sklearn" in tags:
                lines.append(f'  {nid}(["{label}"])')
            else:
                lines.append(f'  {nid}["{label}"]')

        seen_edges: set = set()
        for src, dst, data in self._g.edges(data=True):
            key = (src, dst)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            h = (data.get("data_hash") or "")[:8]
            lines.append(f'  {_nid(src)} -->|"{h}"| {_nid(dst)}')

        return "\n".join(lines)

    def summary(self) -> str:
        if self.node_count == 0:
            return "No operations recorded."

        all_ops = [self._g.nodes[n].get("op_name", "?") for n in self.topological_order()]
        seen: dict[str, int] = {}
        for op in all_ops:
            seen[op] = seen.get(op, 0) + 1

        unique_in_order = list(dict.fromkeys(all_ops))
        annotated = [
            f"{op}(×{seen[op]})" if seen[op] > 1 else op for op in unique_in_order
        ]

        timing_lines = []
        for op_name, count in sorted(seen.items(), key=lambda x: -x[1]):
            durations = [
                self._g.nodes[n].get("duration_ms", 0.0)
                for n in self._g.nodes
                if self._g.nodes[n].get("op_name") == op_name
            ]
            avg_ms = sum(durations) / len(durations) if durations else 0.0
            timing_lines.append(f"  {op_name:<20} {count:>3}×   avg {avg_ms:.1f} ms")

        timing_block = "\n".join(timing_lines)
        return (
            f"Pipeline: {self.node_count} operations, {self.edge_count} data-flow edges\n"
            f"Sequence: {' → '.join(annotated)}\n\n"
            f"Operation breakdown:\n{timing_block}"
        )

    def __repr__(self) -> str:
        return f"<ProvenanceGraph nodes={self.node_count} edges={self.edge_count} valid_dag={self.is_valid_dag()}>"


ProvenanceGraph = LineageGraph


class GraphBuilder:
    __slots__ = ()

    @staticmethod
    def build(records: List[OperationRecord]) -> LineageGraph:
        return LineageGraph.from_records(records)


def build_graph(records: List[OperationRecord]) -> LineageGraph:
    return GraphBuilder.build(records)
