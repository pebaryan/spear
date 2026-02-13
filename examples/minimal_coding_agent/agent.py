#!/usr/bin/env python3
"""SPEAR-native minimal coding agent with platform-agnostic execution and web search."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

from rdflib import Graph, Namespace, RDF

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent
for path in (BASE_DIR, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.conversion.bpmn2rdf import BPMNToRDFConverter
from src.core import RDFProcessEngine

from handlers import build_handlers
from handlers.common import REPORT_FILE, WebSearchTool

PROCESS_DIR = BASE_DIR / "processes"
ENGINE_GRAPH_PATH = BASE_DIR / "engine_graph.ttl"
MEMORY_GRAPH_PATH = BASE_DIR / "memory_graph.ttl"

BPMN_NS = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
CAMUNDA_NS = Namespace("http://camunda.org/schema/1.0/bpmn#")


def load_graph(path: Path) -> Graph:
    graph = Graph()
    if path.exists():
        graph.parse(path, format="turtle")
    return graph


def merge_bpmn_definitions(graph: Graph) -> None:
    """Load BPMN files into graph and normalize for RDFProcessEngine."""
    graph.bind("bpmn", BPMN_NS, replace=True)
    graph.bind("camunda", CAMUNDA_NS, replace=True)

    bpmn_base = "http://example.org/bpmn/"
    to_remove = []
    for subject, predicate, obj in graph:
        if str(subject).startswith(bpmn_base):
            to_remove.append((subject, predicate, obj))
    for triple in to_remove:
        graph.remove(triple)

    converter = BPMNToRDFConverter()
    for filename in os.listdir(PROCESS_DIR):
        if not filename.endswith(".bpmn"):
            continue
        process_graph = converter.parse_bpmn_to_graph(str(PROCESS_DIR / filename))
        for triple in process_graph:
            graph.add(triple)

    for subject, _, topic in list(graph.triples((None, CAMUNDA_NS.topic, None))):
        graph.add((subject, BPMN_NS.topic, topic))

    type_map = {
        "startEvent": "StartEvent",
        "endEvent": "EndEvent",
        "serviceTask": "ServiceTask",
        "userTask": "UserTask",
        "exclusiveGateway": "ExclusiveGateway",
        "parallelGateway": "ParallelGateway",
    }
    for lower, upper in type_map.items():
        lower_uri = BPMN_NS[lower]
        upper_uri = BPMN_NS[upper]
        for subject, _, _ in list(graph.triples((None, RDF.type, lower_uri))):
            graph.remove((subject, RDF.type, lower_uri))
            graph.add((subject, RDF.type, upper_uri))


def print_search_results(query: str, max_results: int = 5) -> int:
    tool = WebSearchTool()
    results = tool.search(query, max_results=max_results)
    print(f"Query: {query}")
    if not results:
        print("No results returned.")
        return 0

    for idx, item in enumerate(results, start=1):
        print(f"{idx}. [{item.source}] {item.title}")
        print(f"   {item.url}")
        if item.snippet:
            print(f"   {item.snippet}")
    return 0


def _load_report() -> dict:
    if not REPORT_FILE.exists():
        return {}
    try:
        return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _print_results(report: dict, instance_uri: str, instance_status: str) -> None:
    print("Process instance:", instance_uri)
    print("Instance status:", instance_status)
    print("Task:", report.get("task"))
    print("Patch applied:", report.get("patch_applied"))
    print("Success:", report.get("success"))
    print("Report:", REPORT_FILE)

    query = report.get("query")
    if query:
        print("")
        print("Search query:", query)
    for idx, item in enumerate(report.get("search_results", []), start=1):
        title = item.get("title", "")
        url = item.get("url", "")
        print(f"{idx}. {title} ({url})")

    repair_steps = report.get("repair_steps", [])
    if isinstance(repair_steps, list) and repair_steps:
        accepted = [
            step
            for step in repair_steps
            if isinstance(step, dict)
            and step.get("event") == "accepted_best_candidate"
        ]
        print("")
        print("Repair steps tried:", len(repair_steps))
        if accepted:
            best = accepted[-1]
            print(
                "Accepted candidate:",
                f"{best.get('file')} - {best.get('description')}",
            )


def run_solve_mode(task: str, reset_target: bool) -> int:
    engine_graph = load_graph(ENGINE_GRAPH_PATH)
    memory_graph = load_graph(MEMORY_GRAPH_PATH)
    merge_bpmn_definitions(engine_graph)

    engine = RDFProcessEngine(engine_graph, engine_graph)
    for topic, handler in build_handlers(task, reset_target).items():
        engine.register_topic_handler(topic, handler)

    process_uri = "http://example.org/bpmn/MinimalCodingAgentProcess"
    instance = engine.start_process_instance(
        process_uri,
        start_event_id="StartEvent_AgentFix",
    )

    engine_graph.serialize(ENGINE_GRAPH_PATH, format="turtle")
    memory_graph.serialize(MEMORY_GRAPH_PATH, format="turtle")

    report = _load_report()
    _print_results(report, str(instance.instance_uri), instance.status)

    return 0 if report.get("success") else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SPEAR-native minimal coding agent",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    search_cmd = sub.add_parser("search", help="Run web search only")
    search_cmd.add_argument("query", help="Search query")
    search_cmd.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of search results",
    )

    solve_cmd = sub.add_parser("solve", help="Run coding agent loop via SPEAR")
    solve_cmd.add_argument(
        "--task",
        default="Fix the failing tests in target_project/app.py",
        help="Task description for the agent",
    )
    solve_cmd.add_argument(
        "--reset-target",
        action="store_true",
        help="Reset target_project to known buggy state before solving",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "search":
        return print_search_results(args.query, args.max_results)
    if args.command == "solve":
        return run_solve_mode(args.task, args.reset_target)
    return 1


if __name__ == "__main__":
    sys.exit(main())
