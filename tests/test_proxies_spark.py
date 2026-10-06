from provtrack.proxies.spark import SparkProxy
from provtrack.logger import get_logger, reset_logger


class MockSparkDataFrame:
    __module__ = "pyspark.sql.dataframe"

    def __init__(self, cols, plan_id="p1") -> None:
        self.columns = cols
        self.schema = f"StructType({cols})"
        self._plan_id = plan_id

    def select(self, *cols):
        return MockSparkDataFrame(list(cols), plan_id=f"{self._plan_id}_select")

    def filter(self, condition):
        return MockSparkDataFrame(self.columns, plan_id=f"{self._plan_id}_filter")


def setup_function():
    reset_logger()


def test_spark_proxy_operations():
    df = MockSparkDataFrame(["a", "b", "c"])
    proxy = SparkProxy(df)

    p2 = proxy.select("a", "b")
    assert isinstance(p2, SparkProxy)
    assert p2.unwrap().columns == ["a", "b"]

    recs = get_logger().all()
    assert len(recs) == 1
    assert recs[0].op_name == "select"
    assert recs[0].tags == ("spark",)
