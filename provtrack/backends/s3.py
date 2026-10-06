from __future__ import annotations

import json
import threading
import uuid
from typing import Any, List, Optional
from urllib.parse import urlparse

from provtrack.logger import OperationRecord
from .base import Backend


class S3Backend(Backend):
    __slots__ = ("bucket", "key", "session_id", "_client", "_records", "_lock")

    def __init__(
        self,
        bucket: Optional[str] = None,
        s3_uri: Optional[str] = None,
        session_id: Optional[str] = None,
        client: Optional[Any] = None,
    ) -> None:
        self._lock = threading.Lock()
        self.session_id = session_id or str(uuid.uuid4())
        self._records: List[OperationRecord] = []
        self._client = client

        if s3_uri:
            parsed = urlparse(s3_uri)
            if parsed.scheme != "s3" or not parsed.netloc:
                raise ValueError(f"Invalid S3 URI: {s3_uri}. Expected format s3://bucket/key")
            self.bucket = parsed.netloc
            raw_path = parsed.path.lstrip("/")
            if raw_path.endswith(".json"):
                self.key = raw_path
            elif raw_path:
                self.key = f"{raw_path.rstrip('/')}/{self.session_id}.json"
            else:
                self.key = f"provtrack/{self.session_id}.json"
        elif bucket:
            self.bucket = bucket
            self.key = f"provtrack/{self.session_id}.json"
        else:
            raise ValueError("S3Backend requires either bucket or s3_uri")

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3

            self._client = boto3.client("s3")
            return self._client
        except ImportError as exc:
            raise ImportError(
                "provtrack: s3 backend requires boto3. Install it with pip install boto3"
            ) from exc

    def save(self, records: List[OperationRecord]) -> None:
        with self._lock:
            self._records.extend(records)
            payload = {
                "session_id": self.session_id,
                "nodes": [rec.to_dict() for rec in self._records],
            }
            body = json.dumps(payload, indent=2).encode("utf-8")
            client = self._get_client()
            client.put_object(
                Bucket=self.bucket,
                Key=self.key,
                Body=body,
                ContentType="application/json",
            )

    def load(self) -> List[OperationRecord]:
        with self._lock:
            client = self._get_client()
            try:
                response = client.get_object(Bucket=self.bucket, Key=self.key)
                content = response["Body"].read().decode("utf-8")
                data = json.loads(content)
            except Exception:
                return list(self._records)

            records: List[OperationRecord] = []
            for node in data.get("nodes", []):
                records.append(
                    OperationRecord(
                        id=node.get("id") or node.get("op_id"),
                        op_name=node.get("op_name", ""),
                        input_hash=node.get("input_hash"),
                        output_hash=node.get("output_hash", ""),
                        timestamp=node.get("timestamp"),
                        source_line=node.get("source_line") or node.get("caller_line", 0),
                        source_file=node.get("source_file") or node.get("caller_file", ""),
                        tags=tuple(node.get("tags", [])),
                        args_repr=node.get("args_repr", ""),
                        kwargs_repr=node.get("kwargs_repr", ""),
                        obj_type=node.get("obj_type", ""),
                        caller_func=node.get("caller_func", ""),
                        duration_ms=node.get("duration_ms", 0.0),
                    )
                )
            self._records = records
            return list(records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            client = self._get_client()
            try:
                client.delete_object(Bucket=self.bucket, Key=self.key)
            except Exception:
                pass
