from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from .hashers import ArrayHasher, FastHasher, Hasher, PandasHasher, TensorHasher, short_id
from .hashers.base import DIGEST_LENGTH
from .hashers.dataframe import HASH_ALGO

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

SAMPLE_ROW_LIMIT: int = 100_000
SAMPLE_SEED: int = 42

_pandas_hasher = PandasHasher()
_fast_hasher = FastHasher(_pandas_hasher, sample_limit=SAMPLE_ROW_LIMIT, seed=SAMPLE_SEED)
_array_hasher = ArrayHasher()


def hash_dataframe(
    df: Any,
    *,
    hash_index: bool = False,
    include_schema: bool = True,
) -> str:
    hasher = PandasHasher(hash_index=hash_index, include_schema=include_schema)
    wrapper = FastHasher(hasher, sample_limit=SAMPLE_ROW_LIMIT, seed=SAMPLE_SEED)
    return wrapper.hash(df)


def hash_array(arr: np.ndarray) -> str:
    return _array_hasher.hash(arr)


def hash_sklearn_params(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.new(HASH_ALGO)
    h.update(canonical.encode("utf-8"))
    return h.hexdigest()


__all__ = [
    "Hasher",
    "PandasHasher",
    "ArrayHasher",
    "TensorHasher",
    "FastHasher",
    "hash_dataframe",
    "hash_array",
    "hash_sklearn_params",
    "short_id",
    "SAMPLE_ROW_LIMIT",
    "SAMPLE_SEED",
    "DIGEST_LENGTH",
    "HASH_ALGO",
]
