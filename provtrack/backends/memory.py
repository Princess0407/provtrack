from __future__ import annotations

import threading
from typing import TYPE_CHECKING, List

from .base import Backend

if TYPE_CHECKING:
    from provtrack.logger import OperationRecord


class MemoryBackend(Backend):
    __slots__ = ("_records", "_lock")

    def __init__(self) -> None:
        self._records: List[OperationRecord] = []
        self._lock = threading.Lock()

    def save(self, records: List[OperationRecord]) -> None:
        with self._lock:
            self._records.extend(records)

    def load(self) -> List[OperationRecord]:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
