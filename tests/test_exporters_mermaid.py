from provtrack.exporters.mermaid import export_mermaid
from provtrack.graph.builder import LineageGraph
from provtrack.logger import OperationRecord


def test_export_mermaid():
    rec1 = OperationRecord(id="op-1", op_name="read_csv", output_hash="h1")
    rec2 = OperationRecord(id="op-2", op_name="dropna", input_hash="h1", output_hash="h2")
    graph = LineageGraph.from_records([rec1, rec2])

    mermaid_str = export_mermaid(graph)
    assert "flowchart LR" in mermaid_str
    assert "read_csv" in mermaid_str
    assert "dropna" in mermaid_str
