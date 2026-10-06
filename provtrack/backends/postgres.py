from __future__ import annotations

import json
import os
import threading
from typing import List, Optional

from provtrack.logger import OperationRecord
from .base import Backend


class PostgresBackend(Backend):
    __slots__ = ("dsn", "_lock")

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or os.environ.get("PROVTRACK_POSTGRES_DSN")
        if not self.dsn:
            raise ValueError(
                "PostgresBackend requires a DSN. Provide dsn or set PROVTRACK_POSTGRES_DSN environment variable."
            )
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise ImportError(
                "provtrack: postgres backend requires psycopg2. Install it with pip install psycopg2-binary"
            ) from exc

        return psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
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
            with conn.cursor() as cur:
                try:
                    from psycopg2.extras import execute_values

                    execute_values(
                        cur,
                        """
                        INSERT INTO records (
                            id, op_name, input_hash, output_hash, timestamp, source_line, source_file, tags, args_repr
                        ) VALUES %s
                        ON CONFLICT (id) DO UPDATE SET
                            op_name = EXCLUDED.op_name,
                            input_hash = EXCLUDED.input_hash,
                            output_hash = EXCLUDED.output_hash,
                            timestamp = EXCLUDED.timestamp,
                            source_line = EXCLUDED.source_line,
                            source_file = EXCLUDED.source_file,
                            tags = EXCLUDED.tags,
                            args_repr = EXCLUDED.args_repr
                        """,
                        rows,
                    )
                except ImportError:
                    cur.executemany(
                        """
                        INSERT INTO records (
                            id, op_name, input_hash, output_hash, timestamp, source_line, source_file, tags, args_repr
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            op_name = EXCLUDED.op_name,
                            input_hash = EXCLUDED.input_hash,
                            output_hash = EXCLUDED.output_hash,
                            timestamp = EXCLUDED.timestamp,
                            source_line = EXCLUDED.source_line,
                            source_file = EXCLUDED.source_file,
                            tags = EXCLUDED.tags,
                            args_repr = EXCLUDED.args_repr
                        """,
                        rows,
                    )
            conn.commit()

    def load(self) -> List[OperationRecord]:
        with self._lock, self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, op_name, input_hash, output_hash, timestamp, source_line, source_file, tags, args_repr FROM records ORDER BY timestamp ASC"
                )
                rows = cur.fetchall()

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
            with conn.cursor() as cur:
                cur.execute("DELETE FROM records")
            conn.commit()
