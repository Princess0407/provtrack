from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from provtrack.hashers.dataframe import PandasHasher
from provtrack.logger import get_logger
from .base import BaseProxy

_pandas_hasher = PandasHasher()

_SKIP_OPS = frozenset({
    "__repr__",
    "__str__",
    "__len__",
    "__contains__",
    "__iter__",
    "__next__",
    "_repr_html_",
    "_repr_mimebundle_",
    "_repr_latex_",
    "to_string",
    "head",
    "tail",
    "info",
    "describe",
    "dtypes",
    "shape",
    "columns",
    "index",
    "values",
    "ndim",
    "size",
    "axes",
    "empty",
    "T",
    "items",
    "iteritems",
    "iterrows",
    "itertuples",
    "keys",
    "copy",
    "__copy__",
    "__deepcopy__",
    "_validate_dtype",
    "_check_label",
    "_get_axis_resolvers",
    "_get_block_manager_meta",
    "_metadata",
    "_typ",
    "__dataframe__",
    "__array__",
    "__array_priority__",
})


class DataFrameProxy(BaseProxy):
    __slots__ = ("_df", "_input_hash")

    @property
    def __class__(self):
        return pd.DataFrame

    __array_ufunc__ = None

    def __init__(self, df: pd.DataFrame) -> None:
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"DataFrameProxy requires a pd.DataFrame, got {type(df).__name__}")
        object.__setattr__(self, "_df", df)
        object.__setattr__(self, "_input_hash", _pandas_hasher.hash(df))

    def __getattr__(self, name: str) -> Any:
        if name in _SKIP_OPS:
            return getattr(object.__getattribute__(self, "_df"), name)

        attr = getattr(object.__getattribute__(self, "_df"), name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            df = object.__getattribute__(self, "_df")
            in_hash = object.__getattribute__(self, "_input_hash")

            t_start = time.perf_counter()
            result = attr(*args, **kwargs)
            duration_ms = (time.perf_counter() - t_start) * 1000

            if kwargs.get("inplace", False):
                out_hash = _pandas_hasher.hash(df)
                object.__setattr__(self, "_input_hash", out_hash)
                out = self
            elif isinstance(result, pd.DataFrame):
                out_hash = _pandas_hasher.hash(result)
                out = DataFrameProxy(result)
            else:
                out_hash = None
                out = result

            rec = get_logger().record(
                op_name=name,
                obj_type="DataFrame",
                input_hash=in_hash,
                output_hash=out_hash,
                args=args,
                kwargs=kwargs,
                duration_ms=duration_ms,
                tags=("pandas",),
            )
            from provtrack.proxy import get_graph
            get_graph().add_record(rec)

            return out

        return _wrapped

    def __getitem__(self, key: Any) -> Any:
        df = object.__getattribute__(self, "_df")
        input_hash = object.__getattribute__(self, "_input_hash")

        t_start = time.perf_counter()
        result = df[key]
        duration_ms = (time.perf_counter() - t_start) * 1000

        if isinstance(result, pd.DataFrame):
            out_obj = DataFrameProxy(result)
            output_hash = _pandas_hasher.hash(result)
        else:
            out_obj = result
            output_hash = None

        is_structural = (
            isinstance(key, (list, slice))
            or isinstance(key, (pd.Series, np.ndarray))
        )
        if is_structural and isinstance(result, pd.DataFrame):
            op_name = "filter" if isinstance(key, (pd.Series, np.ndarray)) else "select_cols"
            rec = get_logger().record(
                op_name=op_name,
                obj_type="DataFrame",
                input_hash=input_hash,
                output_hash=output_hash,
                args=(key,),
                kwargs={},
                duration_ms=duration_ms,
                tags=("pandas",),
            )
            from provtrack.proxy import get_graph
            get_graph().add_record(rec)

        return out_obj

    def __setitem__(self, key: Any, value: Any) -> None:
        df = object.__getattribute__(self, "_df")
        in_hash = object.__getattribute__(self, "_input_hash")
        df[key] = value
        out_hash = _pandas_hasher.hash(df)
        object.__setattr__(self, "_input_hash", out_hash)
        rec = get_logger().record(
            op_name="__setitem__",
            obj_type="DataFrame",
            input_hash=in_hash,
            output_hash=out_hash,
            args=(key,),
            duration_ms=0.0,
            tags=("pandas",),
        )
        from provtrack.proxy import get_graph
        get_graph().add_record(rec)

    def __reduce__(self):
        raise TypeError(
            "DataFrameProxy cannot be pickled. "
            "Access the underlying DataFrame with proxy.unwrap() before pickling."
        )

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_df"))

    def __iter__(self):
        return iter(object.__getattribute__(self, "_df"))

    def __repr__(self) -> str:
        return repr(object.__getattribute__(self, "_df"))

    def __str__(self) -> str:
        return str(object.__getattribute__(self, "_df"))

    @property
    def current_hash(self) -> str:
        return object.__getattribute__(self, "_input_hash")

    def unwrap(self) -> pd.DataFrame:
        return object.__getattribute__(self, "_df")
