import os
import warnings
import pandas as pd

from provtrack.hashers.fast import FastHasher


def test_fast_hasher_small_df():
    df = pd.DataFrame({"a": range(50)})
    hasher = FastHasher(sample_limit=100)
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        h = hasher.hash(df)
    assert len(recorded) == 0
    assert isinstance(h, str)


def test_fast_hasher_large_df():
    df = pd.DataFrame({"a": range(200)})
    hasher = FastHasher(sample_limit=50, seed=123)
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        h1 = hasher.hash(df)
        h2 = hasher.hash(df)
    assert len(recorded) == 2
    assert "sampling" in str(recorded[0].message).lower()
    assert h1 == h2


def test_fast_hasher_full_hash_env(monkeypatch):
    monkeypatch.setenv("PROVTRACK_FULL_HASH", "1")
    df = pd.DataFrame({"a": range(200)})
    hasher = FastHasher(sample_limit=50)
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        h = hasher.hash(df)
    assert len(recorded) == 0
    assert isinstance(h, str)
