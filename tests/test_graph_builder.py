from provtrack.graph.builder import GraphBuilder, LineageGraph, build_graph
from provtrack.logger import OperationRecord


def test_builder_constructs_edges():
    rec1 = OperationRecord(
        id="op-1",
        op_name="read_csv",
        output_hash="hash-1",
        input_hash=None,
    )
    rec2 = OperationRecord(
        id="op-2",
        op_name="dropna",
        output_hash="hash-2",
        input_hash="hash-1",
    )
    graph = build_graph([rec1, rec2])

    assert isinstance(graph, LineageGraph)
    assert graph.node_count == 2
    assert graph.edge_count == 1
    assert graph.is_valid_dag()
    assert graph.roots() == ["op-1"]
    assert graph.leaves() == ["op-2"]


def test_builder_duplicate_ids_ignored():
    rec1 = OperationRecord(id="op-1", op_name="a", output_hash="h1")
    graph = GraphBuilder.build([rec1, rec1])
    assert graph.node_count == 1
