"""
provtrack.graph
~~~~~~~~~~~~~~~
Builds and queries the provenance DAG from OperationRecords.

Design decisions:
  - networkx DiGraph is the backing structure.  Each node is an op_id;
    node attributes store the full OperationRecord dict.
  - Edges are keyed by (input_hash, output_hash) so two operations that share
    the same intermediate data are always linked correctly.
  - The graph is rebuilt lazily from the logger on each query — this keeps the
    graph.py concern purely structural and avoids tight coupling to the proxy.
  - export_json / export_dot / export_mermaid are built-in for zero-dependency
    visualisation.

Security guardrails:
  - No file I/O in this module.  Serialisation is handled by exporters only.
  - The graph is read-only after build(); mutation methods are private.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, Generator, List, Optional

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False
    nx = None  # type: ignore[assignment]

from .logger import OperationRecord

if TYPE_CHECKING:
    pass


# ── ProvenanceGraph ───────────────────────────────────────────────────────────

class ProvenanceGraph:
    """
    Directed Acyclic Graph of ML pipeline operations.

    Nodes
    -----
    op_id (str) — unique per operation, attributes = OperationRecord.to_dict()

    Edges
    -----
    (parent_op_id, child_op_id) — drawn when parent.output_hash == child.input_hash
    """

    def __init__(self) -> None:
        if not _HAS_NX:
            raise ImportError(
                "provtrack requires networkx. Install it with: pip install networkx"
            )
        self._g: "nx.DiGraph" = nx.DiGraph() # type: ignore
        self._output_index: Dict[str, List[str]] = defaultdict(list)
        self._input_index: Dict[str, List[str]] = defaultdict(list)
        self._dedup_seen: set = set()

    # ── build ─────────────────────────────────────────────────────────────────

    def add_record(self, rec: OperationRecord) -> None:
        """Insert one OperationRecord into the graph."""

        # ── deduplication ─────────────────────────────────────────────────────
        # If an operation with the same (op_name, input_hash, output_hash)
        # already exists, it's the same logical transformation logged twice
        # (e.g. pandas calling dropna internally during read_csv wrapping).
        # Keep only the first occurrence — discard the duplicate entirely.
        dedup_key = (rec.op_name, rec.input_hash, rec.output_hash)
        if dedup_key in self._dedup_seen:
            return
        self._dedup_seen.add(dedup_key)
        # ─────────────────────────────────────────────────────────────────────

        attrs = rec.to_dict()
        self._g.add_node(rec.op_id, **attrs)

        for parent_id in self._output_index.get(rec.input_hash, []):
            self._g.add_edge(parent_id, rec.op_id, data_hash=rec.input_hash)

        self._input_index[rec.input_hash].append(rec.op_id)
        if rec.output_hash:
            self._output_index[rec.output_hash].append(rec.op_id)
            for child_id in self._input_index.get(rec.output_hash, []):
                self._g.add_edge(rec.op_id, child_id, data_hash=rec.output_hash)

    @classmethod
    def from_records(cls, records: List[OperationRecord]) -> "ProvenanceGraph":
        """Build a graph from a list of OperationRecords (ordered by time)."""
        g = cls()
        for rec in records:
            g.add_record(rec)
        return g

    # ── query ─────────────────────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        return self._g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def nodes(self) -> List[Dict]:
        """Return all node attribute dicts (one per operation)."""
        return [self._g.nodes[n] for n in self._g.nodes]

    def ancestors_of(self, op_id: str) -> List[str]:
        """All op_ids that (transitively) produced the input to op_id."""
        return list(nx.ancestors(self._g, op_id))

    def descendants_of(self, op_id: str) -> List[str]:
        """All op_ids that (transitively) depend on op_id's output."""
        return list(nx.descendants(self._g, op_id))

    def roots(self) -> List[str]:
        """Nodes with no incoming edges (data sources)."""
        return [n for n in self._g.nodes if self._g.in_degree(n) == 0]

    def leaves(self) -> List[str]:
        """Nodes with no outgoing edges (final outputs)."""
        return [n for n in self._g.nodes if self._g.out_degree(n) == 0]

    def path_between(self, src_op_id: str, dst_op_id: str) -> Optional[List[str]]:
        """
        Return the shortest operation path from src to dst, or None if
        no path exists.
        """
        try:
            return nx.shortest_path(self._g, src_op_id, dst_op_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def topological_order(self) -> Generator[str, None, None]:
        """Yield op_ids in topological order (roots first)."""
        yield from nx.topological_sort(self._g)

    def ops_by_name(self, op_name: str) -> List[Dict]:
        """Return all nodes where op_name matches."""
        return [
            self._g.nodes[n]
            for n in self._g.nodes
            if self._g.nodes[n].get("op_name") == op_name
        ]

    def ops_touching_data(self, data_hash: str) -> List[Dict]:
        """Return all nodes whose input or output matches data_hash."""
        results = []
        for n in self._g.nodes:
            attrs = self._g.nodes[n]
            if attrs.get("input_hash") == data_hash or attrs.get("output_hash") == data_hash:
                results.append(attrs)
        return results

    def is_valid_dag(self) -> bool:
        """Return True if the graph is acyclic (sanity check)."""
        return nx.is_directed_acyclic_graph(self._g)

    # ── export ────────────────────────────────────────────────────────────────

    def to_json(self, indent: int = 2) -> str:
        """
        Serialise the graph to a JSON string.
        Format: {"nodes": [...], "edges": [...]}
        """
        nodes = []
        for n in self._g.nodes:
            nodes.append(self._g.nodes[n])

        edges = []
        for src, dst, data in self._g.edges(data=True):
            edges.append({
                "from": src,
                "to": dst,
                "data_hash": data.get("data_hash", ""),
            })

        return json.dumps({"nodes": nodes, "edges": edges}, indent=indent, default=str)

    def to_dot(self) -> str:
        """
        Graphviz DOT format.  Pipe through `dot -Tpng` to render.
        """
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
            h = data.get("data_hash", "")[:8]
            lines.append(f'  "{src}" -> "{dst}" [label="{h}"];')
        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """
        Mermaid flowchart — clean, human-readable labels.

        Node: op_name only (line N from user script shown as subtext)
        Edge: short 8-char data fingerprint (proves shared data state)
        Duplicate edges suppressed.
        """
        lines = ["flowchart LR"]

        def _nid(full_id: str) -> str:
            return "n" + full_id.replace("-", "")[:12]

        for n in self._g.nodes:
            attrs  = self._g.nodes[n]
            op     = attrs.get("op_name", "?")
            line   = attrs.get("caller_line", "")
            tags   = attrs.get("tags", [])
            label  = op + (f"\\nline {line}" if line else "")
            nid    = _nid(n)
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
        """
        Human-readable summary of the pipeline.

        Shows the unique operation names in topological order, with counts
        when an op appears more than once.  Much more readable than listing
        every node individually.
        """
        if self.node_count == 0:
            return "No operations recorded."

        # Collect op names in topological order.
        all_ops = [
            self._g.nodes[n].get("op_name", "?")
            for n in self.topological_order()
        ]

        # Deduplicate while preserving order, annotating repeats.
        seen: dict[str, int] = {}
        for op in all_ops:
            seen[op] = seen.get(op, 0) + 1

        unique_in_order = list(dict.fromkeys(all_ops))  # stable dedup
        annotated = [
            f"{op}(×{seen[op]})" if seen[op] > 1 else op
            for op in unique_in_order
        ]

        # Per-op timing summary.
        timing_lines = []
        for op_name, count in sorted(seen.items(), key=lambda x: -x[1]):
            durations = [
                self._g.nodes[n].get("duration_ms", 0)
                for n in self._g.nodes
                if self._g.nodes[n].get("op_name") == op_name
            ]
            avg_ms = sum(durations) / len(durations) if durations else 0
            timing_lines.append(f"  {op_name:<20} {count:>3}×   avg {avg_ms:.1f} ms")

        timing_block = "\n".join(timing_lines)

        return (
            f"Pipeline: {self.node_count} operations, {self.edge_count} data-flow edges\n"
            f"Sequence: {' → '.join(annotated)}\n\n"
            f"Operation breakdown:\n{timing_block}"
        )

    def __repr__(self) -> str:
        return (
            f"<ProvenanceGraph nodes={self.node_count} edges={self.edge_count} "
            f"valid_dag={self.is_valid_dag()}>"
        )