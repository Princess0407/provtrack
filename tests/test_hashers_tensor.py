import numpy as np
import pytest

from provtrack.hashers.tensor import TensorHasher


class MockTorchTensor:
    __module__ = "torch"

    def __init__(self, arr: np.ndarray) -> None:
        self._arr = arr

    def detach(self) -> "MockTorchTensor":
        return self

    def cpu(self) -> "MockTorchTensor":
        return self

    def numpy(self) -> np.ndarray:
        return self._arr


class MockTfTensor:
    __module__ = "tensorflow"

    def __init__(self, arr: np.ndarray) -> None:
        self._arr = arr

    def numpy(self) -> np.ndarray:
        return self._arr


def test_tensor_hasher_torch():
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    t1 = MockTorchTensor(arr)
    t2 = MockTorchTensor(arr.copy())
    hasher = TensorHasher()
    assert hasher.hash(t1) == hasher.hash(t2)


def test_tensor_hasher_tf():
    arr = np.array([4, 5, 6], dtype=np.int64)
    t = MockTfTensor(arr)
    hasher = TensorHasher()
    h = hasher.hash(t)
    assert isinstance(h, str)
    assert len(h) == 64


def test_tensor_hasher_type_error():
    hasher = TensorHasher()
    with pytest.raises(TypeError, match="TensorHasher expects a torch or tf Tensor"):
        hasher.hash("not a tensor")
