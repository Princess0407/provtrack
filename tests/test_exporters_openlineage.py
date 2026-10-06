from provtrack.exporters.openlineage import export_openlineage
from provtrack.logger import OperationRecord


def test_export_openlineage_single_event():
    rec = OperationRecord(
        id="rec-1",
        op_name="read_csv",
        output_hash="hash-out",
        input_hash=None,
    )
    events = export_openlineage([rec], run_id="test-run-id")
    assert len(events) == 1
    ev = events[0]
    assert ev["eventType"] == "COMPLETE"
    assert ev["run"]["runId"] == "test-run-id"
    assert ev["job"]["name"] == "provtrack.pipeline"
    assert ev["inputs"] == []
    assert ev["outputs"] == [{"namespace": "provtrack", "name": "hash-out"}]


def test_export_openlineage_multi_events():
    rec1 = OperationRecord(id="rec-1", op_name="read_csv", output_hash="h1")
    rec2 = OperationRecord(id="rec-2", op_name="dropna", input_hash="h1", output_hash="h2")
    rec3 = OperationRecord(id="rec-3", op_name="reset_index", input_hash="h2", output_hash="h3")

    events = export_openlineage([rec1, rec2, rec3], run_id="my-run")
    assert len(events) == 3
    assert events[0]["eventType"] == "START"
    assert events[1]["eventType"] == "RUNNING"
    assert events[2]["eventType"] == "COMPLETE"
    assert events[1]["inputs"] == [{"namespace": "provtrack", "name": "h1"}]
    assert events[1]["outputs"] == [{"namespace": "provtrack", "name": "h2"}]
