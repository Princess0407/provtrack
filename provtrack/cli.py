from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_MAX_FILE_BYTES = 50 * 1024 * 1024


def _safe_open(path_str: str, max_bytes: int = _MAX_FILE_BYTES) -> Dict[str, Any]:
    path = Path(path_str).resolve()
    if path.suffix.lower() != ".json":
        _die(f"Expected a .json file, got: {path.suffix}")
    if not path.is_file():
        _die(f"File not found: {path}")

    file_size = path.stat().st_size
    if file_size > max_bytes:
        _die(f"File too large ({file_size / 1e6:.1f} MB > {max_bytes / 1e6:.0f} MB limit). Use --max-size to raise the limit.")

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
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


def _load_graph_from_data(data: Dict[str, Any]):
    from provtrack.graph.builder import LineageGraph
    from provtrack.logger import OperationRecord

    nodes = data.get("nodes", [])
    if not isinstance(nodes, list):
        _die("Session JSON missing 'nodes' list.")

    records: List[OperationRecord] = []
    for node in nodes:
        try:
            rec = OperationRecord(
                id=node.get("id") or node.get("op_id"),
                op_name=node["op_name"],
                obj_type=node.get("obj_type", ""),
                input_hash=node.get("input_hash"),
                output_hash=node.get("output_hash", ""),
                args_repr=node.get("args_repr", ""),
                kwargs_repr=node.get("kwargs_repr", ""),
                source_file=node.get("source_file") or node.get("caller_file", ""),
                source_line=node.get("source_line") or node.get("caller_line", 0),
                caller_func=node.get("caller_func", ""),
                timestamp=node.get("timestamp"),
                duration_ms=node.get("duration_ms", 0.0),
                tags=tuple(node.get("tags", [])),
            )
            records.append(rec)
        except KeyError as exc:
            _die(f"Malformed node record — missing key: {exc}")

    return LineageGraph.from_records(records)


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
        file_name = node.get("source_file") or node.get("caller_file", "?")
        line_num = node.get("source_line") or node.get("caller_line", "?")
        caller = f"{os.path.basename(file_name)}:{line_num}"
        print(f"{i:<4}  {op:<20}  {obj:<20}  {dur:<12}  {caller}")

    print()
    print(f"Graph valid DAG: {graph.is_valid_dag()}")
    print(f"Total nodes: {graph.node_count}  |  Total edges: {graph.edge_count}")


def cmd_export(args: argparse.Namespace) -> None:
    data = _safe_open(args.file, max_bytes=args.max_size)
    fmt = args.format.lower()

    if fmt == "openlineage":
        from provtrack.exporters.openlineage import export_openlineage
        from provtrack.logger import OperationRecord

        nodes = data.get("nodes", [])
        records = [
            OperationRecord(
                id=n.get("id") or n.get("op_id"),
                op_name=n.get("op_name", ""),
                input_hash=n.get("input_hash"),
                output_hash=n.get("output_hash", ""),
                timestamp=n.get("timestamp"),
                tags=tuple(n.get("tags", [])),
            )
            for n in nodes
        ]
        output = json.dumps(export_openlineage(records), indent=2)
    else:
        graph = _load_graph_from_data(data)
        if fmt == "json":
            output = graph.to_json()
        elif fmt == "dot":
            output = graph.to_dot()
        elif fmt == "mermaid":
            output = graph.to_mermaid()
        else:
            _die(f"Unknown format: {fmt}. Choose json / dot / mermaid / openlineage.")

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
    from provtrack.graph.diff import diff_graphs

    data_a = _safe_open(args.a, max_bytes=args.max_size)
    data_b = _safe_open(args.b, max_bytes=args.max_size)

    graph_a = _load_graph_from_data(data_a)
    graph_b = _load_graph_from_data(data_b)

    diff = diff_graphs(graph_a, graph_b)

    print("=" * 50)
    print("  PROVTRACK SESSION DIFF")
    print("=" * 50)
    print(f"Session A: {args.a}  ({diff.nodes_a} ops, {diff.edges_a} edges)")
    print(f"Session B: {args.b}  ({diff.nodes_b} ops, {diff.edges_b} edges)")
    print()
    print(f"Shared ops   : {len(diff.shared_ops):>4}  {list(diff.shared_ops)}")
    print(f"Added in B   : {len(diff.added_ops):>4}  {list(diff.added_ops)}")
    print(f"Removed in B : {len(diff.removed_ops):>4}  {list(diff.removed_ops)}")
    print()
    print("Structural change: " + ("YES" if diff.has_structural_change else "NO — same operation set"))


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


def cmd_serve(args: argparse.Namespace) -> None:
    data = _safe_open(args.file, max_bytes=args.max_size)
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError as exc:
        _die(f"FastAPI or uvicorn not available: {exc}. Install with: pip install fastapi uvicorn")

    app = FastAPI(title="ProvTrack Graph Server")

    @app.get("/graph")
    def get_graph():
        return data

    uvicorn.run(app, host=args.host, port=args.port)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="provtrack",
        description="Zero-instrumentation ML pipeline provenance tracker.",
    )
    parser.add_argument("--version", action="version", version="provtrack 2.0.0")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_report = subparsers.add_parser("report", help="Human-readable summary of a saved session")
    p_report.add_argument("--file", "-f", required=True, help="Path to session JSON file")
    p_report.add_argument("--max-size", type=int, default=_MAX_FILE_BYTES, help="Max file size in bytes")
    p_report.set_defaults(func=cmd_report)

    p_export = subparsers.add_parser("export", help="Export lineage to JSON, DOT, Mermaid, or OpenLineage")
    p_export.add_argument("--file", "-f", required=True, help="Path to session JSON file")
    p_export.add_argument("--format", default="json", choices=["json", "dot", "mermaid", "openlineage"], help="Export format")
    p_export.add_argument("--output", "-o", default=None, help="Write output to file instead of stdout")
    p_export.add_argument("--max-size", type=int, default=_MAX_FILE_BYTES, help="Max file size in bytes")
    p_export.set_defaults(func=cmd_export)

    p_query = subparsers.add_parser("query", help="Query recorded operations")
    p_query.add_argument("--file", "-f", required=True, help="Path to session JSON file")
    p_query.add_argument("--op", default=None, help="Find operations by method name")
    p_query.add_argument("--hash", default=None, help="Find operations touching this data hash")
    p_query.add_argument("--tag", default=None, help="Find operations with this tag")
    p_query.add_argument("--max-size", type=int, default=_MAX_FILE_BYTES, help="Max file size in bytes")
    p_query.set_defaults(func=cmd_query)

    p_diff = subparsers.add_parser("diff", help="Compare two pipeline session graphs")
    p_diff.add_argument("--a", required=True, help="Session A JSON file")
    p_diff.add_argument("--b", required=True, help="Session B JSON file")
    p_diff.add_argument("--max-size", type=int, default=_MAX_FILE_BYTES, help="Max file size in bytes")
    p_diff.set_defaults(func=cmd_diff)

    p_validate = subparsers.add_parser("validate", help="Verify that a session graph is a valid DAG")
    p_validate.add_argument("--file", "-f", required=True, help="Path to session JSON file")
    p_validate.add_argument("--max-size", type=int, default=_MAX_FILE_BYTES, help="Max file size in bytes")
    p_validate.set_defaults(func=cmd_validate)

    p_serve = subparsers.add_parser("serve", help="Serve session graph via local FastAPI server")
    p_serve.add_argument("--file", "-f", required=True, help="Path to session JSON file")
    p_serve.add_argument("--port", "-p", type=int, default=8000, help="Port to run server on")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    p_serve.add_argument("--max-size", type=int, default=_MAX_FILE_BYTES, help="Max file size in bytes")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
