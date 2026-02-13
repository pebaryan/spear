#!/usr/bin/env python3
"""
Run a deterministic SPEAR conference demo scenario and query pack.

This script prepares local RDF data, executes two instances of a risk-routing
workflow, and runs SPARQL queries used in the conference narrative.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from rdflib import Graph

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.api.storage import StorageFacade


PROCESS_FILE = BASE_DIR / "processes" / "risk_routing_demo.bpmn"
QUERY_DIR = BASE_DIR / "queries"
DEFAULT_DATA_DIR = BASE_DIR / "run_data"
DEFAULT_OUTPUT_DIR = BASE_DIR / "expected_outputs"
GRAPH_FILES = ("definitions.ttl", "instances.ttl", "tasks.ttl", "audit.ttl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SPEAR conference demo")
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Directory for generated RDF files (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for run artifacts (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing data-dir before running demo",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max rows to print per SPARQL query",
    )
    return parser.parse_args()


def reset_data_dir(data_dir: Path) -> None:
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)


def load_graph_bundle(data_dir: Path) -> Graph:
    graph = Graph()
    for filename in GRAPH_FILES:
        filepath = data_dir / filename
        if filepath.exists():
            graph.parse(filepath, format="turtle")
    return graph


def read_query(query_path: Path) -> str:
    return query_path.read_text(encoding="utf-8")


def run_query(graph: Graph, query_name: str, query_text: str, limit: int) -> List[Tuple[str, ...]]:
    result = graph.query(query_text)
    var_names = [str(v) for v in result.vars]
    rows = [tuple(str(row[i]) for i in range(len(var_names))) for row in result]

    print(f"\n== {query_name} ({len(rows)} rows)")
    print("columns:", ", ".join(var_names))
    if not rows:
        print("(no rows)")
        return []

    for idx, row in enumerate(rows[:limit], start=1):
        print(f"{idx:02d}: " + " | ".join(row))
    if len(rows) > limit:
        print(f"... {len(rows) - limit} additional rows")
    return rows


def run_scenario(storage: StorageFacade) -> Dict[str, str]:
    bpmn_xml = PROCESS_FILE.read_text(encoding="utf-8")

    def calculate_tax_handler(instance_id, variables):
        updated = dict(variables)
        order_total = float(updated.get("orderTotal", 0))
        updated["taxAmount"] = round(order_total * 0.10, 2)
        updated["taxRate"] = 0.10
        updated["decision"] = "auto-approved-by-policy"
        updated["approvedBy"] = "risk-policy-v1"
        return updated

    storage.register_topic_handler("calculate_tax", calculate_tax_handler)

    process_id = storage.deploy_process(
        name="Risk Routing Demo",
        description="Conference scenario with deterministic branch behavior",
        bpmn_content=bpmn_xml,
    )

    high_instance = storage.create_instance(
        process_id=process_id,
        variables={"risk": "high", "customerId": "C-100", "orderTotal": 250.0},
    )["id"]

    low_instance = storage.create_instance(
        process_id=process_id,
        variables={"risk": "low", "customerId": "C-101", "orderTotal": 100.0},
    )["id"]

    high_data = storage.get_instance(high_instance)
    low_data = storage.get_instance(low_instance)
    tasks = storage.list_tasks()

    print("\n== Scenario Summary")
    print("process_id:", process_id)
    print("high_instance:", high_instance, "status=", high_data["status"])
    print("low_instance :", low_instance, "status=", low_data["status"])
    print("tasks_total  :", tasks["total"])

    # Demo sanity checks to avoid presenting broken state.
    if high_data["status"] != "RUNNING":
        raise RuntimeError("Expected high-risk instance to remain RUNNING at user task")
    if low_data["status"] != "COMPLETED":
        raise RuntimeError("Expected low-risk instance to auto-complete")
    if tasks["total"] < 1:
        raise RuntimeError("Expected at least one manual review task")

    return {
        "process_id": process_id,
        "high_instance_id": high_instance,
        "low_instance_id": low_instance,
        "high_status": high_data["status"],
        "low_status": low_data["status"],
    }


def write_run_artifacts(output_dir: Path, summary: Dict[str, str], query_rows: Dict[str, List[Tuple[str, ...]]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "latest_run_summary.json"
    query_path = output_dir / "latest_query_rows.json"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    query_path.write_text(json.dumps(query_rows, indent=2), encoding="utf-8")

    print("\nSaved artifacts:")
    print("-", summary_path)
    print("-", query_path)


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if args.reset:
        reset_data_dir(data_dir)
    else:
        data_dir.mkdir(parents=True, exist_ok=True)

    storage = StorageFacade(str(data_dir))

    try:
        summary = run_scenario(storage)
    except Exception as exc:
        print(f"Scenario execution failed: {exc}", file=sys.stderr)
        return 1

    merged_graph = load_graph_bundle(data_dir)
    query_rows: Dict[str, List[Tuple[str, ...]]] = {}

    query_files = [
        "trace_instances.sparql",
        "why_branch_taken.sparql",
        "find_waiting_tokens.sparql",
        "audit_summary.sparql",
    ]

    for query_file in query_files:
        query_name = query_file.replace(".sparql", "")
        query_text = read_query(QUERY_DIR / query_file)
        rows = run_query(merged_graph, query_name, query_text, args.limit)
        query_rows[query_name] = rows

    write_run_artifacts(output_dir, summary, query_rows)
    print("\nConference demo run completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
