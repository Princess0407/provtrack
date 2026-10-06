from abc import ABC, abstractmethod
from typing import Any

DIGEST_LENGTH: int = 16


class Hasher(ABC):
    __slots__ = ()

    @abstractmethod
    def hash(self, obj: Any) -> str:
        raise NotImplementedError


def short_id(full_hex: str) -> str:
    return full_hex[:DIGEST_LENGTH]
