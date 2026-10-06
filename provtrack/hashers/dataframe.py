from __future__ import annotations

import hashlib
import struct
import warnings
from typing import Any

import pandas as pd

from .base import Hasher

HASH_ALGO: str = "sha256"


def _schema_bytes(df: pd.DataFrame) -> bytes:
    parts = [f"{col}:{df[col].dtype}" for col in df.columns]
    return "|".join(parts).encode("utf-8")


def _normalise_object_cols(df: pd.DataFrame) -> pd.DataFrame:
    obj_cols = [c for c in df.columns if df[c].dtype == object]
    if not obj_cols:
        return df
    out = df.copy(deep=False)
    for col in obj_cols:
        out[col] = out[col].astype(str)
    return out


class PandasHasher(Hasher):
    __slots__ = ("hash_index", "include_schema")

    def __init__(self, *, hash_index: bool = False, include_schema: bool = True) -> None:
        self.hash_index = hash_index
        self.include_schema = include_schema

    def hash(self, obj: Any) -> str:
        if not isinstance(obj, pd.DataFrame):
            raise TypeError(f"PandasHasher expects a pd.DataFrame, got {type(obj).__name__}")

        if obj.empty:
            h = hashlib.new(HASH_ALGO)
            h.update(b"__empty__")
            if self.include_schema:
                h.update(_schema_bytes(obj))
            return h.hexdigest()

        work = _normalise_object_cols(obj)

        try:
            row_hashes = pd.util.hash_pandas_object(work, index=self.hash_index)
        except Exception as exc:
            warnings.warn(
                f"provtrack: fast hash failed ({exc}); falling back to pickle hash.",
                RuntimeWarning,
                stacklevel=2,
            )
            import pickle

            raw = pickle.dumps(work, protocol=4)
            h = hashlib.new(HASH_ALGO)
            h.update(raw)
            if self.include_schema:
                h.update(_schema_bytes(obj))
            return h.hexdigest()

        total: int = int(row_hashes.sum())
        packed = struct.pack("<Q", total & 0xFFFF_FFFF_FFFF_FFFF)

        h = hashlib.new(HASH_ALGO)
        h.update(packed)
        if self.include_schema:
            h.update(_schema_bytes(obj))
        return h.hexdigest()
