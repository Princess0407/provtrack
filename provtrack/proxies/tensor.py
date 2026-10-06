from __future__ import annotations

import time
from typing import Any

from provtrack.hashers.tensor import TensorHasher
from provtrack.logger import get_logger
from .base import BaseProxy

_tensor_hasher = TensorHasher()


def _is_tensor(obj: Any) -> bool:
    mod = getattr(type(obj), "__module__", "")
    return "torch" in mod or "tensorflow" in mod or hasattr(obj, "detach") or hasattr(obj, "numpy")


class TensorProxy(BaseProxy):
    __slots__ = ("_tensor", "_input_hash")

    def __init__(self, tensor: Any) -> None:
        object.__setattr__(self, "_tensor", tensor)
        object.__setattr__(self, "_input_hash", _tensor_hasher.hash(tensor))

    def __getattr__(self, name: str) -> Any:
        attr = getattr(object.__getattribute__(self, "_tensor"), name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            tensor = object.__getattribute__(self, "_tensor")
            in_hash = object.__getattribute__(self, "_input_hash")

            unwrapped_args = tuple(
                a.unwrap() if isinstance(a, TensorProxy) else a for a in args
            )

            t_start = time.perf_counter()
            result = attr(*unwrapped_args, **kwargs)
            duration_ms = (time.perf_counter() - t_start) * 1000

            if _is_tensor(result):
                out_hash = _tensor_hasher.hash(result)
                out = TensorProxy(result)
            else:
                out_hash = None
                out = result

            rec = get_logger().record(
                op_name=name,
                obj_type=type(tensor).__name__,
                input_hash=in_hash,
                output_hash=out_hash,
                args=args,
                kwargs=kwargs,
                duration_ms=duration_ms,
                tags=("tensor",),
            )
            try:
                from provtrack.activate import _backend, _graph
                if _backend is not None:
                    _backend.save([rec])
                if _graph is not None:
                    _graph.add_record(rec)
            except Exception:
                pass

            return out

        return _wrapped

    def __add__(self, other: Any) -> Any:
        return self.__getattr__("__add__")(other)

    def __sub__(self, other: Any) -> Any:
        return self.__getattr__("__sub__")(other)

    def __mul__(self, other: Any) -> Any:
        return self.__getattr__("__mul__")(other)

    def __matmul__(self, other: Any) -> Any:
        return self.__getattr__("__matmul__")(other)

    def __repr__(self) -> str:
        return f"<TensorProxy {repr(object.__getattribute__(self, '_tensor'))}>"

    @property
    def current_hash(self) -> str:
        return object.__getattribute__(self, "_input_hash")

    def unwrap(self) -> Any:
        return object.__getattribute__(self, "_tensor")
