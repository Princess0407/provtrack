from __future__ import annotations

from typing import Any

import numpy as np

from .array import ArrayHasher
from .base import Hasher


class TensorHasher(Hasher):
    __slots__ = ("_array_hasher",)

    def __init__(self) -> None:
        self._array_hasher = ArrayHasher()

    def hash(self, obj: Any) -> str:
        arr: np.ndarray
        obj_module = type(obj).__module__

        if "torch" in obj_module:
            arr = obj.detach().cpu().numpy()
        elif "tensorflow" in obj_module or hasattr(obj, "numpy") and callable(getattr(obj, "numpy")):
            arr = obj.numpy()
        else:
            raise TypeError(f"TensorHasher expects a torch or tf Tensor, got {type(obj).__name__}")

        return self._array_hasher.hash(arr)
