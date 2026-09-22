"""
tests.test_hasher
~~~~~~~~~~~~~~~~~
Unit tests for provtrack.hasher.

Every edge case discussed during design is tested here:
  - Identical DataFrames produce the same hash.
  - Different DataFrames produce different hashes.
  - Empty DataFrames are handled.
  - NaN/None values are handled consistently.
  - Object-dtype columns with mixed types.
  - Column renames detected when include_schema=True.
  - Reset index does NOT change hash when hash_index=False (default).
  - Large DataFrames trigger the sampling path.
  - NumPy array hashing.
  - Sklearn param hashing.
  - TypeError on wrong input.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from provtrack.hasher import (
    SAMPLE_ROW_LIMIT,
    hash_array,
    hash_dataframe,
    hash_sklearn_params,
    short_id,
)


# ── basic correctness ─────────────────────────────────────────────────────────

def test_identical_frames_same_hash():
    df1 = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
    df2 = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
    assert hash_dataframe(df1) == hash_dataframe(df2)


def test_different_data_different_hash():
    df1 = pd.DataFrame({"a": [1, 2, 3]})
    df2 = pd.DataFrame({"a": [9, 2, 3]})
    assert hash_dataframe(df1) != hash_dataframe(df2)


def test_hash_is_hex_string():
    df = pd.DataFrame({"x": [1]})
    h = hash_dataframe(df)
    assert isinstance(h, str)
    assert len(h) == 64  # SHA-256 hex
    int(h, 16)  # must be valid hex


# ── NaN / None ────────────────────────────────────────────────────────────────

def test_nan_values_consistent():
    df1 = pd.DataFrame({"a": [1.0, float("nan"), 3.0]})
    df2 = pd.DataFrame({"a": [1.0, float("nan"), 3.0]})
    assert hash_dataframe(df1) == hash_dataframe(df2)


def test_nan_vs_none_object_col():
    df1 = pd.DataFrame({"a": [None, "x"]})
    df2 = pd.DataFrame({"a": [None, "x"]})
    assert hash_dataframe(df1) == hash_dataframe(df2)


def test_nan_vs_number_different_hash():
    df1 = pd.DataFrame({"a": [1.0, 2.0]})
    df2 = pd.DataFrame({"a": [1.0, float("nan")]})
    assert hash_dataframe(df1) != hash_dataframe(df2)


# ── empty DataFrame ───────────────────────────────────────────────────────────

def test_empty_dataframe_stable():
    df = pd.DataFrame()
    h1 = hash_dataframe(df)
    h2 = hash_dataframe(df)
    assert h1 == h2


def test_empty_with_columns_different_from_plain_empty():
    df1 = pd.DataFrame(columns=["a", "b"])
    df2 = pd.DataFrame(columns=["a", "c"])
    # schema differs → different hash
    assert hash_dataframe(df1) != hash_dataframe(df2)


# ── schema sensitivity ────────────────────────────────────────────────────────

def test_column_rename_detected():
    df1 = pd.DataFrame({"age": [25, 30]})
    df2 = df1.rename(columns={"age": "AGE"})
    # Same data, different schema — should differ with default include_schema=True.
    assert hash_dataframe(df1) != hash_dataframe(df2)


def test_schema_excluded_when_asked():
    df1 = pd.DataFrame({"age": [25, 30]})
    df2 = df1.rename(columns={"age": "AGE"})
    # Without schema, same underlying data → same hash.
    assert hash_dataframe(df1, include_schema=False) == hash_dataframe(
        df2, include_schema=False
    )


def test_dtype_change_detected():
    df1 = pd.DataFrame({"a": pd.array([1, 2, 3], dtype="int32")})
    df2 = pd.DataFrame({"a": pd.array([1, 2, 3], dtype="int64")})
    # Different dtype → different schema → different hash.
    assert hash_dataframe(df1) != hash_dataframe(df2)


# ── index behaviour ───────────────────────────────────────────────────────────

def test_reset_index_same_hash_by_default():
    """reset_index() should NOT create a new lineage node (default behaviour)."""
    df1 = pd.DataFrame({"a": [1, 2, 3]})
    df2 = df1.reset_index(drop=True)
    assert hash_dataframe(df1) == hash_dataframe(df2)


def test_reset_index_differs_when_hash_index_true():
    df1 = pd.DataFrame({"a": [1, 2, 3]}, index=[10, 20, 30])
    df2 = df1.reset_index(drop=True)
    assert hash_dataframe(df1, hash_index=True) != hash_dataframe(df2, hash_index=True)


# ── object / mixed dtype columns ──────────────────────────────────────────────

def test_object_dtype_mixed_types():
    df = pd.DataFrame({"x": [1, "two", 3.0, None]})
    h1 = hash_dataframe(df)
    h2 = hash_dataframe(df)
    assert h1 == h2


def test_object_dtype_different_values():
    df1 = pd.DataFrame({"x": ["a", "b"]})
    df2 = pd.DataFrame({"x": ["a", "c"]})
    assert hash_dataframe(df1) != hash_dataframe(df2)


# ── sampling for large DataFrames ─────────────────────────────────────────────

def test_large_frame_triggers_warning():
    df = pd.DataFrame({"a": range(SAMPLE_ROW_LIMIT + 1)})
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        hash_dataframe(df)
    assert any("sample" in str(warning.message).lower() for warning in w)


def test_large_frame_same_data_same_hash():
    df = pd.DataFrame({"a": range(SAMPLE_ROW_LIMIT + 1)})
    h1 = hash_dataframe(df)
    h2 = hash_dataframe(df)
    assert h1 == h2


# ── type errors ───────────────────────────────────────────────────────────────

def test_type_error_on_non_dataframe():
    with pytest.raises(TypeError, match="pd.DataFrame"):
        hash_dataframe([1, 2, 3])  # type: ignore


def test_type_error_on_series():
    s = pd.Series([1, 2, 3])
    with pytest.raises(TypeError):
        hash_dataframe(s)  # type: ignore


# ── numpy array hashing ───────────────────────────────────────────────────────

def test_array_same_hash():
    a1 = np.array([1.0, 2.0, 3.0])
    a2 = np.array([1.0, 2.0, 3.0])
    assert hash_array(a1) == hash_array(a2)


def test_array_different_hash():
    a1 = np.array([1.0, 2.0])
    a2 = np.array([1.0, 9.0])
    assert hash_array(a1) != hash_array(a2)


def test_array_dtype_differs():
    a1 = np.array([1, 2], dtype=np.float32)
    a2 = np.array([1, 2], dtype=np.float64)
    assert hash_array(a1) != hash_array(a2)


def test_array_type_error():
    with pytest.raises(TypeError):
        hash_array([1, 2, 3])  # type: ignore


# ── sklearn param hashing ─────────────────────────────────────────────────────

def test_sklearn_params_same():
    p1 = {"with_mean": True, "with_std": True}
    p2 = {"with_mean": True, "with_std": True}
    assert hash_sklearn_params(p1) == hash_sklearn_params(p2)


def test_sklearn_params_order_invariant():
    p1 = {"a": 1, "b": 2}
    p2 = {"b": 2, "a": 1}
    assert hash_sklearn_params(p1) == hash_sklearn_params(p2)


def test_sklearn_params_different():
    p1 = {"with_mean": True}
    p2 = {"with_mean": False}
    assert hash_sklearn_params(p1) != hash_sklearn_params(p2)


# ── short_id ──────────────────────────────────────────────────────────────────

def test_short_id_length():
    df = pd.DataFrame({"a": [1]})
    h = hash_dataframe(df)
    assert len(short_id(h)) == 16


def test_short_id_is_prefix():
    df = pd.DataFrame({"a": [1]})
    h = hash_dataframe(df)
    assert h.startswith(short_id(h))
