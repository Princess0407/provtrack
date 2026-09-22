# INTERNALS.md

Personal architecture notes — why each decision was made.  
This doubles as interview prep.  Every section here is something you should be able to explain cold.

---

## Why a proxy over `__getattr__`, not import hooks?

Import hooks (`sys.meta_path`) fire when a module is *imported*, not when a method is *called*.  You can use them to swap the `pd.DataFrame` class at import time, but then you'd need to handle every import path (`import pandas`, `from pandas import DataFrame`, `import pandas as pd`) — all of which have different resolution paths.  It's also extremely fragile in a warm Jupyter kernel where the module is already cached in `sys.modules`.

Class-level attribute interception via `__getattr__` fires at the Python object level, on every call, regardless of how the user imported pandas.  It's explicit, reversible, and easy to reason about.  That's the right tradeoff for v1.

The research paper cited `sys.monitoring` (PEP 669, Python 3.12+) as a future direction — a kernel-level tracing hook that fires on every function call without any class patching.  That's the right architecture for v2 (truly zero-instrumentation, no proxy at all), but it requires Python 3.12+ and is significantly more complex to implement correctly.

---

## Why SHA-256 and not Python's built-in `hash()`?

Python's `hash()` is not stable across processes.  If you run your pipeline on Monday and save the hash, then run it again on Tuesday in a new Python process, the same data may produce a different hash due to hash randomisation (`PYTHONHASHSEED`).  This would break any lineage comparison across runs.

`pd.util.hash_pandas_object` produces per-row uint64 hashes that are stable across processes.  We then collapse those into a single digest via SHA-256 to get a short, fixed-length fingerprint.

Why not just `df.to_string().encode()` + SHA-256?  Two reasons: `to_string()` truncates large DataFrames, and string serialisation is much slower than `hash_pandas_object`'s vectorised C implementation.

---

## Why exclude the index from hashing by default?

`reset_index()` on an unchanged DataFrame renumbers the row labels but doesn't change the data.  If we included the index in the hash, `reset_index()` would always appear as a new lineage node even if the data content is identical — creating noise in the graph.

The default (`hash_index=False`) means the hash captures what the data *is*, not where the rows happen to be numbered.  Users who care about index state (e.g. time-series data where the index is the timestamp) can opt in with `hash_index=True`.

---

## Why `frozen=True` on `OperationRecord`?

Audit integrity.  A provenance record that can be mutated after the fact is not a provenance record — it's a log that someone might have tampered with.  Making it a frozen dataclass means the record is guaranteed immutable from the moment it's created.

In v2, we'd want cryptographic signatures on records so that a tampered session file is detectable.

---

## Why networkx for the DAG?

For v1, networkx is the right choice: it's a mature Python library, well-understood by ML engineers, and has built-in functions for everything we need (`topological_sort`, `ancestors`, `descendants`, `shortest_path`, `is_directed_acyclic_graph`).

For v2 (startup scale), we'd want to replace the in-memory networkx graph with a persistent graph database (Neo4j or Amazon Neptune) so lineage is queryable across sessions and teams.  The `ProvenanceGraph` class is designed to make this swap straightforward — the interface would stay the same, only the backing store changes.

---

## The re-wrapping problem

The most common bug in proxy-based interception:

```python
result = df.dropna()
type(result)  # pd.DataFrame, not DataFrameProxy
result.reset_index()  # NOT tracked
```

When `dropna()` is called on the proxy, it delegates to the real DataFrame's `dropna()`, which returns a *real* DataFrame.  The proxy never sees that return value.

The fix is in `__getattr__`'s wrapper function: after calling the real method, we check `isinstance(result, pd.DataFrame)` and if True, wrap the result in a new `DataFrameProxy` before returning it.  This means every method in a chain returns a proxy, so every subsequent call is intercepted.

The corollary: we use `object.__getattribute__` to access `self._df` inside the proxy, not `self._df` directly — because `self._df` would trigger `__getattr__` again, creating infinite recursion.

---

## Why `__slots__` on the proxies?

Two reasons:
1. Memory: without `__slots__`, Python allocates a `__dict__` on every proxy instance.  For pipelines that create many intermediate DataFrames, that's overhead.
2. Safety: `__slots__` prevents accidental attribute assignment on the proxy (`proxy.some_attr = value` would otherwise silently create a new attribute on the proxy, shadowing the underlying DataFrame's attribute).

---

## Why is `activate()` idempotent?

Calling `activate()` twice in a script (or from two imported modules that both call it) should not double-patch pandas.  The `_activated` flag and the lock ensure the patches are only applied once, and the `_patches` dict stores the originals so `deactivate()` always restores exactly what was there.

---

## The `__class__` spoof

sklearn internally does `isinstance(estimator, BaseEstimator)` checks in `Pipeline`, `clone()`, and other utilities.  If `EstimatorProxy.__class__` returns `EstimatorProxy`, those checks fail and sklearn breaks.

The fix: define `__class__` as a property that returns `type(self._estimator)`.  This way `isinstance(proxy, StandardScaler)` returns True, and sklearn's internal plumbing works as expected.

The same trick is used on `DataFrameProxy` — `__class__` returns `pd.DataFrame` so any external code doing `isinstance(df, pd.DataFrame)` still works.

---

## What v2 needs that v1 doesn't have

1. `sys.monitoring` (PEP 669) tracing — truly zero-instrumentation, no proxy at all.
2. Pluggable storage backends (SQLite, Postgres, S3) via a `Backend` interface.
3. PySpark DataFrame proxy — same architecture, different class.
4. Persistent session storage so lineage survives process restarts.
5. Team-scale graph database backing (Neo4j / Neptune).
6. Web UI — interactive DAG visualisation.
7. OpenLineage export — industry standard lineage format for integrations.
8. Cryptographic signatures on records for tamper detection.
