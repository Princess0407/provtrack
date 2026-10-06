from provtrack.exporters.dot import export_dot
from provtrack.graph.builder import LineageGraph
from provtrack.logger import OperationRecord


def test_export_dot():
    rec1 = OperationRecord(id="op-1", op_name="read_csv", output_hash="h1")
    rec2 = OperationRecord(id="op-2", op_name="dropna", input_hash="h1", output_hash="h2")
    graph = LineageGraph.from_records([rec1, rec2])

    dot_str = export_dot(graph)
    assert "digraph provenance" in dot_str
    assert '"op-1" -> "op-2"' in dot_str
