import sys
import pandas as pd
import pytest

import provtrack
from provtrack.backends.sqlite import SQLiteBackend


def teardown_function():
    provtrack.deactivate()


def test_activate_sys_monitoring_memory_pipeline():
    provtrack.activate(backend="memory")
    assert provtrack.is_active()

    df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
    df2 = df.dropna()
    df3 = df2.reset_index(drop=True)

    records = provtrack.get_records()
    assert len(records) >= 2

    op_names = [r.op_name for r in records]
    assert "dropna" in op_names
    assert "reset_index" in op_names

    lineage = provtrack.lineage()
    assert lineage.node_count >= 2
    assert lineage.is_valid_dag()

    provtrack.deactivate()
    assert not provtrack.is_active()
    assert len(provtrack.get_records()) == 0


def test_activate_sqlite_backend(tmp_path):
    db_file = tmp_path / "lineage_test.db"
    provtrack.activate(backend="sqlite", db_path=str(db_file))
    assert provtrack.is_active()

    df = pd.DataFrame({"x": [10, 20, 30]})
    _ = df.dropna()

    records = provtrack.get_records()
    assert len(records) >= 1
    assert any(r.op_name == "dropna" for r in records)

    provtrack.deactivate()

    # Verify SQLite file contains records
    backend = SQLiteBackend(db_path=db_file)
    saved = backend.load()
    assert len(saved) >= 1


def test_wrap_functionality():
    df = pd.DataFrame({"a": [1, 2]})
    proxy = provtrack.wrap(df)
    assert isinstance(proxy, provtrack.DataFrameProxy)

    with pytest.raises(TypeError, match="does not support"):
        provtrack.wrap("invalid_object")


def test_reset():
    provtrack.activate(backend="memory")
    df = pd.DataFrame({"a": [1, 2]})
    _ = df.dropna()
    assert len(provtrack.get_records()) >= 1

    provtrack.reset()
    assert len(provtrack.get_records()) == 0
    assert provtrack.lineage().node_count == 0
    provtrack.deactivate()
