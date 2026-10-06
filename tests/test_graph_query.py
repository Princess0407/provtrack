from provtrack.graph.builder import LineageGraph
from provtrack.graph.query import (
    ancestors_of,
    descendants_of,
    leaves,
    ops_by_name,
    ops_touching_data,
    path_between,
    roots,
)
from provtrack.logger import OperationRecord


def test_query_functions():
    rec1 = OperationRecord(id="op-1", op_name="read_csv", output_hash="h1")
    rec2 = OperationRecord(id="op-2", op_name="dropna", input_hash="h1", output_hash="h2")
    rec3 = OperationRecord(id="op-3", op_name="reset_index", input_hash="h2", output_hash="h3")
    graph = LineageGraph.from_records([rec1, rec2, rec3])

    assert len(ops_by_name(graph, "dropna")) == 1
    assert len(ops_touching_data(graph, "h1")) == 2
    assert path_between(graph, "op-1", "op-3") == ["op-1", "op-2", "op-3"]
    assert ancestors_of(graph, "op-3") == ["op-2", "op-1"] or set(ancestors_of(graph, "op-3")) == {"op-1", "op-2"}
    assert descendants_of(graph, "op-1") == ["op-2", "op-3"] or set(descendants_of(graph, "op-1")) == {"op-2", "op-3"}
    assert roots(graph) == ["op-1"]
    assert leaves(graph) == ["op-3"]
