from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from provtrack.hashers.array import ArrayHasher
from provtrack.hashers.dataframe import PandasHasher
from provtrack.hasher import hash_sklearn_params
from provtrack.logger import get_logger
from .base import BaseProxy
from .dataframe import DataFrameProxy

_pandas_hasher = PandasHasher()
_array_hasher = ArrayHasher()

_SKLEARN_TRACKED_METHODS = frozenset({
    "fit",
    "transform",
    "fit_transform",
    "predict",
    "predict_proba",
    "predict_log_proba",
    "score",
    "inverse_transform",
})


class EstimatorProxy(BaseProxy):
    __slots__ = ("_estimator", "_estimator_hash")

    @property
    def __class__(self):
        return type(object.__getattribute__(self, "_estimator"))

    def __init__(self, estimator: Any) -> None:
        object.__setattr__(self, "_estimator", estimator)
        try:
            params = estimator.get_params(deep=True)
        except Exception:
            params = {}
        object.__setattr__(self, "_estimator_hash", hash_sklearn_params(params))

    def __getattr__(self, name: str) -> Any:
        est = object.__getattribute__(self, "_estimator")
        attr = getattr(est, name)

        if name not in _SKLEARN_TRACKED_METHODS or not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            estimator_hash = object.__getattribute__(self, "_estimator_hash")

            input_hash = estimator_hash
            if args:
                x = args[0]
                if isinstance(x, DataFrameProxy):
                    input_hash = x.current_hash
                elif isinstance(x, pd.DataFrame):
                    input_hash = _pandas_hasher.hash(x)
                elif isinstance(x, np.ndarray):
                    input_hash = _array_hasher.hash(x)

            t_start = time.perf_counter()
            result = attr(*args, **kwargs)
            duration_ms = (time.perf_counter() - t_start) * 1000

            if isinstance(result, pd.DataFrame):
                output_hash = _pandas_hasher.hash(result)
                out = DataFrameProxy(result)
            elif isinstance(result, np.ndarray):
                output_hash = _array_hasher.hash(result)
                out = result
            else:
                output_hash = None
                out = result

            rec = get_logger().record(
                op_name=name,
                obj_type=type(est).__name__,
                input_hash=input_hash,
                output_hash=output_hash,
                args=args,
                kwargs=kwargs,
                duration_ms=duration_ms,
                tags=("sklearn",),
            )
            from provtrack.proxy import get_graph
            get_graph().add_record(rec)

            return out

        return _wrapped

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("_estimator", "_estimator_hash"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_estimator"), name, value)

    def __repr__(self) -> str:
        return repr(object.__getattribute__(self, "_estimator"))

    def unwrap(self) -> Any:
        return object.__getattribute__(self, "_estimator")
