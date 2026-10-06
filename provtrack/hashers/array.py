from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from .base import Hasher

HASH_ALGO: str = "sha256"


class ArrayHasher(Hasher):
    __slots__ = ()

    def hash(self, obj: Any) -> str:
        if not isinstance(obj, np.ndarray):
            raise TypeError(f"ArrayHasher expects np.ndarray, got {type(obj).__name__}")
        h = hashlib.new(HASH_ALGO)
        h.update(obj.dtype.str.encode("utf-8"))
        h.update(obj.tobytes())
        return h.hexdigest()
