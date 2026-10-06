from provtrack.graph.builder import LineageGraph
from provtrack.graph.diff import diff_graphs
from provtrack.logger import OperationRecord


def test_diff_graphs():
    rec1 = OperationRecord(id="op-1", op_name="read_csv", output_hash="h1")
    rec2 = OperationRecord(id="op-2", op_name="dropna", input_hash="h1", output_hash="h2")
    graph_a = LineageGraph.from_records([rec1, rec2])

    rec3 = OperationRecord(id="op-3", op_name="fillna", input_hash="h1", output_hash="h3")
    graph_b = LineageGraph.from_records([rec1, rec3])

    res = diff_graphs(graph_a, graph_b)
    assert res.shared_ops == ("read_csv",)
    assert res.added_ops == ("fillna",)
    assert res.removed_ops == ("dropna",)
    assert res.has_structural_change is True
    assert res.nodes_a == 2
    assert res.nodes_b == 2
