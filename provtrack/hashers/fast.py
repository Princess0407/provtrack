from __future__ import annotations

import hashlib
import os
import warnings
from typing import Any

from .base import Hasher
from .dataframe import PandasHasher


class FastHasher(Hasher):
    __slots__ = ("inner_hasher", "sample_limit", "seed")

    def __init__(
        self,
        inner_hasher: Hasher | None = None,
        *,
        sample_limit: int = 100_000,
        seed: int = 42,
    ) -> None:
        self.inner_hasher = inner_hasher if inner_hasher is not None else PandasHasher()
        self.sample_limit = sample_limit
        self.seed = seed

    def hash(self, obj: Any) -> str:
        if (
            os.environ.get("PROVTRACK_FULL_HASH") == "1"
            or not hasattr(obj, "__len__")
            or len(obj) <= self.sample_limit
        ):
            return self.inner_hasher.hash(obj)

        warnings.warn(
            f"provtrack: DataFrame has {len(obj):,} rows — hashing a "
            f"{self.sample_limit:,}-row sample for performance. "
            "Set PROVTRACK_FULL_HASH=1 to disable sampling.",
            RuntimeWarning,
            stacklevel=2,
        )
        sample = obj.sample(n=self.sample_limit, random_state=self.seed)
        base_hash = self.inner_hasher.hash(sample)
        h = hashlib.new("sha256")
        h.update(base_hash.encode("utf-8"))
        h.update(b"__sampled__")
        return h.hexdigest()
