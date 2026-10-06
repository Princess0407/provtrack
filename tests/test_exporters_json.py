import json

from provtrack.exporters.json import export_json, import_json
from provtrack.graph.builder import LineageGraph
from provtrack.logger import OperationRecord


def test_export_and_import_json():
    rec1 = OperationRecord(id="op-1", op_name="read_csv", output_hash="h1")
    rec2 = OperationRecord(id="op-2", op_name="dropna", input_hash="h1", output_hash="h2")
    graph = LineageGraph.from_records([rec1, rec2])

    json_str = export_json(graph)
    data = json.loads(json_str)
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1

    imported_graph = import_json(json_str)
    assert imported_graph.node_count == 2
    assert imported_graph.edge_count == 1
    assert imported_graph.is_valid_dag()
