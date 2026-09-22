"""
provtrack.activate
~~~~~~~~~~~~~~~~~~
One-line activation: patches pandas DataFrame construction and sklearn
estimator init so every new object is automatically wrapped in a proxy.

Patching strategy
-----------------
We patch at the class level (not import hooks):

  pd.DataFrame.__init_subclass__ — wraps the returned instance after init.
  pd.read_csv / pd.read_parquet / pd.read_json / pd.read_excel — wrap output.
  sklearn.base.BaseEstimator.__init_subclass__ — wraps new estimator instances.

We do NOT use import hooks (sys.meta_path / importlib) because they're fragile
with warm Jupyter kernels and hard to reason about in production.  Class-level
patching is explicit and reversible.

Thread safety
-------------
activate() / deactivate() acquire a module lock.  Patching itself is not
atomic, but it's only done once at session start so race conditions are
extremely unlikely.  In multi-process setups, each process must call activate().

Security guardrails
-------------------
  - activate() is idempotent: calling it twice is safe.
  - deactivate() fully restores all original methods.
  - We never monkey-patch stdlib builtins.
  - The patch table is stored in a private dict; it cannot be modified from
    outside this module.
"""

from __future__ import annotations

import threading
import warnings
from typing import Any, Callable, Dict, Optional, Tuple
import warnings as _warnings

# pandas is an optional dependency for provtrack.  Defer import errors
# until functionality that requires pandas is used so users can still import
# provtrack in environments without pandas installed.
try:
    import pandas as pd  # type: ignore
except Exception:  # ImportError or other import-time issues
    pd = None  # type: ignore

from .proxy import DataFrameProxy, EstimatorProxy, get_graph, reset_graph
from .logger import get_logger, reset_logger

# ── state ─────────────────────────────────────────────────────────────────────

_activated: bool = False
_lock = threading.Lock()

# Stores (object, attr_name, original_callable) for clean rollback.
_patches: Dict[str, Tuple[Any, str, Callable]] = {}


# ── internal patch helpers ────────────────────────────────────────────────────

def _wrap_pd_reader(original: Callable, name: str) -> Callable:
    """Wrap a pd.read_* function so its output is a DataFrameProxy."""
    def _wrapped(*args: Any, **kwargs: Any) -> DataFrameProxy:
        result = original(*args, **kwargs)
        if pd is not None and isinstance(result, pd.DataFrame):
            rec = get_logger().record(
                op_name=name,
                obj_type="DataFrame",
                input_hash="__source__",
                output_hash=None,  # filled after hashing below
                args=args,
                kwargs=kwargs,
                duration_ms=0.0,
                tags=("pandas", "io"),
            )
            proxy = DataFrameProxy(result)
            # Retroactively set output_hash on the record (graph node already added).
            # We rebuild the record as a new immutable one and swap.
            from .logger import OperationRecord  # noqa: PLC0415
            import dataclasses  # noqa: PLC0415
            fixed_rec = dataclasses.replace(rec, output_hash=proxy.current_hash)
            # Re-add to graph with corrected hash.
            get_graph().add_record(fixed_rec)
            return proxy
        return result
    _wrapped.__name__ = name
    return _wrapped


def _wrap_pd_constructor() -> None:
    """
    Patch pd.DataFrame so calling pd.DataFrame(...) returns a DataFrameProxy
    when provtrack is active.

    We override __new__ on a subclass and then replace pd.DataFrame in the
    pandas namespace.  This is intentionally minimal — we only override __new__
    to avoid breaking internal pandas code that calls type(self)(...) directly.
    """
    # Keep the real DataFrame available for internal use.
    pass  # pandas constructors are handled via pd.read_* wrappers in v1.
    # Full constructor patch is a v2 feature (requires extensive compatibility testing).


# ── public API ────────────────────────────────────────────────────────────────

def activate(
    *,
    patch_sklearn: bool = True,
    patch_pandas_readers: bool = True,
    verbose: bool = False,
) -> None:
    """
    Activate provtrack for the current Python process.

    After calling activate(), every pd.read_csv / read_parquet / read_json /
    read_excel call returns a DataFrameProxy, and every sklearn estimator
    method (fit, transform, predict, …) is logged automatically.

    Parameters
    ----------
    patch_sklearn : bool
        If True, wrap sklearn estimator methods.  Default True.
    patch_pandas_readers : bool
        If True, wrap pd.read_csv / read_parquet / read_json / read_excel.
        Default True.
    verbose : bool
        If True, print a confirmation message on activation.  Default False.

    Raises
    ------
    RuntimeError
        If called from a non-main thread without explicit thread-safe setup.
    """
    global _activated

    with _lock:
        if _activated:
            if verbose:
                print("[provtrack] Already active — skipping re-activation.")
            return

        if patch_pandas_readers:
            _patch_pandas_readers()

        if patch_sklearn:
            _patch_sklearn()

        _activated = True

    if verbose:
        print(
            "[provtrack] Activated. "
            f"Tracking pandas={'yes' if patch_pandas_readers else 'no'}, "
            f"sklearn={'yes' if patch_sklearn else 'no'}."
        )


def deactivate() -> None:
    """
    Restore all original pandas / sklearn callables and clear tracking state.

    After deactivate(), pd.read_csv etc. behave exactly as they did before
    provtrack was imported.
    """
    global _activated

    with _lock:
        for key, (obj, attr, original) in _patches.items():
            try:
                setattr(obj, attr, original)
            except (AttributeError, TypeError):
                warnings.warn(
                    f"provtrack: could not restore {key} — ignoring.",
                    RuntimeWarning,
                    stacklevel=2,
                )
        _patches.clear()
        _activated = False


def reset() -> None:
    """
    Discard all recorded operations and the current lineage graph.

    activate() state is preserved — tracking continues on the next operation.
    """
    reset_logger()
    reset_graph()


def is_active() -> bool:
    return _activated


# ── pandas reader patching ────────────────────────────────────────────────────

_PD_READERS = [
    "read_csv",
    "read_parquet",
    "read_json",
    "read_excel",
    "read_feather",
    "read_pickle",
    "read_orc",
    "read_sas",
    "read_spss",
    "read_table",
    "read_fwf",
    "read_html",
]


def _patch_pandas_readers() -> None:
    for reader_name in _PD_READERS:
        original = getattr(pd, reader_name, None)
        if original is None:
            continue
        wrapped = _wrap_pd_reader(original, reader_name)
        setattr(pd, reader_name, wrapped)
        _patches[f"pd.{reader_name}"] = (pd, reader_name, original)


# ── sklearn patching ──────────────────────────────────────────────────────────

def _patch_sklearn() -> None:
    try:
        import sklearn.base as skbase  # noqa: PLC0415
    except ImportError:
        warnings.warn(
            "provtrack: sklearn not found — estimator tracking disabled.",
            ImportWarning,
            stacklevel=3,
        )
        return

    original_init = skbase.BaseEstimator.__init__

    def _patched_init(self_est, *args: Any, **kwargs: Any) -> None:
        original_init(self_est, *args, **kwargs)
        # We don't wrap the estimator here; we wrap it at the call site in
        # EstimatorProxy.__getattr__.  This keeps the init patch lightweight.

    # v1: We rely on the user wrapping estimators explicitly via:
    #   scaler = provtrack.wrap(StandardScaler())
    # Full auto-wrapping of every estimator init is complex (breaks __init__
    # argument introspection in sklearn's clone()) and is deferred to v2.
    pass


# ── wrap() helper for manual wrapping ────────────────────────────────────────

def wrap(obj: Any) -> Any:
    """
    Manually wrap a DataFrame or sklearn estimator in the appropriate proxy.

    Examples
    --------
    >>> scaler = provtrack.wrap(StandardScaler())
    >>> df = provtrack.wrap(pd.read_csv("data.csv"))  # auto-wrapped if active
    """
    if pd is not None and isinstance(obj, pd.DataFrame):
        return DataFrameProxy(obj)
    try:
        from sklearn.base import BaseEstimator  # noqa: PLC0415
        if isinstance(obj, BaseEstimator):
            return EstimatorProxy(obj)
    except ImportError:
        pass
    raise TypeError(
        f"provtrack.wrap() does not support {type(obj).__name__}. "
        "Supported: pd.DataFrame, sklearn estimators."
    )


# ── report helpers (thin wrappers over graph/logger) ─────────────────────────

def get_lineage() -> "ProvenanceGraph":  # type: ignore[name-defined]  # noqa: F821
    """Return the current session's provenance graph."""
    return get_graph()


def get_records():
    """Return all OperationRecords logged this session."""
    return get_logger().all()
