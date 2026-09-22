# EDGE_CASES.md

Every edge case encountered or anticipated during the build.  Update this as you find new ones.

---

## EC-1: Chained operations lose tracking after first method

**Problem:** `df.dropna()` returns a real `pd.DataFrame`, not a `DataFrameProxy`.  The next call in the chain (`result.reset_index()`) runs on the unwrapped frame and is never logged.

**Fix:** In `__getattr__`'s wrapper, always check `isinstance(result, pd.DataFrame)` and re-wrap if True before returning.

**Test:** `test_rewrapping_chained_ops` in `test_proxy.py`.

---

## EC-2: In-place operations don't return a value

**Problem:** `df.dropna(inplace=True)` returns `None`.  The underlying DataFrame is mutated.  Our wrapper returns `None`, which is correct, but we need to re-hash `self._df` to record the new state.

**Fix:** Detect `kwargs.get("inplace", False)` before calling the real method.  After the call, re-hash `self._df` and update `self._input_hash`.

**Test:** `test_inplace_op_updates_hash` in `test_proxy.py`.

---

## EC-3: `__getitem__` and `__setitem__` bypass `__getattr__`

**Problem:** `df["col"]` and `df["col"] = value` resolve via Python's special method lookup, which does NOT go through `__getattr__`.

**Fix:** Override `__getitem__` and `__setitem__` explicitly on `DataFrameProxy`.

**Test:** `test_getitem_intercepted`, `test_setitem_intercepted`.

---

## EC-4: NaN in float columns

**Problem:** `float("nan") != float("nan")` in Python.  Naively hashing a DataFrame with NaN will break equality checks.

**Fix:** `pd.util.hash_pandas_object` handles NaN values correctly — two NaN values in the same position produce the same row hash.  No extra handling needed.

**Test:** `test_nan_values_consistent` in `test_hasher.py`.

---

## EC-5: Object-dtype columns with mixed types

**Problem:** A column with dtype `object` can contain integers, strings, None, and floats in the same column.  `pd.util.hash_pandas_object` may handle this inconsistently for exotic types.

**Fix:** Cast all object-dtype columns to `str` before hashing (via `_normalise_object_cols`).  This sacrifices type precision in the hash in exchange for stability.

**Test:** `test_object_dtype_mixed_types` in `test_hasher.py`.

---

## EC-6: Large DataFrames → performance cliff

**Problem:** SHA-256 hashing a 10M-row DataFrame takes several seconds, making provtrack unacceptable for large-scale pipelines.

**Fix:** When `len(df) > SAMPLE_ROW_LIMIT` (default 100,000), hash a reservoir sample.  The sample is seeded (`SAMPLE_SEED=42`) so the same frame always produces the same sample and therefore the same hash.  A warning is emitted.  The full hash can be forced via `PROVTRACK_FULL_HASH=1` env var (not yet implemented — v2).

**Test:** `test_large_frame_triggers_warning`, `test_large_frame_same_data_same_hash`.

---

## EC-7: `isinstance(proxy, pd.DataFrame)` fails

**Problem:** `isinstance(proxy, pd.DataFrame)` returns `False` for `DataFrameProxy` instances.  This breaks sklearn Pipelines and any library that type-checks its inputs.

**Fix:** Override `__class__` as a property returning `pd.DataFrame`.  Python's `isinstance()` uses `__class__` for the check.

**Test:** `test_proxy_class_spoofing` in `test_proxy.py`.

---

## EC-8: Warm Jupyter kernel double-patching

**Problem:** In a Jupyter notebook, if you re-run the cell that calls `activate()`, the patching code runs again.  Without the idempotency guard, you'd double-wrap `pd.read_csv` and get a proxy of a proxy.

**Fix:** `activate()` checks the `_activated` flag before applying any patches.  The flag + lock together make it idempotent.

**Not yet tested** — requires a Jupyter fixture.  Manual verification: call `activate()` twice, verify `pd.read_csv` is only wrapped once by checking `_patches` has one entry.

---

## EC-9: `object.__getattribute__` vs `self._df` inside the proxy

**Problem:** Accessing `self._df` inside a method defined on `DataFrameProxy` would trigger `__getattr__("_df")`, which would then try to find `_df` on the underlying DataFrame — causing attribute errors or infinite recursion.

**Fix:** Use `object.__getattribute__(self, "_df")` to bypass the proxy's own `__getattr__` and access the slot directly.  All internal attribute access inside `DataFrameProxy` must use this pattern.

---

## EC-10: `pd.util.hash_pandas_object` returns uint64 — sum can overflow

**Problem:** Summing 1M uint64 row hashes can exceed 64-bit range.

**Fix:** Mask the sum to 64 bits with `& 0xFFFF_FFFF_FFFF_FFFF` before packing.  Then SHA-256 the packed bytes.  SHA-256 collision resistance is maintained regardless.

---

## EC-11: Python's built-in `hash()` is process-non-deterministic

**Problem:** `PYTHONHASHSEED` is randomised per process by default (Python 3.3+).  `hash(df)` produces a different value in every new process.

**Fix:** Never use `hash()`.  Use `pd.util.hash_pandas_object` + SHA-256 only.

---

## EC-12: `pickle.dumps(proxy)` silently corrupts data

**Problem:** Pickling a `DataFrameProxy` by default would pickle the wrapper object, not the underlying DataFrame.  When unpickled, the result may behave unexpectedly.

**Fix:** Override `__reduce__` to raise `TypeError` with a clear message directing the user to `proxy.unwrap()` before pickling.

**Test:** `test_pickle_blocked` in `test_proxy.py`.

---

## EC-13: sklearn `clone()` breaks on EstimatorProxy

**Problem:** `sklearn.base.clone(estimator)` inspects `estimator.__init__` parameters and calls the constructor with them.  If `estimator` is an `EstimatorProxy`, `clone()` would try to construct an `EstimatorProxy` with the sklearn params, not the original estimator class.

**Status:** Not fixed in v1.  Workaround: call `clone(proxy.unwrap())` and re-wrap.  Full fix requires spoofing `__init__` signature — deferred to v2.

---

## EC-14: `read_csv` output hash is computed after the record is created

**Problem:** In `_wrap_pd_reader`, we create the logger record before we have the proxy (and therefore the output hash).  The record is created with `output_hash=None` and then needs to be updated.

**Fix:** We use `dataclasses.replace()` to create a corrected copy of the record with the real output hash, and re-add it to the graph.  In v2, the record creation and hashing should be atomic.  This is a known limitation of v1.

---

## EC-15: Stack frame walking finds wrong caller

**Problem:** `inspect.stack()` sees our own proxy frames before user frames.  We need to skip provtrack's own files to find the actual line in the user's pipeline.

**Fix:** `_caller_frame()` in `logger.py` walks the stack and skips any frame whose filename ends in a provtrack module name.  The first non-provtrack, non-importlib frame is the user's code.
