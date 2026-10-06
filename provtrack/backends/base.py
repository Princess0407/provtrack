from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from provtrack.logger import OperationRecord


class Backend(ABC):
    __slots__ = ()

    @abstractmethod
    def save(self, records: List[OperationRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self) -> List[OperationRecord]:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError
