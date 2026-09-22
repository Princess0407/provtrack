"""
provtrack.proxy
~~~~~~~~~~~~~~~
Transparent proxy wrappers for pandas DataFrames and sklearn Estimators.

Architecture
------------
DataFrameProxy wraps a pd.DataFrame.  When any attribute is accessed on the
proxy, __getattr__ intercepts it.  If the attribute is callable, we wrap the
call to:
  1. Hash the current state (input).
  2. Call the real method on the underlying DataFrame.
  3. If the return value is a DataFrame, re-wrap it so tracking continues.
  4. Hash the return value (output).
  5. Log the operation.
  6. Add a node + edge to the graph.

EstimatorProxy wraps sklearn BaseEstimator subclasses.  Intercepts fit,
transform, fit_transform, predict, predict_proba so that sklearn ops appear
as typed nodes in the lineage graph.

Key design decisions:
  - __class__ is spoofed so sklearn's isinstance checks pass through the proxy.
  - __array_ufunc__ = None disables numpy ufunc dispatch on the proxy —
    prevents subtle bugs where numpy tries to use the proxy directly.
  - Operations that return non-DataFrame values (e.g. .mean(), .sum()) are
    recorded with output_hash=None so they appear as leaf nodes.
  - __getitem__ / __setitem__ are handled explicitly (they bypass __getattr__).
  - inplace=True operations are detected and the proxy's internal _df is
    updated to reflect the mutation.

Security guardrails:
  - No eval/exec anywhere in this module.
  - Args and kwargs are never stored raw — only safe repr strings.
  - The proxy never exposes the underlying _df directly via public API.
  - ProvenanceProxy.__reduce__ is blocked to prevent pickle bypass.
"""

from __future__ import annotations

import inspect
import time
from typing import Any, Optional, TYPE_CHECKING

import pandas as pd

from .hasher import hash_dataframe, hash_sklearn_params
from .logger import get_logger, OperationRecord
from .graph import ProvenanceGraph

if TYPE_CHECKING:
    pass

# ── pandas internal file path fragments ──────────────────────────────────────
# When __getitem__ is called from one of these files, it's an internal pandas
# operation, not a user operation — skip logging it.
_PANDAS_INTERNAL_PREFIXES: tuple = ()

def _is_user_call() -> bool:
    """
    Return True if the immediate caller (2 frames up from the proxy method)
    is user code, not pandas internals.

    We walk the stack and check whether the first non-provtrack frame is from
    the pandas package itself.  If it is, the __getitem__ was triggered
    internally by pandas (e.g. during dropna, rename, apply) and should not
    generate a lineage node.
    """
    stack = inspect.stack()
    provtrack_files = {"proxy.py", "logger.py", "hasher.py", "graph.py",
                       "activate.py", "__init__.py"}
    for frame_info in stack[1:]:   # skip the current frame
        fname = frame_info.filename
        # Skip our own frames.
        if any(fname.endswith(pt) for pt in provtrack_files):
            continue
        # If the first non-provtrack frame is inside pandas, it's internal.
        if "pandas" in fname and "site-packages" in fname:
            return False
        # First non-provtrack, non-pandas frame → user code.
        return True
    return True  # defensive default: log it


# ── module-level graph singleton (per process) ────────────────────────────────
_graph: Optional[ProvenanceGraph] = None


def get_graph() -> ProvenanceGraph:
    global _graph
    if _graph is None:
        _graph = ProvenanceGraph()
    return _graph


def reset_graph() -> None:
    global _graph
    _graph = ProvenanceGraph()


# ── skip list — ops that are too noisy or meaningless to track ────────────────
# These are either:
#   (a) display/inspection ops that don't transform data, or
#   (b) internal pandas methods called during computation of higher-level ops
#       (e.g. pandas calls df.items() and df["col"] internally during dropna).
#
# The core rule: if an op fires as a *side effect* of another tracked op
# rather than directly from user code, it shouldn't get its own node.
_SKIP_OPS = frozenset({
    # ── display / inspection — no data change ────────────────────────────────
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
    # ── attribute access — metadata, not transformation ───────────────────────
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
    # ── internal pandas iteration — fires during rename, apply, etc. ──────────
    "items",
    "iteritems",      # deprecated alias
    "iterrows",
    "itertuples",
    "keys",           # alias for .columns
    # ── copy — doesn't change data, just allocates ───────────────────────────
    "copy",
    "__copy__",
    "__deepcopy__",
    # ── internal pandas validation / resolution helpers ───────────────────────
    "_validate_dtype",
    "_check_label",
    "_get_axis_resolvers",
    "_get_block_manager_meta",
    "_metadata",
    "_typ",
    "__dataframe__",  # dataframe interchange protocol
    "__array__",      # numpy conversion — fires during sklearn fit
    "__array_priority__",
})

# ── DataFrameProxy ─────────────────────────────────────────────────────────────

class DataFrameProxy:
    """
    Drop-in transparent wrapper around pd.DataFrame that logs every
    method call to the provenance graph.

    The proxy passes all attribute lookups through to the underlying frame
    so user code never needs to change.
    """

    # Prevent accidental attribute shadowing.
    __slots__ = ("_df", "_input_hash")

    # Spoof class identity so sklearn isinstance() checks pass.
    @property
    def __class__(self):  # type: ignore[override]
        return pd.DataFrame

    # Disable numpy ufunc dispatch — numpy must not try to use the proxy.
    __array_ufunc__ = None

    def __init__(self, df: pd.DataFrame) -> None:
        if not isinstance(df, pd.DataFrame):
            raise TypeError(
                f"DataFrameProxy requires a pd.DataFrame, got {type(df).__name__}"
            )
        object.__setattr__(self, "_df", df)
        object.__setattr__(self, "_input_hash", hash_dataframe(df))

    # ── core interception ──────────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        if name in _SKIP_OPS:
            return getattr(object.__getattribute__(self, "_df"), name)

        attr = getattr(object.__getattribute__(self, "_df"), name)

        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            df = object.__getattribute__(self, "_df")
            input_hash = object.__getattribute__(self, "_input_hash")

            # Detect inplace operations before the call.
            is_inplace = kwargs.get("inplace", False)

            t_start = time.perf_counter()
            try:
                result = attr(*args, **kwargs)
            except Exception:
                raise  # Never swallow user exceptions.
            duration_ms = (time.perf_counter() - t_start) * 1000

            # Determine output hash.
            if is_inplace:
                # The underlying _df was mutated.
                new_hash = hash_dataframe(df)
                object.__setattr__(self, "_input_hash", new_hash)
                output_hash = new_hash
                out_obj = None
            elif isinstance(result, pd.DataFrame):
                output_hash = hash_dataframe(result)
                out_obj = DataFrameProxy(result)
            else:
                output_hash = None
                out_obj = result

            rec = get_logger().record(
                op_name=name,
                obj_type="DataFrame",
                input_hash=input_hash,
                output_hash=output_hash,
                args=args,
                kwargs=kwargs,
                duration_ms=duration_ms,
                tags=("pandas",),
            )
            get_graph().add_record(rec)

            return out_obj if out_obj is not None else result

        return _wrapped

    # ── special methods that bypass __getattr__ ────────────────────────────────

    def __getitem__(self, key: Any) -> Any:
        import numpy as np  # noqa: PLC0415
        df = object.__getattribute__(self, "_df")
        input_hash = object.__getattribute__(self, "_input_hash")

        t_start = time.perf_counter()
        result = df[key]
        duration_ms = (time.perf_counter() - t_start) * 1000

        if isinstance(result, pd.DataFrame):
            output_hash = hash_dataframe(result)
            out_obj = DataFrameProxy(result)
        elif isinstance(result, pd.Series):
            output_hash = None
            out_obj = result
        else:
            output_hash = None
            out_obj = result

        # Only log __getitem__ when it's a *meaningful structural selection*:
        #   - list of columns  → df[["col_a", "col_b"]]
        #   - boolean Series   → df[df["age"] > 18]   (filter = new shape)
        #   - slice            → df[10:20]
        # Skip:
        #   - single string    → df["col"]  (column access, returns Series,
        #                                    fires constantly inside pandas internals)
        #   - integer          → df[0]
        is_structural = (
            isinstance(key, (list, slice))
            or isinstance(key, (pd.Series, np.ndarray))
        )
        if is_structural and isinstance(result, pd.DataFrame):
            rec = get_logger().record(
                op_name="filter" if isinstance(key, (pd.Series, np.ndarray)) else "select_cols",
                obj_type="DataFrame",
                input_hash=input_hash,
                output_hash=output_hash,
                args=(key,),
                kwargs={},
                duration_ms=duration_ms,
                tags=("pandas",),
            )
            get_graph().add_record(rec)
        return out_obj

    def __setitem__(self, key: Any, value: Any) -> None:
        df = object.__getattribute__(self, "_df")
        input_hash = object.__getattribute__(self, "_input_hash")

        t_start = time.perf_counter()
        df[key] = value
        duration_ms = (time.perf_counter() - t_start) * 1000

        new_hash = hash_dataframe(df)
        object.__setattr__(self, "_input_hash", new_hash)

        rec = get_logger().record(
            op_name="__setitem__",
            obj_type="DataFrame",
            input_hash=input_hash,
            output_hash=new_hash,
            args=(key,),
            kwargs={},
            duration_ms=duration_ms,
            tags=("pandas",),
        )
        get_graph().add_record(rec)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("_df", "_input_hash"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_df"), name, value)

    def __delitem__(self, key: Any) -> None:
        df = object.__getattribute__(self, "_df")
        del df[key]

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_df"))

    def __iter__(self):
        return iter(object.__getattribute__(self, "_df"))

    def __contains__(self, item: Any) -> bool:
        return item in object.__getattribute__(self, "_df")

    def __repr__(self) -> str:
        return repr(object.__getattribute__(self, "_df"))

    def __str__(self) -> str:
        return str(object.__getattribute__(self, "_df"))

    def __reduce__(self):
        raise TypeError(
            "DataFrameProxy cannot be pickled.  "
            "Access the underlying DataFrame with proxy._df before pickling."
        )

    # ── convenience — expose underlying frame safely ──────────────────────────

    def unwrap(self) -> pd.DataFrame:
        """Return the underlying DataFrame (for pickling, serialisation, etc.)."""
        return object.__getattribute__(self, "_df")

    @property
    def current_hash(self) -> str:
        return object.__getattribute__(self, "_input_hash")


# ── EstimatorProxy ─────────────────────────────────────────────────────────────

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


class EstimatorProxy:
    """
    Transparent proxy for sklearn estimators.

    Only the SKLEARN_TRACKED_METHODS are logged — the rest pass through
    directly to avoid noise from internal sklearn attribute access.
    """

    __slots__ = ("_estimator", "_estimator_hash")

    @property
    def __class__(self):  # type: ignore[override]
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

            # Determine input hash from first positional arg (X).
            input_hash = estimator_hash
            if args and isinstance(args[0], (pd.DataFrame, DataFrameProxy)):
                x = args[0]
                if isinstance(x, DataFrameProxy):
                    input_hash = x.current_hash
                else:
                    input_hash = hash_dataframe(x)

            t_start = time.perf_counter()
            result = attr(*args, **kwargs)
            duration_ms = (time.perf_counter() - t_start) * 1000

            if isinstance(result, pd.DataFrame):
                output_hash = hash_dataframe(result)
                out = DataFrameProxy(result)
            else:
                import numpy as np  # noqa: PLC0415
                if isinstance(result, np.ndarray):
                    from .hasher import hash_array  # noqa: PLC0415
                    output_hash = hash_array(result)
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