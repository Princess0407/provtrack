from .base import BaseProxy
from .dataframe import DataFrameProxy
from .estimator import EstimatorProxy
from .spark import SparkProxy
from .tensor import TensorProxy

__all__ = [
    "BaseProxy",
    "DataFrameProxy",
    "EstimatorProxy",
    "TensorProxy",
    "SparkProxy",
]
