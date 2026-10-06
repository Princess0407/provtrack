from __future__ import annotations

import logging
import sys
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import pandas as pd
except Exception:
    pd = None

from provtrack.backends.base import Backend
from provtrack.backends.memory import MemoryBackend
from provtrack.backends.postgres import PostgresBackend
from provtrack.backends.s3 import S3Backend
from provtrack.backends.sqlite import SQLiteBackend
from provtrack.graph.builder import LineageGraph, ProvenanceGraph
from provtrack.hashers.dataframe import PandasHasher
from provtrack.logger import OperationRecord, get_logger, reset_logger
from provtrack.proxies.dataframe import DataFrameProxy
from provtrack.proxies.estimator import EstimatorProxy
from provtrack.proxies.spark import SparkProxy
from provtrack.proxies.tensor import TensorProxy

TOOL_ID: int = 1
_SYS_MONITORING_AVAILABLE: bool = sys.version_info >= (3, 12)
logger = logging.getLogger(__name__)

_activated: bool = False
_lock = threading.Lock()
_backend: Optional[Backend] = None
_graph: Optional[LineageGraph] = None
_run_id: str = str(uuid.uuid4())

_pandas_hasher = PandasHasher()
_local = threading.local()
_patches: Dict[str, Tuple[Any, str, Callable]] = {}

_INTERNAL_PATH_PARTS = (
    "/provtrack/activate.py",
    "/provtrack/logger.py",
    "/provtrack/hasher.py",
    "/provtrack/proxy.py",
    "/provtrack/hashers/",
    "/provtrack/backends/",
    "/provtrack/proxies/",
    "/provtrack/graph/",
    "/provtrack/exporters/",
)


def _is_internal_file(filename: str) -> bool:
    norm = filename.replace("\\", "/")
    if "pandas" in norm or "sklearn" in norm:
        return True
    return any(part in norm for part in _INTERNAL_PATH_PARTS)


def _get_pending() -> Tuple[Dict[int, Tuple[str, str]], Dict[Tuple[int, int], Tuple[str, str, Any, Any, float]]]:
    if not hasattr(_local, "pending_calls"):
        _local.pending_calls = {}
        _local.frame_calls = {}
    return _local.pending_calls, _local.frame_calls


def _on_call(code: Any, instruction_offset: int, callable_: Any, arg0: Any) -> Any:
    module = getattr(callable_, "__module__", "") or ""
    qualname = getattr(callable_, "__qualname__", "") or ""
    if "pandas" not in module and "sklearn" not in module:
        return sys.monitoring.DISABLE

    pending_calls, frame_calls = _get_pending()
    pending_calls[id(callable_)] = (qualname, module)

    frame = sys._getframe(1)
    frame_calls[(id(frame), instruction_offset)] = (
        qualname,
        module,
        getattr(callable_, "__self__", None),
        arg0,
        time.perf_counter(),
    )
    return None


def _on_return(code: Any, instruction_offset: int, retval: Any) -> Any:
    try:
        df_cls = getattr(pd, "DataFrame", None)
        if df_cls is None or not isinstance(retval, df_cls):
            return None
    except (TypeError, AttributeError):
        return None

    frame = sys._getframe(1)
    caller = frame.f_back
    if not caller:
        return None

    caller_file = caller.f_code.co_filename
    if _is_internal_file(caller_file):
        return None

    pending_calls, frame_calls = _get_pending()
    key = (id(caller), caller.f_lasti)
    call_info = frame_calls.pop(key, None)

    op_name = code.co_name
    input_hash: Optional[str] = None
    duration_ms = 0.0
    tags = ("pandas",)

    if call_info:
        qualname, module, self_obj, arg0, t_start = call_info
        duration_ms = (time.perf_counter() - t_start) * 1000
        op_name = qualname.split(".")[-1] or code.co_name
        if "sklearn" in module:
            tags = ("sklearn",)

        if isinstance(self_obj, pd.DataFrame):
            input_hash = _pandas_hasher.hash(self_obj)
        elif isinstance(arg0, pd.DataFrame):
            input_hash = _pandas_hasher.hash(arg0)
        elif isinstance(arg0, (list, tuple)):
            for item in arg0:
                if isinstance(item, pd.DataFrame):
                    input_hash = _pandas_hasher.hash(item)
                    break

    output_hash = _pandas_hasher.hash(retval)
    if input_hash is None and op_name.startswith("read_"):
        input_hash = "__source__"

    rec = OperationRecord(
        id=str(uuid.uuid4()),
        op_name=op_name,
        obj_type=type(retval).__name__,
        input_hash=input_hash,
        output_hash=output_hash,
        timestamp=time.time(),
        source_line=caller.f_lineno,
        source_file=caller_file,
        tags=tags,
        args_repr="",
        duration_ms=round(duration_ms, 3),
        caller_func=caller.f_code.co_name,
    )

    if _backend is not None:
        _backend.save([rec])
    if _graph is not None:
        _graph.add_record(rec)

    return None


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


def _wrap_pd_reader(original: Callable, name: str) -> Callable:
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if pd is not None and isinstance(result, pd.DataFrame):
            rec = get_logger().record(
                op_name=name,
                obj_type="DataFrame",
                input_hash="__source__",
                output_hash=None,
                args=args,
                kwargs=kwargs,
                duration_ms=0.0,
                tags=("pandas", "io"),
            )
            proxy = DataFrameProxy(result)
            import dataclasses
            fixed_rec = dataclasses.replace(rec, output_hash=proxy.current_hash)
            if _backend is not None:
                _backend.save([fixed_rec])
            if _graph is not None:
                _graph.add_record(fixed_rec)
            return proxy
        return result

    _wrapped.__name__ = name
    return _wrapped


def _setup_v1_fallback(patch_readers: bool = True) -> None:
    if pd is None or not patch_readers:
        return
    for reader_name in _PD_READERS:
        original = getattr(pd, reader_name, None)
        if original is None:
            continue
        wrapped = _wrap_pd_reader(original, reader_name)
        setattr(pd, reader_name, wrapped)
        _patches[f"pd.{reader_name}"] = (pd, reader_name, original)


def activate(
    backend: Union[str, Backend] = "memory",
    db_path: Optional[str] = None,
    dsn: Optional[str] = None,
    s3_uri: Optional[str] = None,
    *,
    patch_sklearn: bool = True,
    patch_pandas_readers: bool = True,
    verbose: bool = False,
    **backend_kwargs: Any,
) -> None:
    global _activated, _backend, _graph, _run_id

    with _lock:
        if _activated:
            if verbose:
                logger.debug("[provtrack] Already active.")
            return

        _run_id = str(uuid.uuid4())
        _graph = LineageGraph()

        if isinstance(backend, Backend):
            _backend = backend
        elif backend == "memory":
            _backend = MemoryBackend()
        elif backend == "sqlite":
            _backend = SQLiteBackend(db_path=db_path or "lineage.db", **backend_kwargs)
        elif backend == "postgres":
            _backend = PostgresBackend(dsn=dsn, **backend_kwargs)
        elif backend == "s3":
            _backend = S3Backend(s3_uri=s3_uri, **backend_kwargs)
        else:
            raise ValueError(f"Unknown backend: {backend}. Choose memory, sqlite, postgres, or s3.")

        if _SYS_MONITORING_AVAILABLE:
            try:
                sys.monitoring.use_tool_id(TOOL_ID, "provtrack")
            except ValueError:
                pass
            sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.CALL | sys.monitoring.events.PY_RETURN)
            sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.CALL, _on_call)
            sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_RETURN, _on_return)
        else:
            _setup_v1_fallback(patch_readers=patch_pandas_readers)

        _activated = True


def deactivate() -> None:
    global _activated, _backend, _graph

    with _lock:
        if not _activated:
            return

        if _SYS_MONITORING_AVAILABLE:
            try:
                sys.monitoring.set_events(TOOL_ID, 0)
                sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.CALL, None)
                sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_RETURN, None)
                sys.monitoring.free_tool_id(TOOL_ID)
            except Exception:
                pass
        else:
            for key, (obj, attr, original) in _patches.items():
                try:
                    setattr(obj, attr, original)
                except (AttributeError, TypeError):
                    pass
            _patches.clear()

        if isinstance(_backend, MemoryBackend):
            _backend.clear()

        reset_logger()
        _backend = None
        _graph = None
        _activated = False


def reset() -> None:
    global _graph
    with _lock:
        if _backend is not None:
            _backend.clear()
        _graph = LineageGraph()
        reset_logger()


def is_active() -> bool:
    return _activated


def get_backend() -> Optional[Backend]:
    return _backend


def get_run_id() -> str:
    return _run_id


def get_lineage() -> LineageGraph:
    if _backend is not None:
        records = _backend.load()
        return LineageGraph.from_records(records)
    if _graph is not None:
        return _graph
    return LineageGraph()


def lineage() -> LineageGraph:
    return get_lineage()


def get_records() -> List[OperationRecord]:
    if _backend is not None:
        return _backend.load()
    if not _activated:
        return []
    return get_logger().all()


def records() -> List[OperationRecord]:
    return get_records()


def wrap(obj: Any) -> Any:
    if pd is not None and isinstance(obj, pd.DataFrame):
        return DataFrameProxy(obj)
    try:
        from sklearn.base import BaseEstimator
        if isinstance(obj, BaseEstimator):
            return EstimatorProxy(obj)
    except ImportError:
        pass

    obj_mod = getattr(type(obj), "__module__", "")
    if "pyspark" in obj_mod or hasattr(obj, "_jdf"):
        return SparkProxy(obj)
    if "torch" in obj_mod or "tensorflow" in obj_mod or hasattr(obj, "detach"):
        return TensorProxy(obj)

    raise TypeError(
        f"provtrack.wrap() does not support {type(obj).__name__}. "
        "Supported: pd.DataFrame, sklearn estimators, PyTorch/TF tensors, PySpark DataFrames."
    )
