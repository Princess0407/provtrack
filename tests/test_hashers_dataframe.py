import pandas as pd
import pytest

from provtrack.hashers.dataframe import PandasHasher


def test_pandas_hasher_basic():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    hasher = PandasHasher()
    h1 = hasher.hash(df)
    h2 = hasher.hash(df)
    assert isinstance(h1, str)
    assert len(h1) == 64
    assert h1 == h2


def test_pandas_hasher_empty():
    df1 = pd.DataFrame(columns=["a", "b"])
    df2 = pd.DataFrame(columns=["a", "c"])
    hasher = PandasHasher()
    h1 = hasher.hash(df1)
    h2 = hasher.hash(df2)
    assert h1 != h2


def test_pandas_hasher_type_error():
    hasher = PandasHasher()
    with pytest.raises(TypeError, match="PandasHasher expects a pd.DataFrame"):
        hasher.hash([1, 2, 3])


def test_pandas_hasher_hash_index():
    df1 = pd.DataFrame({"a": [1, 2]}, index=[0, 1])
    df2 = pd.DataFrame({"a": [1, 2]}, index=[10, 20])
    hasher_no_index = PandasHasher(hash_index=False)
    hasher_with_index = PandasHasher(hash_index=True)
    assert hasher_no_index.hash(df1) == hasher_no_index.hash(df2)
    assert hasher_with_index.hash(df1) != hasher_with_index.hash(df2)
