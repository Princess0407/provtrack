"""
provtrack
~~~~~~~~~
Zero-instrumentation ML pipeline provenance tracking.

Quick start
-----------
    import provtrack
    provtrack.activate()

    import pandas as pd
    from sklearn.preprocessing import StandardScaler

    df = pd.read_csv("data.csv")     # auto-wrapped
    df = provtrack.wrap(df)           # or wrap manually

    scaler = provtrack.wrap(StandardScaler())
    X = scaler.fit_transform(df)

    print(provtrack.lineage().summary())
    print(provtrack.lineage().to_mermaid())
"""

from .activate import (
    activate,
    deactivate,
    reset,
    wrap,
    is_active,
    get_lineage as lineage,
    get_records as records,
)
from .proxy import DataFrameProxy, EstimatorProxy
from .graph import ProvenanceGraph
from .logger import OperationRecord, get_logger

__version__ = "0.1.0"
__author__ = "Princess"
__all__ = [
    "activate",
    "deactivate",
    "reset",
    "wrap",
    "is_active",
    "lineage",
    "records",
    "DataFrameProxy",
    "EstimatorProxy",
    "ProvenanceGraph",
    "OperationRecord",
    "__version__",
]
