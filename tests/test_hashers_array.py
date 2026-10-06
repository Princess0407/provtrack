import numpy as np
import pytest

from provtrack.hashers.array import ArrayHasher


def test_array_hasher_basic():
    arr1 = np.array([1, 2, 3], dtype=np.int32)
    arr2 = np.array([1, 2, 3], dtype=np.int32)
    hasher = ArrayHasher()
    h1 = hasher.hash(arr1)
    h2 = hasher.hash(arr2)
    assert isinstance(h1, str)
    assert len(h1) == 64
    assert h1 == h2


def test_array_hasher_dtype_difference():
    arr1 = np.array([1, 2, 3], dtype=np.int32)
    arr2 = np.array([1, 2, 3], dtype=np.int64)
    hasher = ArrayHasher()
    assert hasher.hash(arr1) != hasher.hash(arr2)


def test_array_hasher_type_error():
    hasher = ArrayHasher()
    with pytest.raises(TypeError, match="ArrayHasher expects np.ndarray"):
        hasher.hash([1, 2, 3])
