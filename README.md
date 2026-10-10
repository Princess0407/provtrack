# provtrack

[![PyPI version](https://img.shields.io/pypi/v/provtrack.svg?color=blue)](https://pypi.org/project/provtrack/)
[![Python](https://img.shields.io/pypi/pyversions/provtrack.svg)](https://pypi.org/project/provtrack/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/Princess0407/provtrack/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/Princess0407/provtrack/ci.yml?label=CI)](https://github.com/Princess0407/provtrack/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen.svg)](https://github.com/Princess0407/provtrack)
[![pandas](https://img.shields.io/badge/pandas-1.3%2B-informational)](https://pandas.pydata.org/)
[![sklearn](https://img.shields.io/badge/sklearn-0.24%2B-informational)](https://scikit-learn.org/)

Zero-instrumentation ML pipeline provenance tracking.

MLflow tracks your hyperparameters. It does not track what happened to your data between `pd.read_csv()` and `model.fit()`. That gap is where debugging takes hours. provtrack closes it.

Add one line to your script. Get a complete, cryptographically linked DAG of every operation that touched your data, from the raw file to the trained model.

---

## The problem

You trained a model six months ago. It worked. You retrain today and the AUC drops by 8 points. What changed?

You have git history for your code. You have MLflow for your hyperparameters. You have nothing for the data transformations that happened between the raw file and the model input. Did someone change a `dropna` to a `fillna`? Did a column filter threshold shift? Did a new preprocessing step appear that was never in any commit message?

provtrack answers these questions without any manual logging. Every intermediate DataFrame state is fingerprinted. Every operation is recorded with the line number it came from. You can diff two pipeline runs and see exactly where the data diverged.

---

## Install

```bash
pip install provtrack
```

Optional extras:

```bash
pip install provtrack[sklearn]    # sklearn EstimatorProxy
pip install provtrack[spark]      # PySpark DataFrame support
pip install provtrack[backends]   # SQLite, PostgreSQL, S3 storage
pip install provtrack[tui]        # terminal UI
pip install provtrack[all]        # everything
```

Requirements: Python 3.8+, pandas 1.3+, networkx 2.6+

---

## Quickstart

```python
import provtrack
provtrack.activate()

import pandas as pd

df = pd.read_csv("titanic.csv")
df = provtrack.wrap(df)

df = df.dropna(subset=["Age", "Embarked"])
df = df[df["Age"] > 18]
df = df.rename(columns={"Survived": "label"})

print(provtrack.lineage().summary())
```

```
Pipeline: 4 operations, 3 data-flow edges
Sequence: read_csv -> dropna -> filter -> rename

Operation breakdown:
  read_csv    1x   avg 0.0 ms
  dropna      1x   avg 3.7 ms
  filter      1x   avg 0.9 ms
  rename      1x   avg 0.8 ms
```

The graph as a Mermaid diagram:

```
flowchart LR
  A["read_csv\nline 6"] -->|"79fdb5c3"| B["dropna\nline 9"]
  B -->|"e3ac0ecc"| C["filter\nline 10"]
  C -->|"e2cf8720"| D["rename\nline 11"]
```

The hashes on the edges are SHA-256 fingerprints of the DataFrame state at that point. If your data changes between runs, the hash changes. That is how you know something upstream broke your pipeline.

---

## How it works

provtrack has four layers. Each does exactly one job.

```
Your code
    |
    v
Layer 4: activate.py
Patches pd.read_csv, pd.read_parquet, etc.
Returns DataFrameProxy instead of DataFrame
    |
    v
Layer 3: proxy.py
DataFrameProxy.__getattr__ intercepts every call
Calls the real method, re-wraps the result
Records (op_name, input_hash, output_hash, line)
    |
    v
Layer 2: hasher.py + logger.py
SHA-256 fingerprint of each DataFrame state
Immutable OperationRecord stored in thread-safe singleton
    |
    v
Layer 1: graph.py
NetworkX DiGraph. Nodes = operations.
Edges = data flows, linked by hash identity.
output_hash(A) == input_hash(B) => edge A->B
```

### Proxy

`DataFrameProxy` is a transparent wrapper around `pd.DataFrame`. It uses `__slots__` to prevent attribute shadowing, `__class__` spoofing so `isinstance(proxy, pd.DataFrame)` returns `True` for sklearn compatibility, and `object.__getattribute__` for all internal access to avoid recursion.

When you call `df.dropna()` on a proxy:

1. `__getattr__("dropna")` fires and returns a wrapper function
2. The wrapper hashes the current DataFrame state (input hash)
3. The real `dropna()` runs on the underlying frame
4. The result is hashed (output hash)
5. An `OperationRecord` is logged with op name, both hashes, and the source line number
6. The result is re-wrapped as a new `DataFrameProxy`

This means `df.dropna().reset_index().rename(columns={"a": "b"})` generates three records with correctly linked hashes, with zero changes to your code.

### Hashing

Every DataFrame state is fingerprinted with `pd.util.hash_pandas_object`, which produces stable per-row uint64 hashes across processes and Python versions. Row hashes are collapsed to a single SHA-256 digest.

Python's built-in `hash()` is not used anywhere. It is randomised per process by `PYTHONHASHSEED` and cannot be compared across runs.

For DataFrames over 100,000 rows, provtrack hashes a seeded reservoir sample to bound latency to approximately 25ms regardless of file size.

### Graph

The graph links nodes by hash identity: if operation A's output hash equals operation B's input hash, then A produced the data that B consumed, so there is an edge from A to B. This works across different scripts and sessions as long as the session JSON files are present.

Deduplication is applied at write time: if two calls produce the same `(op_name, input_hash, output_hash)` triple, only the first is kept.

---

## CLI

```bash
# Human-readable pipeline report
provtrack report --file session.json

# Export the lineage graph
provtrack export --file session.json --format mermaid
provtrack export --file session.json --format dot --output pipeline.dot
provtrack export --file session.json --format json
provtrack export --file session.json --format openlineage

# Query operations
provtrack query --file session.json --hash e3ac0ecc
provtrack query --file session.json --tag pandas
provtrack query --file session.json --op dropna

# Compare two pipeline runs
provtrack diff --a session_v1.json --b session_v2.json

# Validate the lineage graph
provtrack validate --file session.json

# Launch terminal UI
provtrack tui --file session.json
provtrack tui --a session_v1.json --b session_v2.json
```

---

## Terminal UI

Install with `pip install provtrack[tui]`, then run:

```bash
provtrack tui --file session.json
```

Four screens, keyboard navigable:

| Screen | Key | Description |
|---|---|---|
| DAG view | `1` | Interactive pipeline graph, select nodes with j/k |
| Operation detail | `Enter` | Full detail for the selected operation |
| Diff view | `2` | Side-by-side comparison of two pipeline runs |
| Hash inspector | `3` | Every operation that touched a specific data state |

The TUI uses a slate grey and charcoal black color palette. No bright colors. Runs entirely in the terminal.

---

## Storage backends

provtrack ships four storage backends selectable at activation time.

```python
# Default: in-process, cleared on deactivate
provtrack.activate(backend="memory")

# Persist across runs
provtrack.activate(backend="sqlite", db_path="lineage.db")

# Team-scale, queryable
provtrack.activate(backend="postgres")
# Reads PROVTRACK_POSTGRES_DSN from environment

# Object storage
provtrack.activate(backend="s3", bucket="my-lineage-bucket")
```

---

## Backends comparison

| Backend | Persists | Cross-process | Team-scale | Setup |
|---|---|---|---|---|
| memory | No | No | No | None |
| sqlite | Yes | No | No | File path |
| postgres | Yes | Yes | Yes | DSN env var |
| s3 | Yes | Yes | Yes | AWS credentials |

---

## Export formats

| Format | Use case |
|---|---|
| `json` | Session persistence, CLI queries, diff |
| `mermaid` | Renders in GitHub, Notion, Obsidian |
| `dot` | Graphviz, pipe through `dot -Tpng` for an image |
| `openlineage` | Industry standard, compatible with Airflow, Spark, dbt |

---

## API reference

```python
# Activation
provtrack.activate(
    backend="memory",       # memory | sqlite | postgres | s3
    patch_sklearn=True,
    patch_pandas_readers=True,
    verbose=False,
)
provtrack.deactivate()
provtrack.reset()           # clear all records, keep activation
provtrack.is_active()       # bool

# Wrapping
provtrack.wrap(df)          # pd.DataFrame -> DataFrameProxy
provtrack.wrap(estimator)   # sklearn estimator -> EstimatorProxy

# Querying
graph = provtrack.lineage()
records = provtrack.records()

# Graph methods
graph.summary()
graph.to_mermaid()
graph.to_dot()
graph.to_json()
graph.to_openlineage()
graph.nodes()
graph.roots()
graph.leaves()
graph.ancestors_of(op_id)
graph.descendants_of(op_id)
graph.path_between(src_op_id, dst_op_id)
graph.ops_by_name("dropna")
graph.ops_touching_data(hash)
graph.is_valid_dag()
```

---

## Performance

Overhead is bounded by the SHA-256 hash of the DataFrame after each operation.

| DataFrame size | Hash time | Proxy overhead per call |
|---|---|---|
| 1K rows x 10 cols | 0.3 ms | 0.01 ms |
| 10K rows x 10 cols | 2.1 ms | 0.01 ms |
| 100K rows x 10 cols | 25 ms | 0.01 ms |
| 1M+ rows | ~25 ms (sampled) | 0.01 ms |

For large DataFrames, provtrack samples 100,000 rows with a fixed seed before hashing. The sample is deterministic, so the same data always produces the same hash. The sampling threshold is configurable.

---

## Security

**Immutable records.** `OperationRecord` is a frozen dataclass. A record cannot be mutated after it is created.

**No raw data in logs.** Args and kwargs are stored as bounded repr strings, not raw objects. No user data leaks into the provenance record.

**No eval or exec.** The codebase has zero uses of `eval`, `exec`, or `__import__`. The CLI parses JSON with strict mode and validates file size before reading.

**Pickle blocked on proxies.** `DataFrameProxy.__reduce__` raises `TypeError`. Call `proxy.unwrap()` before pickling.

**Thread-safe logger.** All record mutations go through a `threading.Lock`. Safe for multi-threaded preprocessing pipelines.

**Reversible activation.** `provtrack.deactivate()` fully restores all original pandas callables. Calling `activate()` twice is safe.

---

## Comparison

| Tool | Approach | Tracks intermediate pandas ops | Zero instrumentation | Cross-run diff | OpenLineage export |
|---|---|---|---|---|---|
| MLflow | Explicit logging | No | No | No | No |
| DVC | File-level hashing | No | No | Yes | No |
| mlinspect | AST rewriting | Partial | No | No | No |
| Vamsa | Static analysis | No | No | No | No |
| DataLineagePy | Runtime proxy | Yes | No | No | No |
| yProv4ML | Explicit logging | No | No | No | Yes |
| **provtrack** | **Runtime proxy** | **Yes** | **Yes** | **Yes** | **Yes** |

---

## Project structure

```
provtrack/
├── provtrack/
│   ├── _version.py          version string, single source of truth
│   ├── __init__.py          public API
│   ├── activate.py          patches pandas I/O, public API entry point
│   ├── hasher.py            SHA-256 fingerprinting
│   ├── logger.py            immutable OperationRecord, thread-safe singleton
│   ├── graph.py             NetworkX DAG
│   ├── proxy.py             DataFrameProxy, EstimatorProxy
│   ├── cli.py               report/export/query/diff/validate/tui commands
│   ├── hashers/             pluggable hasher layer (v2)
│   ├── proxies/             pluggable proxy layer (v2)
│   ├── backends/            memory/sqlite/postgres/s3 (v2)
│   ├── graph/               builder/query/diff/replay (v2)
│   ├── exporters/           json/dot/mermaid/openlineage (v2)
│   └── tui/                 Textual terminal UI (v3)
├── tests/
│   ├── test_hasher.py       28 tests
│   ├── test_proxy.py        17 tests
│   └── test_graph.py        17 tests
├── .github/
│   ├── workflows/
│   │   ├── ci.yml           test matrix Python 3.8-3.12
│   │   └── publish.yml      PyPI publish on version tag
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
├── INTERNALS.md             every design decision documented
├── EDGE_CASES.md            15 documented edge cases with fixes
├── pyproject.toml
└── LICENSE
```

---

## Contributing

Read `INTERNALS.md` first. It explains every design decision and why it was made. `EDGE_CASES.md` covers 15 specific failure modes found and fixed during development.

```bash
git clone https://github.com/Princess0407/provtrack
cd provtrack
python -m venv venv && source venv/bin/activate
pip install -e ".[all]"
pytest tests/ -v
```

All 64 tests should pass. If you are adding a feature, add a test first. If you are fixing a bug, add it to `EDGE_CASES.md` with the fix and a test reference.

---

## Roadmap

**Foundation:** pandas DataFrameProxy, sklearn EstimatorProxy, NetworkX DAG, CLI, session JSON export, Mermaid/DOT/JSON export formats, 64 passing tests.

**Base version(released):** `sys.monitoring` (PEP 669, Python 3.12+) as the primary tracing layer with v1 proxy fallback for Python 3.8-3.11. Pluggable storage backends (memory, SQLite, PostgreSQL, S3). OpenLineage export format. PySpark and tensor proxies. Modular hasher and exporter architecture.

**v1.0 (released):** Textual terminal UI with four interactive screens. Slate/charcoal dark theme. Keyboard-navigable DAG view, operation detail, side-by-side diff, and hash inspector. PyPI packaging with trusted publishing via OIDC.

**v1.2(planned):** Cryptographic signatures on records for tamper detection. Team-scale graph database backend.

---

## License

Apache 2.0.[LICENSE](https://github.com/Princess0407/provtrack/blob/main/LICENSE).
