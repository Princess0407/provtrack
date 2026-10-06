from __future__ import annotations

import hashlib
import time
from typing import Any

from provtrack.logger import get_logger
from .base import BaseProxy


def _hash_spark_df(df: Any) -> str:
    h = hashlib.sha256()
    if hasattr(df, "schema"):
        h.update(str(df.schema).encode("utf-8"))
    if hasattr(df, "_jdf"):
        try:
            h.update(str(df._jdf.queryExecution().logical().toString()).encode("utf-8"))
        except Exception:
            pass
    elif hasattr(df, "columns"):
        h.update(str(df.columns).encode("utf-8"))
    return h.hexdigest()


def _is_spark_df(obj: Any) -> bool:
    mod = getattr(type(obj), "__module__", "")
    return "pyspark" in mod or (hasattr(obj, "schema") and hasattr(obj, "columns"))


class SparkProxy(BaseProxy):
    __slots__ = ("_df", "_input_hash")

    def __init__(self, df: Any) -> None:
        object.__setattr__(self, "_df", df)
        object.__setattr__(self, "_input_hash", _hash_spark_df(df))

    def __getattr__(self, name: str) -> Any:
        df = object.__getattribute__(self, "_df")
        attr = getattr(df, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            in_hash = object.__getattribute__(self, "_input_hash")

            unwrapped_args = tuple(
                a.unwrap() if isinstance(a, SparkProxy) else a for a in args
            )

            t_start = time.perf_counter()
            result = attr(*unwrapped_args, **kwargs)
            duration_ms = (time.perf_counter() - t_start) * 1000

            if _is_spark_df(result):
                out_hash = _hash_spark_df(result)
                out = SparkProxy(result)
            else:
                out_hash = None
                out = result

            rec = get_logger().record(
                op_name=name,
                obj_type=type(df).__name__,
                input_hash=in_hash,
                output_hash=out_hash,
                args=args,
                kwargs=kwargs,
                duration_ms=duration_ms,
                tags=("spark",),
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

    def __repr__(self) -> str:
        return f"<SparkProxy {repr(object.__getattribute__(self, '_df'))}>"

    @property
    def current_hash(self) -> str:
        return object.__getattribute__(self, "_input_hash")

    def unwrap(self) -> Any:
        return object.__getattribute__(self, "_df")
