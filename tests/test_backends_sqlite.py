from provtrack.backends.sqlite import SQLiteBackend
from provtrack.logger import OperationRecord


def test_sqlite_backend_save_load_clear(tmp_path):
    db_file = tmp_path / "test_lineage.db"
    backend = SQLiteBackend(db_path=db_file)
    assert backend.load() == []

    rec = OperationRecord(
        id="rec-123",
        op_name="read_csv",
        output_hash="hash-out-1",
        input_hash=None,
        source_line=42,
        source_file="pipeline.py",
        tags=("pandas", "io"),
        args_repr="('data.csv',)",
    )
    backend.save([rec])

    loaded = backend.load()
    assert len(loaded) == 1
    r = loaded[0]
    assert r.id == "rec-123"
    assert r.op_name == "read_csv"
    assert r.input_hash is None
    assert r.output_hash == "hash-out-1"
    assert r.source_line == 42
    assert r.source_file == "pipeline.py"
    assert r.tags == ("pandas", "io")
    assert r.args_repr == "('data.csv',)"

    # Persistence check across instances
    backend2 = SQLiteBackend(db_path=db_file)
    assert len(backend2.load()) == 1

    backend2.clear()
    assert backend2.load() == []
