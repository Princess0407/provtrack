import json
from fastapi.testclient import TestClient

from provtrack.cli import main, _safe_open
from provtrack.graph.builder import LineageGraph
from provtrack.logger import OperationRecord


def _make_session_file(tmp_path, name="session.json"):
    rec1 = OperationRecord(id="op-1", op_name="read_csv", output_hash="h1", source_file="app.py", source_line=1)
    rec2 = OperationRecord(id="op-2", op_name="dropna", input_hash="h1", output_hash="h2", source_file="app.py", source_line=2)
    graph = LineageGraph.from_records([rec1, rec2])

    path = tmp_path / name
    path.write_text(graph.to_json(), encoding="utf-8")
    return str(path)


def test_cli_report(tmp_path, capsys):
    f = _make_session_file(tmp_path)
    main(["report", "--file", f])
    captured = capsys.readouterr()
    assert "PROVTRACK LINEAGE REPORT" in captured.out
    assert "dropna" in captured.out


def test_cli_export(tmp_path, capsys):
    f = _make_session_file(tmp_path)

    main(["export", "--file", f, "--format", "json"])
    out_json = capsys.readouterr().out
    assert "nodes" in out_json

    main(["export", "--file", f, "--format", "dot"])
    out_dot = capsys.readouterr().out
    assert "digraph" in out_dot

    main(["export", "--file", f, "--format", "mermaid"])
    out_mermaid = capsys.readouterr().out
    assert "flowchart LR" in out_mermaid

    main(["export", "--file", f, "--format", "openlineage"])
    out_ol = capsys.readouterr().out
    assert "provtrack.pipeline" in out_ol


def test_cli_query(tmp_path, capsys):
    f = _make_session_file(tmp_path)
    main(["query", "--file", f, "--op", "dropna"])
    captured = capsys.readouterr()
    assert "dropna" in captured.out


def test_cli_diff(tmp_path, capsys):
    f1 = _make_session_file(tmp_path, "s1.json")
    f2 = _make_session_file(tmp_path, "s2.json")
    main(["diff", "--a", f1, "--b", f2])
    captured = capsys.readouterr()
    assert "PROVTRACK SESSION DIFF" in captured.out
    assert "Structural change: NO" in captured.out


def test_cli_validate(tmp_path, capsys):
    f = _make_session_file(tmp_path)
    main(["validate", "--file", f])
    captured = capsys.readouterr()
    assert "Valid DAG: True" in captured.out


def test_cli_serve_fastapi(tmp_path):
    f = _make_session_file(tmp_path)
    data = _safe_open(f)

    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/graph")
    def get_graph():
        return data

    client = TestClient(app)
    response = client.get("/graph")
    assert response.status_code == 200
    res_data = response.json()
    assert "nodes" in res_data
    assert len(res_data["nodes"]) == 2
