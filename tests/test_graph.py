"""
tests.test_graph
~~~~~~~~~~~~~~~~
Tests for ProvenanceGraph — construction, querying, export formats.
"""

from __future__ import annotations

import json
import uuid

import pytest

from provtrack.graph import ProvenanceGraph
from provtrack.logger import OperationRecord


def _make_record(
    op_name: str,
    input_hash: str,
    output_hash: str | None = None,
    obj_type: str = "DataFrame",
) -> OperationRecord:
    return OperationRecord(
        op_id=str(uuid.uuid4()),
        op_name=op_name,
        obj_type=obj_type,
        input_hash=input_hash,
        output_hash=output_hash,
        args_repr="()",
        kwargs_repr="{}",
        caller_file="test.py",
        caller_line=1,
        caller_func="test_fn",
        timestamp="2026-01-01T00:00:00+00:00",
        duration_ms=1.0,
        tags=("pandas",),
    )


# ── construction ──────────────────────────────────────────────────────────────

def test_empty_graph():
    g = ProvenanceGraph()
    assert g.node_count == 0
    assert g.edge_count == 0


def test_add_single_record():
    g = ProvenanceGraph()
    rec = _make_record("read_csv", "__source__", "hash_A")
    g.add_record(rec)
    assert g.node_count == 1
    assert g.edge_count == 0


def test_chain_builds_edges():
    g = ProvenanceGraph()
    r1 = _make_record("read_csv", "__source__", "hash_A")
    r2 = _make_record("dropna", "hash_A", "hash_B")
    r3 = _make_record("reset_index", "hash_B", "hash_C")
    for r in [r1, r2, r3]:
        g.add_record(r)

    assert g.node_count == 3
    assert g.edge_count == 2


def test_from_records():
    records = [
        _make_record("read_csv", "__source__", "hash_A"),
        _make_record("dropna", "hash_A", "hash_B"),
    ]
    g = ProvenanceGraph.from_records(records)
    assert g.node_count == 2
    assert g.edge_count == 1


# ── querying ──────────────────────────────────────────────────────────────────

def test_roots_and_leaves():
    g = ProvenanceGraph()
    r1 = _make_record("read_csv", "__source__", "hash_A")
    r2 = _make_record("dropna", "hash_A", "hash_B")
    for r in [r1, r2]:
        g.add_record(r)

    assert len(g.roots()) == 1
    assert len(g.leaves()) == 1
    assert g.roots()[0] == r1.op_id
    assert g.leaves()[0] == r2.op_id


def test_ops_by_name():
    g = ProvenanceGraph()
    g.add_record(_make_record("dropna", "h1", "h2"))
    g.add_record(_make_record("dropna", "h3", "h4"))
    g.add_record(_make_record("fillna", "h5", "h6"))

    assert len(g.ops_by_name("dropna")) == 2
    assert len(g.ops_by_name("fillna")) == 1
    assert len(g.ops_by_name("reset_index")) == 0


def test_ops_touching_data():
    g = ProvenanceGraph()
    r1 = _make_record("read_csv", "__source__", "hash_A")
    r2 = _make_record("dropna", "hash_A", "hash_B")
    for r in [r1, r2]:
        g.add_record(r)

    touching = g.ops_touching_data("hash_A")
    assert len(touching) == 2  # r1 produced it, r2 consumed it


def test_path_between():
    g = ProvenanceGraph()
    r1 = _make_record("read_csv", "__source__", "hash_A")
    r2 = _make_record("dropna", "hash_A", "hash_B")
    r3 = _make_record("filter", "hash_B", "hash_C")
    for r in [r1, r2, r3]:
        g.add_record(r)

    path = g.path_between(r1.op_id, r3.op_id)
    assert path is not None
    assert len(path) == 3


def test_path_between_nonexistent():
    g = ProvenanceGraph()
    r1 = _make_record("read_csv", "__source__", "hash_A")
    r2 = _make_record("dropna", "hash_X", "hash_Y")  # disconnected
    for r in [r1, r2]:
        g.add_record(r)

    path = g.path_between(r1.op_id, r2.op_id)
    assert path is None


def test_topological_order():
    g = ProvenanceGraph()
    r1 = _make_record("read_csv", "__source__", "hash_A")
    r2 = _make_record("dropna", "hash_A", "hash_B")
    r3 = _make_record("scale", "hash_B", "hash_C")
    for r in [r1, r2, r3]:
        g.add_record(r)

    order = list(g.topological_order())
    assert order.index(r1.op_id) < order.index(r2.op_id)
    assert order.index(r2.op_id) < order.index(r3.op_id)


def test_is_valid_dag_true():
    g = ProvenanceGraph()
    g.add_record(_make_record("read_csv", "src", "h1"))
    g.add_record(_make_record("dropna", "h1", "h2"))
    assert g.is_valid_dag() is True


# ── export ────────────────────────────────────────────────────────────────────

def test_to_json_valid():
    g = ProvenanceGraph()
    g.add_record(_make_record("read_csv", "__source__", "hash_A"))
    g.add_record(_make_record("dropna", "hash_A", "hash_B"))

    j = g.to_json()
    data = json.loads(j)
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1


def test_to_dot_contains_nodes():
    g = ProvenanceGraph()
    g.add_record(_make_record("read_csv", "src", "h1"))
    dot = g.to_dot()
    assert "digraph" in dot
    assert "read_csv" in dot


def test_to_mermaid_contains_flowchart():
    g = ProvenanceGraph()
    g.add_record(_make_record("dropna", "src", "h1"))
    mm = g.to_mermaid()
    assert "flowchart" in mm
    assert "dropna" in mm


def test_summary_non_empty_graph():
    g = ProvenanceGraph()
    g.add_record(_make_record("read_csv", "src", "h1"))
    g.add_record(_make_record("dropna", "h1", "h2"))
    s = g.summary()
    assert "2 operations" in s
    assert "read_csv" in s


def test_summary_empty_graph():
    g = ProvenanceGraph()
    assert "No operations" in g.summary()


# ── repr ──────────────────────────────────────────────────────────────────────

def test_repr():
    g = ProvenanceGraph()
    r = repr(g)
    assert "ProvenanceGraph" in r
    assert "nodes=0" in r
