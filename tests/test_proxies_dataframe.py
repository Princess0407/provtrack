import pandas as pd
import pytest

from provtrack.proxies.dataframe import DataFrameProxy
from provtrack.logger import get_logger, reset_logger


def setup_function():
    reset_logger()


def test_dataframe_proxy_interception():
    df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
    proxy = DataFrameProxy(df)

    res = proxy.dropna()
    assert isinstance(res, DataFrameProxy)
    assert len(res) == 2

    recs = get_logger().all()
    assert len(recs) == 1
    assert recs[0].op_name == "dropna"
    assert recs[0].output_hash == res.current_hash


def test_dataframe_proxy_type_error():
    with pytest.raises(TypeError, match="DataFrameProxy requires a pd.DataFrame"):
        DataFrameProxy("not-a-df")
