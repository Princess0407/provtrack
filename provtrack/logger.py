from __future__ import annotations

import inspect
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass(frozen=True, slots=True)
class OperationRecord:
    id: str
    op_name: str
    output_hash: str
    input_hash: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    source_line: int = 0
    source_file: str = ""
    tags: Tuple[str, ...] = ()
    args_repr: str = ""
    kwargs_repr: str = ""
    obj_type: str = ""
    caller_func: str = ""
    duration_ms: float = 0.0

    def __init__(
        self,
        id: Optional[str] = None,
        op_name: str = "",
        output_hash: Optional[str] = None,
        input_hash: Optional[str] = None,
        timestamp: Optional[Union[float, str]] = None,
        source_line: Optional[int] = None,
        source_file: Optional[str] = None,
        tags: Union[Tuple[str, ...], List[str], str] = (),
        args_repr: str = "",
        kwargs_repr: str = "",
        obj_type: str = "",
        caller_func: str = "",
        duration_ms: float = 0.0,
        op_id: Optional[str] = None,
        caller_line: Optional[int] = None,
        caller_file: Optional[str] = None,
    ) -> None:
        rec_id = id or op_id or str(uuid.uuid4())
        s_line = source_line if source_line is not None else (caller_line if caller_line is not None else 0)
        s_file = source_file if source_file is not None else (caller_file or "")

        ts_val: float
        if timestamp is None:
            ts_val = time.time()
        elif isinstance(timestamp, (int, float)):
            ts_val = float(timestamp)
        elif isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp)
                ts_val = dt.timestamp()
            except ValueError:
                try:
                    ts_val = float(timestamp)
                except ValueError:
                    ts_val = time.time()
        else:
            ts_val = time.time()

        tags_val: Tuple[str, ...]
        if isinstance(tags, tuple):
            tags_val = tags
        elif isinstance(tags, list):
            tags_val = tuple(tags)
        elif isinstance(tags, str):
            try:
                parsed = json.loads(tags)
                tags_val = tuple(parsed) if isinstance(parsed, list) else (tags,)
            except (json.JSONDecodeError, ValueError):
                tags_val = tuple(t.strip() for t in tags.split(",") if t.strip()) if tags else ()
        else:
            tags_val = ()

        object.__setattr__(self, "id", str(rec_id))
        object.__setattr__(self, "op_name", str(op_name))
        object.__setattr__(self, "output_hash", str(output_hash or ""))
        object.__setattr__(self, "input_hash", str(input_hash) if input_hash is not None else None)
        object.__setattr__(self, "timestamp", ts_val)
        object.__setattr__(self, "source_line", int(s_line))
        object.__setattr__(self, "source_file", str(s_file))
        object.__setattr__(self, "tags", tags_val)
        object.__setattr__(self, "args_repr", str(args_repr))
        object.__setattr__(self, "kwargs_repr", str(kwargs_repr))
        object.__setattr__(self, "obj_type", str(obj_type))
        object.__setattr__(self, "caller_func", str(caller_func))
        object.__setattr__(self, "duration_ms", float(duration_ms))

    @property
    def op_id(self) -> str:
        return self.id

    @property
    def caller_line(self) -> int:
        return self.source_line

    @property
    def caller_file(self) -> str:
        return self.source_file

    @property
    def short_op_id(self) -> str:
        return self.id[:8]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "op_id": self.id,
            "op_name": self.op_name,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "timestamp": self.timestamp,
            "source_line": self.source_line,
            "source_file": self.source_file,
            "caller_line": self.source_line,
            "caller_file": self.source_file,
            "tags": list(self.tags),
            "args_repr": self.args_repr,
            "kwargs_repr": self.kwargs_repr,
            "obj_type": self.obj_type,
            "caller_func": self.caller_func,
            "duration_ms": self.duration_ms,
        }


_PROVTRACK_MODULE_MARKERS = ("provtrack",)
_MAX_REPR_LEN = 120


def _safe_repr(obj: Any) -> str:
    try:
        r = repr(obj)
    except Exception:
        r = f"<unrepresentable {type(obj).__name__}>"
    if len(r) > _MAX_REPR_LEN:
        r = r[: _MAX_REPR_LEN - 3] + "..."
    return r


def _caller_frame() -> tuple[str, int, str]:
    stack = inspect.stack()
    for frame_info in stack:
        fname = frame_info.filename
        if any(marker in fname for marker in _PROVTRACK_MODULE_MARKERS):
            continue
        if "importlib" in fname or "<frozen" in fname:
            continue
        return fname, frame_info.lineno, frame_info.function
    return "<unknown>", 0, "<unknown>"


class ProvenanceLogger:
    def __init__(self) -> None:
        self._records: List[OperationRecord] = []
        self._lock = threading.Lock()
        self._enabled = True

    def record(
        self,
        *,
        op_name: str,
        obj_type: str,
        input_hash: Optional[str],
        output_hash: Optional[str],
        args: tuple = (),
        kwargs: dict | None = None,
        duration_ms: float = 0.0,
        tags: tuple = (),
        source_file: Optional[str] = None,
        source_line: Optional[int] = None,
        caller_func: Optional[str] = None,
    ) -> OperationRecord:
        if not self._enabled:
            raise RuntimeError("provtrack: logger is disabled. Call provtrack.activate() first.")

        if kwargs is None:
            kwargs = {}

        if source_file is None or source_line is None:
            c_file, c_line, c_func = _caller_frame()
            source_file = source_file or c_file
            source_line = source_line if source_line is not None else c_line
            caller_func = caller_func or c_func

        rec = OperationRecord(
            id=str(uuid.uuid4()),
            op_name=op_name,
            obj_type=obj_type,
            input_hash=input_hash,
            output_hash=output_hash or "",
            args_repr=_safe_repr(args),
            kwargs_repr=_safe_repr(kwargs),
            source_file=source_file,
            source_line=source_line,
            caller_func=caller_func or "",
            timestamp=time.time(),
            duration_ms=round(duration_ms, 3),
            tags=tuple(tags),
        )

        with self._lock:
            self._records.append(rec)

        return rec

    def all(self) -> List[OperationRecord]:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def disable(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._records)


_logger_instance: Optional[ProvenanceLogger] = None
_singleton_lock = threading.Lock()


def get_logger() -> ProvenanceLogger:
    global _logger_instance
    if _logger_instance is None:
        with _singleton_lock:
            if _logger_instance is None:
                _logger_instance = ProvenanceLogger()
    return _logger_instance


def reset_logger() -> None:
    global _logger_instance
    with _singleton_lock:
        _logger_instance = ProvenanceLogger()
