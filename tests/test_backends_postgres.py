from unittest.mock import MagicMock, patch
import pytest

from provtrack.backends.postgres import PostgresBackend
from provtrack.logger import OperationRecord


def test_postgres_missing_dsn():
    with pytest.raises(ValueError, match="requires a DSN"):
        PostgresBackend(dsn=None)


def test_postgres_backend_operations():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn

    with patch("provtrack.backends.postgres.PostgresBackend._get_connection", return_value=mock_conn):
        backend = PostgresBackend(dsn="postgresql://user:pass@localhost:5432/db")

        # Verify table creation called
        assert mock_cursor.execute.called

        # Test save
        rec = OperationRecord(
            id="rec-pg",
            op_name="dropna",
            output_hash="hash-pg-out",
            input_hash="hash-pg-in",
        )
        backend.save([rec])
        assert mock_conn.commit.called

        # Test load
        mock_cursor.fetchall.return_value = [
            {
                "id": "rec-pg",
                "op_name": "dropna",
                "input_hash": "hash-pg-in",
                "output_hash": "hash-pg-out",
                "timestamp": 1234567.0,
                "source_line": 10,
                "source_file": "script.py",
                "tags": '["pandas"]',
                "args_repr": "()",
            }
        ]
        loaded = backend.load()
        assert len(loaded) == 1
        assert loaded[0].id == "rec-pg"
        assert loaded[0].tags == ("pandas",)

        # Test clear
        backend.clear()
        assert mock_conn.commit.called
