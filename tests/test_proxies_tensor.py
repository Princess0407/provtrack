import numpy as np

from provtrack.proxies.tensor import TensorProxy
from provtrack.logger import get_logger, reset_logger


class MockTensor:
    __module__ = "torch"

    def __init__(self, arr: np.ndarray) -> None:
        self._arr = arr

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._arr

    def add(self, other):
        other_arr = other.numpy() if hasattr(other, "numpy") else other
        return MockTensor(self._arr + other_arr)

    def __repr__(self):
        return f"MockTensor({self._arr})"


def setup_function():
    reset_logger()


def test_tensor_proxy_operations():
    t1 = MockTensor(np.array([1, 2, 3]))
    t2 = MockTensor(np.array([4, 5, 6]))
    p1 = TensorProxy(t1)
    p2 = TensorProxy(t2)

    p3 = p1.add(p2)
    assert isinstance(p3, TensorProxy)
    assert np.array_equal(p3.unwrap().numpy(), np.array([5, 7, 9]))

    recs = get_logger().all()
    assert len(recs) == 1
    assert recs[0].op_name == "add"
    assert recs[0].input_hash == p1.current_hash
    assert recs[0].output_hash == p3.current_hash
