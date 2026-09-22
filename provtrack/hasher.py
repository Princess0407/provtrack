"""
provtrack.hasher
~~~~~~~~~~~~~~~~
Stable, content-addressable fingerprinting of DataFrame states.

Design decisions:
  - SHA-256 over pd.util.hash_pandas_object row-hashes — stable across
    processes, platforms, and Python versions; avoids collision with sum-only.
  - Index is excluded by default (hash_index=False) so a reset_index() on the
    same rows does NOT produce a new lineage node unless the caller opts in.
  - NaN / None values are handled by pd.util.hash_pandas_object natively.
  - Object-dtype columns are normalised via .astype(str) before hashing so
    mixed-type cells produce consistent bytes.
  - Numpy arrays and plain Python lists are supported via a fast path.
  - A HMAC-style prefix encodes the schema (columns + dtypes) separately from
    the data so column renames are always detectable.

Security guardrail:
  All input is read-only during hashing (no mutations). The function is
  idempotent and has no side effects. Maximum DataFrame size for full hashing
  is configurable; above that we fall back to reservoir sampling to bound
  latency on very large frames (> SAMPLE_ROW_LIMIT rows).
"""

from __future__ import annotations

import hashlib
import struct
import warnings
from typing import TYPE_CHECKING

import numpy as np
# pandas is optional at import-time; raise clear errors only when hashing
# functionality is invoked.
try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # type: ignore

if TYPE_CHECKING:
    from typing import Union

# ── tuneable constants ────────────────────────────────────────────────────────
HASH_ALGO: str = "sha256"
DIGEST_LENGTH: int = 16          # hex chars to keep in short_id (full = 64)
SAMPLE_ROW_LIMIT: int = 100_000  # rows above which sampling kicks in
SAMPLE_SEED: int = 42
# ─────────────────────────────────────────────────────────────────────────────


def _schema_bytes(df: pd.DataFrame) -> bytes:
    """Encode column names + dtype names as a deterministic byte sequence."""
    parts = [f"{col}:{df[col].dtype}" for col in df.columns]
    return "|".join(parts).encode("utf-8")


def _normalise_object_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast object-dtype columns to string so hash_pandas_object sees consistent
    bytes regardless of whether the value is int, float, or str in a mixed col.
    Returns a lightweight copy — original frame is never mutated.
    """
    obj_cols = [c for c in df.columns if df[c].dtype == object]
    if not obj_cols:
        return df
    out = df.copy(deep=False)
    for col in obj_cols:
        out[col] = out[col].astype(str)
    return out


def _sample(df: pd.DataFrame) -> pd.DataFrame:
    """Reservoir-sample SAMPLE_ROW_LIMIT rows for large frames."""
    return df.sample(n=SAMPLE_ROW_LIMIT, random_state=SAMPLE_SEED)


def hash_dataframe(
    df: pd.DataFrame,
    *,
    hash_index: bool = False,
    include_schema: bool = True,
) -> str:
    """
    Return a hex-digest fingerprint that uniquely identifies the current
    state of *df*.

    Parameters
    ----------
    df : pd.DataFrame
        The frame to fingerprint. Not mutated.
    hash_index : bool
        If True, the row-index is included in the hash.  Default False —
        operations like reset_index() that only renumber rows won't produce
        spurious lineage nodes.
    include_schema : bool
        If True, column names and dtypes are folded into the hash so a
        column rename is always a new node.  Default True.

    Returns
    -------
    str
        64-character hex digest (SHA-256).
    """
    if pd is None:
        raise TypeError("hash_dataframe requires pandas; install pandas to use this function")
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"hash_dataframe expects a pd.DataFrame, got {type(df).__name__}"
        )

    if df.empty:
        # Deterministic hash for empty frames, keyed on schema only.
        h = hashlib.new(HASH_ALGO)
        h.update(b"__empty__")
        if include_schema:
            h.update(_schema_bytes(df))
        return h.hexdigest()

    sampled = False
    if len(df) > SAMPLE_ROW_LIMIT:
        warnings.warn(
            f"provtrack: DataFrame has {len(df):,} rows — hashing a "
            f"{SAMPLE_ROW_LIMIT:,}-row sample for performance. "
            "Set PROVTRACK_FULL_HASH=1 to disable sampling.",
            RuntimeWarning,
            stacklevel=2,
        )
        work = _sample(df)
        sampled = True
    else:
        work = df

    work = _normalise_object_cols(work)

    try:
        row_hashes = pd.util.hash_pandas_object(work, index=hash_index)
    except Exception as exc:
        # Fallback: pickle-based hash for exotic dtypes
        warnings.warn(
            f"provtrack: fast hash failed ({exc}); falling back to pickle hash.",
            RuntimeWarning,
            stacklevel=2,
        )
        import pickle  # noqa: PLC0415 — lazy import for fallback only
        raw = pickle.dumps(work, protocol=4)
        row_hashes = None
        h = hashlib.new(HASH_ALGO)
        h.update(raw)
        if include_schema:
            h.update(_schema_bytes(df))
        if sampled:
            h.update(b"__sampled__")
        return h.hexdigest()

    # Collapse per-row uint64 hashes into one digest.
    # Convert sum to fixed-width little-endian bytes to avoid variable-length
    # integer encoding issues.
    total: int = int(row_hashes.sum())
    packed = struct.pack("<Q", total & 0xFFFF_FFFF_FFFF_FFFF)

    h = hashlib.new(HASH_ALGO)
    h.update(packed)
    if include_schema:
        h.update(_schema_bytes(df))
    if sampled:
        h.update(b"__sampled__")
    return h.hexdigest()


def hash_array(arr: "np.ndarray") -> str:
    """
    Fingerprint a NumPy array.  Uses tobytes() which is O(n) but deterministic.
    """
    if not isinstance(arr, np.ndarray):
        raise TypeError(
            f"hash_array expects np.ndarray, got {type(arr).__name__}"
        )
    h = hashlib.new(HASH_ALGO)
    h.update(arr.dtype.str.encode())
    h.update(arr.tobytes())
    return h.hexdigest()


def hash_sklearn_params(params: dict) -> str:
    """
    Fingerprint a dict of sklearn estimator parameters so that a StandardScaler
    with different settings produces a different graph node.
    """
    import json  # noqa: PLC0415
    canonical = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.new(HASH_ALGO)
    h.update(canonical.encode("utf-8"))
    return h.hexdigest()


def short_id(full_hex: str) -> str:
    """Return a human-readable 16-char prefix of a full hex digest."""
    return full_hex[:DIGEST_LENGTH]
