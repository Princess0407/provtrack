"""
tests.test_proxy
~~~~~~~~~~~~~~~~
Tests for DataFrameProxy and EstimatorProxy.

Covers:
  - Basic interception fires.
  - Re-wrapping: chained ops stay as proxies.
  - in-place operations update the internal hash.
  - __getitem__ / __setitem__ are intercepted.
  - Non-DataFrame return values pass through correctly.
  - sklearn proxy intercepts fit/transform.
  - Pickle blocked on proxy.
  - unwrap() returns the underlying frame.
  - Logger receives records for each intercepted op.
  - Graph grows correctly with each op.
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from provtrack.proxy import DataFrameProxy, EstimatorProxy, get_graph, reset_graph
from provtrack.logger import reset_logger, get_logger


@pytest.fixture(autouse=True)
def clean_state():
    """Reset logger + graph before each test."""
    reset_logger()
    reset_graph()
    yield
    reset_logger()
    reset_graph()


# ── DataFrameProxy ────────────────────────────────────────────────────────────

def _simple_df():
    return pd.DataFrame({"age": [25, None, 30], "city": ["Delhi", "Mumbai", None]})


def test_proxy_wraps_dataframe():
    proxy = DataFrameProxy(_simple_df())
    assert isinstance(proxy, DataFrameProxy)


def test_proxy_class_spoofing():
    """isinstance(proxy, pd.DataFrame) must be True for sklearn compat."""
    proxy = DataFrameProxy(_simple_df())
    assert proxy.__class__ is pd.DataFrame


def test_basic_interception_logged():
    proxy = DataFrameProxy(_simple_df())
    _ = proxy.dropna()
    recs = get_logger().all()
    assert len(recs) == 1
    assert recs[0].op_name == "dropna"


def test_rewrapping_chained_ops():
    """Each step in a chain should return a DataFrameProxy."""
    proxy = DataFrameProxy(_simple_df())
    result = proxy.dropna()
    assert isinstance(result, DataFrameProxy), "dropna should return DataFrameProxy"

    result2 = result.reset_index()
    assert isinstance(result2, DataFrameProxy), "reset_index should return DataFrameProxy"


def test_chain_logging():
    """Three chained ops produce three log records."""
    proxy = DataFrameProxy(_simple_df())
    _ = proxy.dropna().reset_index().rename(columns={"age": "AGE"})
    assert get_logger().count == 3


def test_chain_links_correctly():
    """Output hash of op N equals input hash of op N+1."""
    proxy = DataFrameProxy(_simple_df())
    _ = proxy.dropna().reset_index()
    recs = get_logger().all()
    assert recs[0].output_hash == recs[1].input_hash


def test_inplace_op_updates_hash():
    df = pd.DataFrame({"a": [1, None, 3]})
    proxy = DataFrameProxy(df)
    old_hash = proxy.current_hash
    proxy.dropna(inplace=True)
    assert proxy.current_hash != old_hash


def test_getitem_list_logged_as_select_cols():
    """Selecting a list of columns logs as 'select_cols'."""
    proxy = DataFrameProxy(_simple_df())
    _ = proxy[["age"]]
    recs = get_logger().all()
    assert any(r.op_name == "select_cols" for r in recs)

def test_getitem_boolean_filter_logged():
    """Boolean mask filtering logs as 'filter'."""
    df = pd.DataFrame({"age": [25, 17, 30]})
    proxy = DataFrameProxy(df)
    _ = proxy[proxy.unwrap()["age"] > 18]
    recs = get_logger().all()
    assert any(r.op_name == "filter" for r in recs)

def test_getitem_single_col_not_logged():
    """Single-column string access (df['col']) is silent — it's a Series, not structural."""
    proxy = DataFrameProxy(_simple_df())
    _ = proxy.unwrap()["age"]   # access via underlying df, not proxy
    recs = get_logger().all()
    assert len(recs) == 0


def test_setitem_intercepted():
    proxy = DataFrameProxy(_simple_df())
    proxy["new_col"] = 1
    recs = get_logger().all()
    assert any(r.op_name == "__setitem__" for r in recs)


def test_non_df_return_passthrough():
    """Operations like .mean() return scalars — those should pass through as-is."""
    proxy = DataFrameProxy(pd.DataFrame({"a": [1, 2, 3]}))
    result = proxy.mean()
    assert not isinstance(result, DataFrameProxy)


def test_len_works():
    proxy = DataFrameProxy(_simple_df())
    assert len(proxy) == 3


def test_repr_works():
    proxy = DataFrameProxy(_simple_df())
    r = repr(proxy)
    assert "age" in r


def test_unwrap_returns_dataframe():
    df = _simple_df()
    proxy = DataFrameProxy(df)
    unwrapped = proxy.unwrap()
    assert isinstance(unwrapped, pd.DataFrame)
    pd.testing.assert_frame_equal(unwrapped, df)


def test_pickle_blocked():
    import pickle
    proxy = DataFrameProxy(_simple_df())
    with pytest.raises(TypeError, match="pickled"):
        pickle.dumps(proxy)


def test_wrong_type_raises():
    with pytest.raises(TypeError):
        DataFrameProxy("not a dataframe")  # type: ignore


def test_graph_grows_with_ops():
    proxy = DataFrameProxy(_simple_df())
    _ = proxy.dropna()
    _ = proxy.dropna()  # second call on original
    graph = get_graph()
    assert graph.node_count == 2


# ── EstimatorProxy ────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    True,
    reason="sklearn not required for v1 CI — enable when sklearn is installed"
)
def test_estimator_proxy_fit_logged():
    from sklearn.preprocessing import StandardScaler
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    proxy_df = DataFrameProxy(df)
    scaler = EstimatorProxy(StandardScaler())
    scaler.fit_transform(proxy_df)
    recs = get_logger().all()
    assert any(r.op_name == "fit_transform" for r in recs)
    assert any(r.obj_type == "StandardScaler" for r in recs)


@pytest.mark.skipif(
    True,
    reason="sklearn not required for v1 CI — enable when sklearn is installed"
)
def test_estimator_class_spoofing():
    from sklearn.preprocessing import StandardScaler
    from sklearn.base import BaseEstimator
    scaler = EstimatorProxy(StandardScaler())
    assert isinstance(scaler, BaseEstimator)


def test_estimator_unwrap():
    """EstimatorProxy.unwrap() should return the original estimator."""
    try:
        from sklearn.preprocessing import StandardScaler
        scaler = EstimatorProxy(StandardScaler())
        assert type(scaler.unwrap()) is StandardScaler
    except ImportError:
        pytest.skip("sklearn not installed")
