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

from handlers import build_handlers, build_build_handlers
from handlers.common import REPORT_FILE, WebSearchTool
from handlers.session_history import add_run, get_history
from handlers.run_report import save_report, load_latest_report
from handlers.llm_provenance import get_interactions
from handlers.explanation_engine import (
    explain_last_run,
    explain_failure,
    generate_why_explanation,
    generate_what_if_scaffold,
    generate_reflection,
    llm_generate_explanation,
)
from handlers.scratchpad import (
    read_notes,
    write_note,
    get_memory_summary,
    search_notes,
    Scratchpad,
)
from handlers.subagent import decompose_task, dispatch_subagents

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
    report = load_latest_report()
    if not report and REPORT_FILE.exists():
        try:
            return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return report


def _save_report(data: dict) -> None:
    report_uri = save_report(data)
    REPORT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


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
            if isinstance(step, dict) and step.get("event") == "accepted_best_candidate"
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

    success = report.get("success", False)
    add_run(
        "solve",
        task,
        success,
        {
            "exit_code": report.get("repair_exit_code", "-1"),
            "output": report.get("repair_output", "")[:500],
        },
    )

    return 0 if success else 1


def run_build_mode(task: str) -> int:
    engine_graph = load_graph(ENGINE_GRAPH_PATH)
    memory_graph = load_graph(MEMORY_GRAPH_PATH)
    merge_bpmn_definitions(engine_graph)

    engine = RDFProcessEngine(engine_graph, engine_graph)
    for topic, handler in build_build_handlers(task).items():
        engine.register_topic_handler(topic, handler)

    process_uri = "http://example.org/bpmn/MinimalCodingAgentBuildProcess"
    instance = engine.start_process_instance(
        process_uri,
        start_event_id="StartEvent_AgentBuild",
    )

    engine_graph.serialize(ENGINE_GRAPH_PATH, format="turtle")
    memory_graph.serialize(MEMORY_GRAPH_PATH, format="turtle")

    report = _load_report()
    _print_results(report, str(instance.instance_uri), instance.status)

    success = report.get("build_success", False)
    add_run(
        "build",
        task,
        success,
        {
            "exit_code": report.get("build_exit_code", "-1"),
            "output": report.get("build_output", "")[:500],
        },
    )

    return 0 if success else 1


def run_interactive_mode() -> int:
    print("=" * 50)
    print("SPEAR Minimal Coding Agent - Interactive Mode")
    print("=" * 50)
    print("Commands:")
    print("  build <task>  - Build new code from scratch")
    print("  solve <task> - Fix bugs in target_project")
    print("  reset         - Reset target to buggy state")
    print("  tests         - Run tests in target_project")
    print("  cat           - Show target app.py")
    print("  history       - Show session history")
    print("  quit/exit     - Exit interactive mode")
    print("=" * 50)
    print()

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not user_input:
            continue

        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit"):
            print("Goodbye!")
            break

        if cmd == "history":
            for entry in get_history():
                status = "OK" if entry.get("success") else "FAIL"
                print(
                    f"[{status}] [{entry['timestamp']}] {entry['command']}: {entry['task'][:50]}"
                )
            continue

        if cmd == "reset":
            from handlers.common import BUGGY_APP_SOURCE, APP_FILE, TARGET_DIR

            APP_FILE.write_text(BUGGY_APP_SOURCE, encoding="utf-8")
            (TARGET_DIR / "test_app.py").write_text(
                '''"""Tests for minimal coding agent target project."""

import pytest
from app import running_average


def test_running_average_basic():
    assert running_average(10, 2) == 5


def test_running_average_zero_count():
    with pytest.raises(ValueError):
        running_average(10, 0)


def test_running_average_negative_count():
    with pytest.raises(ValueError):
        running_average(10, -1)
''',
                encoding="utf-8",
            )
            print("Target reset to buggy state.")
            continue

        if cmd == "tests":
            from handlers.common import PythonTestTool, TARGET_DIR

            result = PythonTestTool.run_tests(TARGET_DIR)
            print(result["output"])
            continue

        if cmd == "cat":
            from handlers.common import APP_FILE

            print(APP_FILE.read_text(encoding="utf-8"))
            continue

        if cmd == "build":
            if not arg:
                print("Usage: build <task description>")
                continue
            print(f"Building: {arg}")
            add_run("build", arg, False, {})

            engine_graph = load_graph(ENGINE_GRAPH_PATH)
            memory_graph = load_graph(MEMORY_GRAPH_PATH)
            merge_bpmn_definitions(engine_graph)

            engine = RDFProcessEngine(engine_graph, engine_graph)
            for topic, handler in build_build_handlers(arg).items():
                engine.register_topic_handler(topic, handler)

            process_uri = "http://example.org/bpmn/MinimalCodingAgentBuildProcess"
            instance = engine.start_process_instance(
                process_uri,
                start_event_id="StartEvent_AgentBuild",
            )

            engine_graph.serialize(ENGINE_GRAPH_PATH, format="turtle")
            memory_graph.serialize(MEMORY_GRAPH_PATH, format="turtle")

            report = _load_report()
            if report.get("build_success"):
                print("Build SUCCESS!")
                print(f"Tests: {report.get('build_exit_code', '0')} passed")
            else:
                print("Build FAILED")
                print(report.get("build_output", "")[:500])
            continue

        if cmd == "solve":
            if not arg:
                print("Usage: solve <task description>")
                continue
            print(f"Solving: {arg}")
            add_run("solve", arg, False, {})

            engine_graph = load_graph(ENGINE_GRAPH_PATH)
            memory_graph = load_graph(MEMORY_GRAPH_PATH)
            merge_bpmn_definitions(engine_graph)

            engine = RDFProcessEngine(engine_graph, engine_graph)
            for topic, handler in build_handlers(arg, False).items():
                engine.register_topic_handler(topic, handler)

            process_uri = "http://example.org/bpmn/MinimalCodingAgentProcess"
            instance = engine.start_process_instance(
                process_uri,
                start_event_id="StartEvent_AgentFix",
            )

            engine_graph.serialize(ENGINE_GRAPH_PATH, format="turtle")
            memory_graph.serialize(MEMORY_GRAPH_PATH, format="turtle")

            report = _load_report()
            if report.get("success"):
                print("Fix SUCCESS!")
                print(f"Tests: {report.get('repair_exit_code', '0')} passed")
            else:
                print("Fix FAILED")
                print(report.get("repair_output", "")[:500])
            continue

        print(f"Unknown command: {cmd}")
        print("Available: build, solve, reset, tests, cat, history, quit")

    return 0


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

    build_cmd = sub.add_parser("build", help="Build new code from scratch")
    build_cmd.add_argument(
        "task",
        help="Task description for what to build",
    )

    sub.add_parser("history", help="Show session history")

    sub.add_parser("interactions", help="Show LLM interactions")

    explain_cmd = sub.add_parser("explain", help="Generate explanations")
    explain_cmd.add_argument(
        "type",
        nargs="?",
        default="last",
        choices=["last", "why", "what-if", "reflect", "failure"],
        help="Type of explanation: last (default), why, what-if, reflect, failure",
    )
    explain_cmd.add_argument(
        "--query",
        type=str,
        help="Ask a specific question (uses LLM)",
    )

    sub.add_parser("interactive", help="Start interactive REPL mode")

    scratch_cmd = sub.add_parser("scratch", help="Scratchpad/memory operations")
    scratch_cmd.add_argument(
        "action",
        nargs="?",
        default="list",
        choices=["list", "write", "search", "summary"],
    )
    scratch_cmd.add_argument(
        "content", nargs="?", help="Content for write action or search query"
    )

    mcp_cmd = sub.add_parser("tools", help="MCP tool operations")
    mcp_cmd.add_argument("action", nargs="?", default="list", choices=["list", "call"])
    mcp_cmd.add_argument("tool", nargs="?", help="Tool name to call")
    mcp_cmd.add_argument("args", nargs="?", help="Tool arguments as JSON")

    skill_cmd = sub.add_parser("skills", help="Skill import operations")
    skill_cmd.add_argument(
        "action", nargs="?", default="list", choices=["list", "import", "search"]
    )
    skill_cmd.add_argument(
        "target", nargs="?", help="File/directory to import or search query"
    )

    sub_parse = sub.add_parser("decompose", help="Decompose a task into subtasks")
    sub_parse.add_argument("task", help="Task to decompose")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "search":
        return print_search_results(args.query, args.max_results)
    if args.command == "solve":
        return run_solve_mode(args.task, args.reset_target)
    if args.command == "build":
        return run_build_mode(args.task)
    if args.command == "history":
        for entry in get_history():
            status = "OK" if entry.get("success") else "FAIL"
            print(
                f"[{status}] [{entry['timestamp']}] {entry['command']}: {entry['task'][:50]}"
            )
        return 0
    if args.command == "interactions":
        for interaction in get_interactions():
            print(f"\n=== Interaction: {interaction['uri']} ===")
            print(f"Timestamp: {interaction['timestamp']}")
            print(f"Model: {interaction['model']}")
            print(f"Success: {interaction.get('success', 'N/A')}")
            print(f"\n--- Prompt ---")
            print(interaction.get("prompt", "")[:500])
            print(f"\n--- Response ---")
            print(interaction.get("response", "")[:500])
        return 0
    if args.command == "explain":
        if args.query:
            result = llm_generate_explanation(args.query)
            print(result)
        elif args.type == "last":
            print(explain_last_run())
        elif args.type == "why":
            print(generate_why_explanation())
        elif args.type == "what-if":
            print(generate_what_if_scaffold())
        elif args.type == "reflect":
            print(generate_reflection())
        elif args.type == "failure":
            print(explain_failure())
        return 0
    if args.command == "scratch":
        if args.action == "list":
            notes = read_notes(limit=20)
            for note in notes:
                print(f"[{note['note_type']}] {note['content'][:100]}")
                print(f"  Timestamp: {note['timestamp']}")
                print()
        elif args.action == "write":
            if args.content:
                uri = write_note(args.content, note_type="note")
                print(f"Written: {uri}")
            else:
                print("Usage: scratch write <content>")
        elif args.action == "search":
            if args.content:
                notes = search_notes(args.content)
                for note in notes:
                    print(f"[{note['note_type']}] {note['content'][:100]}")
            else:
                print("Usage: scratch search <query>")
        elif args.action == "summary":
            summary = get_memory_summary()
            print(f"Total notes: {summary['total_notes']}")
            print("By type:")
            for t, count in summary["by_type"].items():
                print(f"  - {t}: {count}")
        return 0
    if args.command == "tools":
        from handlers.builtin_tools import (
            register_all_tools,
            list_available_tools,
            call_tool,
        )

        register_all_tools()

        if args.action == "list":
            tools = list_available_tools()
            print("Available MCP tools:")
            for t in tools:
                print(f"  - {t['name']}: {t['description']}")
        elif args.action == "call":
            if not args.tool:
                print("Usage: tools call <tool_name> <args_json>")
                return 1
            import json

            tool_args = {}
            if args.args:
                try:
                    tool_args = json.loads(args.args)
                except:
                    print(f"Invalid JSON: {args.args}")
                    return 1
            result = call_tool(args.tool, tool_args)
            print(json.dumps(result, indent=2))
        return 0
    if args.command == "skills":
        from handlers.skill_import import (
            import_markdown_skill,
            import_directory_skills,
            get_skills,
            search_skills,
        )

        if args.action == "list":
            skills = get_skills()
            print(f"Loaded skills: {len(skills)}\n")
            for s in skills:
                print(f"- {s['title']}: {s['description'][:60]}...")
        elif args.action == "import":
            if not args.target:
                print("Usage: skills import <file_or_directory>")
                return 1
            if os.path.isdir(args.target):
                results = import_directory_skills(args.target)
                for r in results:
                    print(r)
            else:
                result = import_markdown_skill(args.target)
                print(result)
        elif args.action == "search":
            if not args.target:
                print("Usage: skills search <query>")
                return 1
            results = search_skills(args.target)
            print(f"Found {len(results)} skills:\n")
            for s in results:
                print(f"- {s['title']}")
                print(f"  {s['description'][:80]}...")
                if s["patterns"]:
                    print(f"  Patterns: {s['patterns'][:2]}")
                print()
        return 0
    if args.command == "decompose":
        subtasks = decompose_task(args.task)
        print(f"Decomposed task into {len(subtasks)} subtasks:\n")
        for i, st in enumerate(subtasks, 1):
            print(f"{i}. {st.get('task', 'unnamed')}")
            print(f"   Description: {st.get('description', 'N/A')}")
            deps = st.get("depends_on", [])
            if deps:
                print(f"   Depends on: {deps}")
            print()
        return 0
    if args.command == "interactive":
        return run_interactive_mode()
    return 1


if __name__ == "__main__":
    sys.exit(main())
