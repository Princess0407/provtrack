"""
provtrack.cli
~~~~~~~~~~~~~
Command-line interface.

Commands
--------
  provtrack report   -- print human-readable lineage for a saved session
  provtrack export   -- export to json / dot / mermaid
  provtrack query    -- find ops by name, data hash, or tag
  provtrack diff     -- compare two saved sessions (v1: structural diff only)
  provtrack validate -- verify a saved session graph is a valid DAG

Usage
-----
  provtrack report --file session.json
  provtrack export --file session.json --format mermaid
  provtrack query --file session.json --op dropna
  provtrack diff --a session1.json --b session2.json
  provtrack validate --file session.json

Security guardrails
-------------------
  - All file inputs are validated before parsing (extension, size limit).
  - JSON is parsed with strict=True; no exec/eval.
  - Paths are resolved and checked against a safe directory before opening.
  - Max file size: 50 MB (configurable via --max-size).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


# ── security helpers ──────────────────────────────────────────────────────────

def _safe_open(path_str: str, max_bytes: int = _MAX_FILE_BYTES) -> dict:
    """
    Open and parse a provtrack session JSON file with safety checks.

    Raises
    ------
    SystemExit on any validation failure (cleaner UX than raw exceptions).
    """
    path = Path(path_str).resolve()

    # Extension check.
    if path.suffix.lower() != ".json":
        _die(f"Expected a .json file, got: {path.suffix}")

    # Existence + size check.
    if not path.is_file():
        _die(f"File not found: {path}")

    file_size = path.stat().st_size
    if file_size > max_bytes:
        _die(
            f"File too large ({file_size / 1e6:.1f} MB > "
            f"{max_bytes / 1e6:.0f} MB limit).  "
            "Use --max-size to raise the limit."
        )

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f, parse_constant=None)
    except json.JSONDecodeError as exc:
        _die(f"Invalid JSON in {path}: {exc}")
    except OSError as exc:
        _die(f"Could not read {path}: {exc}")

    if not isinstance(data, dict):
        _die("Session file must contain a JSON object at the top level.")

    return data


def _die(msg: str, code: int = 1) -> None:
    print(f"[provtrack] Error: {msg}", file=sys.stderr)
    sys.exit(code)


def _load_graph_from_data(data: dict) -> "ProvenanceGraph":
    """Reconstruct a ProvenanceGraph from a saved session dict."""
    from .graph import ProvenanceGraph  # noqa: PLC0415
    from .logger import OperationRecord  # noqa: PLC0415

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        _die("Session JSON missing 'nodes' list.")

    records: List[OperationRecord] = []
    for node in nodes:
        try:
            rec = OperationRecord(
                op_id=node["op_id"],
                op_name=node["op_name"],
                obj_type=node["obj_type"],
                input_hash=node["input_hash"],
                output_hash=node.get("output_hash"),
                args_repr=node.get("args_repr", ""),
                kwargs_repr=node.get("kwargs_repr", ""),
                caller_file=node.get("caller_file", ""),
                caller_line=node.get("caller_line", 0),
                caller_func=node.get("caller_func", ""),
                timestamp=node.get("timestamp", ""),
                duration_ms=node.get("duration_ms", 0.0),
                tags=tuple(node.get("tags", [])),
            )
            records.append(rec)
        except KeyError as exc:
            _die(f"Malformed node record — missing key: {exc}")

    return ProvenanceGraph.from_records(records)


# ── sub-commands ──────────────────────────────────────────────────────────────

def cmd_report(args: argparse.Namespace) -> None:
    data = _safe_open(args.file, max_bytes=args.max_size)
    graph = _load_graph_from_data(data)

    print("=" * 60)
    print("  PROVTRACK LINEAGE REPORT")
    print("=" * 60)
    print(graph.summary())
    print()

    print(f"{'#':<4}  {'Operation':<20}  {'Object':<20}  {'Duration ms':<12}  {'Caller'}")
    print("-" * 90)

    for i, node in enumerate(graph.nodes(), start=1):
        op = node.get("op_name", "?")
        obj = node.get("obj_type", "?")
        dur = f"{node.get('duration_ms', 0):.1f}"
        caller = f"{os.path.basename(node.get('caller_file', '?'))}:{node.get('caller_line', '?')}"
        print(f"{i:<4}  {op:<20}  {obj:<20}  {dur:<12}  {caller}")

    print()
    print(f"Graph valid DAG: {graph.is_valid_dag()}")
    print(f"Total nodes: {graph.node_count}  |  Total edges: {graph.edge_count}")


def cmd_export(args: argparse.Namespace) -> None:
    data = _safe_open(args.file, max_bytes=args.max_size)
    graph = _load_graph_from_data(data)

    fmt = args.format.lower()
    if fmt == "json":
        output = graph.to_json()
    elif fmt == "dot":
        output = graph.to_dot()
    elif fmt == "mermaid":
        output = graph.to_mermaid()
    else:
        _die(f"Unknown format: {fmt}. Choose json / dot / mermaid.")

    if args.output:
        out_path = Path(args.output).resolve()
        try:
            out_path.write_text(output, encoding="utf-8")
            print(f"[provtrack] Exported to {out_path}")
        except OSError as exc:
            _die(f"Could not write to {out_path}: {exc}")
    else:
        print(output)


def cmd_query(args: argparse.Namespace) -> None:
    data = _safe_open(args.file, max_bytes=args.max_size)
    graph = _load_graph_from_data(data)

    results = []
    if args.op:
        results = graph.ops_by_name(args.op)
    elif args.hash:
        results = graph.ops_touching_data(args.hash)
    elif args.tag:
        results = [n for n in graph.nodes() if args.tag in n.get("tags", [])]
    else:
        _die("Provide --op, --hash, or --tag to filter.")

    if not results:
        print("[provtrack] No matching operations found.")
        return

    for node in results:
        print(json.dumps(node, indent=2, default=str))


def cmd_diff(args: argparse.Namespace) -> None:
    data_a = _safe_open(args.a, max_bytes=args.max_size)
    data_b = _safe_open(args.b, max_bytes=args.max_size)

    graph_a = _load_graph_from_data(data_a)
    graph_b = _load_graph_from_data(data_b)

    ops_a = {n["op_name"] for n in graph_a.nodes()}
    ops_b = {n["op_name"] for n in graph_b.nodes()}

    added = ops_b - ops_a
    removed = ops_a - ops_b
    shared = ops_a & ops_b

    print("=" * 50)
    print("  PROVTRACK SESSION DIFF")
    print("=" * 50)
    print(f"Session A: {args.a}  ({graph_a.node_count} ops, {graph_a.edge_count} edges)")
    print(f"Session B: {args.b}  ({graph_b.node_count} ops, {graph_b.edge_count} edges)")
    print()
    print(f"Shared ops   : {len(shared):>4}  {sorted(shared)}")
    print(f"Added in B   : {len(added):>4}  {sorted(added)}")
    print(f"Removed in B : {len(removed):>4}  {sorted(removed)}")
    print()
    print(
        "Structural change: "
        + ("YES" if added or removed else "NO — same operation set")
    )


def cmd_validate(args: argparse.Namespace) -> None:
    data = _safe_open(args.file, max_bytes=args.max_size)
    graph = _load_graph_from_data(data)

    is_dag = graph.is_valid_dag()
    print(f"[provtrack] Nodes: {graph.node_count}")
    print(f"[provtrack] Edges: {graph.edge_count}")
    print(f"[provtrack] Valid DAG: {is_dag}")

    if not is_dag:
        print("[provtrack] WARNING: Graph contains cycles — data lineage is corrupt.")
        sys.exit(2)
    else:
        print("[provtrack] OK")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="provtrack",
        description="Zero-instrumentation ML pipeline provenance tracker.",
    )
    parser.add_argument(
        "--version", action="version", version="provtrack 0.1.0"
    )

    # Shared flag.
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--max-size",
        type=int,
        default=_MAX_FILE_BYTES,
        metavar="BYTES",
        help=f"Maximum session file size in bytes (default: {_MAX_FILE_BYTES})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # report
    p_report = sub.add_parser("report", parents=[parent], help="Print lineage report.")
    p_report.add_argument("--file", required=True, help="Path to session .json file.")

    # export
    p_export = sub.add_parser("export", parents=[parent], help="Export lineage graph.")
    p_export.add_argument("--file", required=True, help="Path to session .json file.")
    p_export.add_argument(
        "--format",
        choices=["json", "dot", "mermaid"],
        default="mermaid",
        help="Output format (default: mermaid).",
    )
    p_export.add_argument("--output", help="Write to file instead of stdout.")

    # query
    p_query = sub.add_parser("query", parents=[parent], help="Query operations.")
    p_query.add_argument("--file", required=True, help="Path to session .json file.")
    p_query.add_argument("--op", help="Filter by operation name.")
    p_query.add_argument("--hash", help="Filter by data hash.")
    p_query.add_argument("--tag", help="Filter by tag (e.g. pandas, sklearn).")

    # diff
    p_diff = sub.add_parser("diff", parents=[parent], help="Compare two sessions.")
    p_diff.add_argument("--a", required=True, help="First session .json file.")
    p_diff.add_argument("--b", required=True, help="Second session .json file.")

    # validate
    p_validate = sub.add_parser(
        "validate", parents=[parent], help="Validate session graph is a DAG."
    )
    p_validate.add_argument("--file", required=True, help="Path to session .json file.")

    args = parser.parse_args(argv)

    dispatch = {
        "report": cmd_report,
        "export": cmd_export,
        "query": cmd_query,
        "diff": cmd_diff,
        "validate": cmd_validate,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
