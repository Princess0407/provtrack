from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseProxy(ABC):
    __slots__ = ()

    @abstractmethod
    def unwrap(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def __getattr__(self, name: str) -> Any:
        raise NotImplementedError
