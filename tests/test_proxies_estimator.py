import pandas as pd
from sklearn.preprocessing import StandardScaler

from provtrack.proxies.estimator import EstimatorProxy
from provtrack.proxies.dataframe import DataFrameProxy
from provtrack.logger import get_logger, reset_logger


def setup_function():
    reset_logger()


def test_estimator_proxy_fit_transform():
    scaler = EstimatorProxy(StandardScaler())
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]})
    proxy_df = DataFrameProxy(df)

    res = scaler.fit_transform(proxy_df)
    recs = get_logger().all()
    assert len(recs) == 1
    assert recs[0].op_name == "fit_transform"
    assert recs[0].input_hash == proxy_df.current_hash
