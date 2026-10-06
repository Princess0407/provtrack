from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Union

from provtrack.logger import OperationRecord
from .base import Backend


class SQLiteBackend(Backend):
    __slots__ = ("db_path", "_lock")

    def __init__(self, db_path: Union[str, Path] = "provtrack.db") -> None:
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    op_name TEXT NOT NULL,
                    input_hash TEXT,
                    output_hash TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    source_line INTEGER,
                    source_file TEXT,
                    tags TEXT,
                    args_repr TEXT
                )
                """
            )
            conn.commit()

    def save(self, records: List[OperationRecord]) -> None:
        if not records:
            return
        rows = [
            (
                rec.id,
                rec.op_name,
                rec.input_hash,
                rec.output_hash,
                rec.timestamp,
                rec.source_line,
                rec.source_file,
                json.dumps(list(rec.tags)),
                rec.args_repr,
            )
            for rec in records
        ]
        with self._lock, self._get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO records (
                    id, op_name, input_hash, output_hash, timestamp, source_line, source_file, tags, args_repr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()

    def load(self) -> List[OperationRecord]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, op_name, input_hash, output_hash, timestamp, source_line, source_file, tags, args_repr FROM records ORDER BY timestamp ASC"
            )
            rows = cursor.fetchall()

        records: List[OperationRecord] = []
        for row in rows:
            try:
                tags = tuple(json.loads(row["tags"])) if row["tags"] else ()
            except (json.JSONDecodeError, ValueError):
                tags = ()
            records.append(
                OperationRecord(
                    id=row["id"],
                    op_name=row["op_name"],
                    input_hash=row["input_hash"],
                    output_hash=row["output_hash"],
                    timestamp=row["timestamp"],
                    source_line=row["source_line"],
                    source_file=row["source_file"],
                    tags=tags,
                    args_repr=row["args_repr"],
                )
            )
        return records

    def clear(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM records")
            conn.commit()
