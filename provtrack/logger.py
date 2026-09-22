"""
provtrack.logger
~~~~~~~~~~~~~~~~
Records every intercepted operation into a structured OperationRecord.

Design decisions:
  - Immutable dataclass (frozen=True) so records can't be mutated after the
    fact — audit integrity.
  - inspect.stack() is called once per operation to capture the caller's
    filename and line number from user code (not from our own proxy frames).
  - Timestamps are UTC ISO-8601 strings — timezone-safe, JSON-serialisable.
  - The logger is a singleton per-process to avoid multiple graphs diverging.
    Call provtrack.reset() to get a clean slate (used in tests).
  - Thread-safe: all mutations go through a threading.Lock.

Security guardrails:
  - Stack frames are captured but the full local variable state is NOT — we
    only record filename, lineno, and function name.  No user data leaks into
    the operation record.
  - The global registry cannot be written to externally; consumers must go
    through get_logger() / reset().
"""

from __future__ import annotations

import inspect
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── OperationRecord ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OperationRecord:
    """
    Immutable record of a single intercepted operation.

    Attributes
    ----------
    op_id      : Unique UUID for this operation node in the DAG.
    op_name    : Method/function name (e.g. "dropna", "fit_transform").
    obj_type   : Class name of the object the method was called on.
    input_hash : SHA-256 of the input DataFrame/array state.
    output_hash: SHA-256 of the output state (None if op had no DF output).
    args_repr  : Truncated repr of positional args (no raw data).
    kwargs_repr: Truncated repr of keyword args (no raw data).
    caller_file: Source file where the user called this operation.
    caller_line: Line number in user code.
    caller_func: Function name in user code that triggered this.
    timestamp  : UTC ISO-8601 when the operation completed.
    duration_ms: Wall-clock ms the operation took (excludes hashing time).
    tags       : Arbitrary string tags (e.g. "sklearn", "pandas").
    """
    op_id       : str
    op_name     : str
    obj_type    : str
    input_hash  : str
    output_hash : Optional[str]
    args_repr   : str
    kwargs_repr : str
    caller_file : str
    caller_line : int
    caller_func : str
    timestamp   : str
    duration_ms : float
    tags        : tuple = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tags"] = list(d["tags"])
        return d

    @property
    def short_op_id(self) -> str:
        return self.op_id[:8]


# ── helpers ───────────────────────────────────────────────────────────────────

_PROVTRACK_FILES = frozenset({
    "proxy.py",
    "logger.py",
    "hasher.py",
    "graph.py",
    "activate.py",
    "__init__.py",
})

_MAX_REPR_LEN = 120


def _safe_repr(obj: Any) -> str:
    """Repr that never raises and is bounded in length."""
    try:
        r = repr(obj)
    except Exception:
        r = f"<unrepresentable {type(obj).__name__}>"
    if len(r) > _MAX_REPR_LEN:
        r = r[: _MAX_REPR_LEN - 3] + "..."
    return r


def _caller_frame() -> tuple[str, int, str]:
    """
    Walk the call stack upward until we find a frame from user code
    (i.e. not from provtrack's own modules).

    Returns (filename, lineno, funcname).
    """
    stack = inspect.stack()
    for frame_info in stack:
        fname = frame_info.filename
        # Skip frames that belong to provtrack itself.
        if any(fname.endswith(pt) for pt in _PROVTRACK_FILES):
            continue
        # Skip the Python stdlib internals.
        if "importlib" in fname or "<frozen" in fname:
            continue
        return fname, frame_info.lineno, frame_info.function
    # Fallback — shouldn't happen in practice.
    return "<unknown>", 0, "<unknown>"


# ── ProvenanceLogger ──────────────────────────────────────────────────────────

class ProvenanceLogger:
    """
    Thread-safe singleton that accumulates OperationRecords for one session.

    Usage
    -----
    logger = get_logger()
    logger.record(op_name="dropna", obj_type="DataFrame", ...)
    records = logger.all()
    """

    def __init__(self) -> None:
        self._records: List[OperationRecord] = []
        self._lock = threading.Lock()
        self._enabled = True

    # ── public API ────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        op_name: str,
        obj_type: str,
        input_hash: str,
        output_hash: Optional[str],
        args: tuple = (),
        kwargs: dict | None = None,
        duration_ms: float = 0.0,
        tags: tuple = (),
    ) -> OperationRecord:
        """
        Build and store a new OperationRecord.  Returns the record so the
        caller (proxy.py) can pass the op_id to graph.py immediately.
        """
        if not self._enabled:
            raise RuntimeError(
                "provtrack: logger is disabled. Call provtrack.activate() first."
            )

        if kwargs is None:
            kwargs = {}

        caller_file, caller_line, caller_func = _caller_frame()

        rec = OperationRecord(
            op_id       = str(uuid.uuid4()),
            op_name     = op_name,
            obj_type    = obj_type,
            input_hash  = input_hash,
            output_hash = output_hash,
            args_repr   = _safe_repr(args),
            kwargs_repr = _safe_repr(kwargs),
            caller_file = caller_file,
            caller_line = caller_line,
            caller_func = caller_func,
            timestamp   = datetime.now(timezone.utc).isoformat(),
            duration_ms = round(duration_ms, 3),
            tags        = tuple(tags),
        )

        with self._lock:
            self._records.append(rec)

        return rec

    def all(self) -> List[OperationRecord]:
        """Return a snapshot of all records (thread-safe copy)."""
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        """Discard all records (used by provtrack.reset())."""
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

    def __repr__(self) -> str:
        return f"<ProvenanceLogger records={self.count} enabled={self._enabled}>"


# ── module-level singleton ────────────────────────────────────────────────────

_logger_instance: Optional[ProvenanceLogger] = None
_singleton_lock = threading.Lock()


def get_logger() -> ProvenanceLogger:
    """Return (or lazily create) the process-wide ProvenanceLogger."""
    global _logger_instance
    if _logger_instance is None:
        with _singleton_lock:
            if _logger_instance is None:
                _logger_instance = ProvenanceLogger()
    return _logger_instance


def reset_logger() -> None:
    """
    Discard the current session's records and create a fresh logger.
    Used in tests and when the user calls provtrack.reset().
    """
    global _logger_instance
    with _singleton_lock:
        _logger_instance = ProvenanceLogger()
