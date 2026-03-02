#!/usr/bin/env python3
"""SPEAR-native minimal coding agent with platform-agnostic execution and web search."""

import argparse
import builtins
import json
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import uuid4

from rdflib import Graph, Namespace, RDF

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent
for path in (BASE_DIR, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.conversion.bpmn2rdf import BPMNToRDFConverter
from src.core import RDFProcessEngine

from handlers import build_handlers, build_build_handlers, build_autonomous_handlers
from handlers.common import (
    REPORT_FILE,
    APP_FILE,
    BUGGY_APP_SOURCE,
    BUGGY_TEST_SOURCE,
    TARGET_DIR,
    PythonTestTool,
    WebSearchTool,
)
from handlers.session_history import add_run, get_history
from handlers.run_report import AG as REPORT_AG
from handlers.run_report import (
    load_latest_report,
    load_report_by_run_id,
    load_report_graph,
    save_report,
)
from handlers.llm_provenance import get_interactions
from handlers.explanation_engine import (
    explain_last_run,
    explain_failure,
    generate_why_explanation,
    generate_what_if_scaffold,
    generate_reflection,
    llm_generate_explanation,
)
from handlers.nl_parser import parse_intent, execute_intent, format_help
from handlers.scratchpad import (
    read_notes,
    write_note,
    get_memory_summary,
    search_notes,
)
from handlers.subagent import decompose_task, dispatch_subagents

PROCESS_DIR = BASE_DIR / "processes"
ENGINE_GRAPH_PATH = BASE_DIR / "engine_graph.ttl"
MEMORY_GRAPH_PATH = BASE_DIR / "memory_graph.ttl"
TARGET_TEST_FILE = TARGET_DIR / "test_app.py"
DEFAULT_SOLVE_TASK = "Fix the failing tests in target_project/app.py"
PROCESS_FILES = {
    "solve": ["agent_fix_loop.bpmn"],
    "build": ["agent_build.bpmn"],
    "auto": ["autonomous_agent.bpmn"],
}
DEFAULT_AUTO_TASK = "fix this"
DEFAULT_APPROVAL_MODE = "prompt"

BPMN_NS = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
CAMUNDA_NS = Namespace("http://camunda.org/schema/1.0/bpmn#")


def load_graph(path: Path) -> Graph:
    graph = Graph()
    if path.exists():
        graph.parse(path, format="turtle")
    return graph


def merge_bpmn_definitions(graph: Graph, process_files: List[str]) -> None:
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
    for filename in process_files:
        if not filename.endswith(".bpmn"):
            continue
        file_path = PROCESS_DIR / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Process file not found: {file_path}")
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


def _load_report_for_run(run_id: str) -> dict:
    report = load_report_by_run_id(run_id)
    if report:
        return report
    return _load_report()


def _save_report(data: dict) -> None:
    report_uri = save_report(data)
    REPORT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _print_results(report: dict, instance_uri: str, instance_status: str) -> None:
    print("Process instance:", instance_uri)
    print("Instance status:", instance_status)
    if report.get("run_id"):
        print("Run ID:", report.get("run_id"))
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


def _get_report_count() -> int:
    graph = load_report_graph()
    return sum(1 for _ in graph.subjects(RDF.type, REPORT_AG.RunReport))


def _print_history() -> None:
    for entry in get_history():
        status = "OK" if entry.get("success") else "FAIL"
        run_suffix = f" ({entry['run_id']})" if entry.get("run_id") else ""
        print(
            f"[{status}] [{entry['timestamp']}] {entry['command']}{run_suffix}: {entry['task'][:50]}"
        )


def _print_interactions() -> None:
    for interaction in get_interactions():
        print(f"\n=== Interaction: {interaction['uri']} ===")
        print(f"Timestamp: {interaction['timestamp']}")
        if interaction.get("run_id"):
            print(f"Run ID: {interaction['run_id']}")
        print(f"Model: {interaction['model']}")
        print(f"Success: {interaction.get('success', 'N/A')}")
        print("\n--- Prompt ---")
        print(interaction.get("prompt", "")[:500])
        print("\n--- Response ---")
        print(interaction.get("response", "")[:500])


def _reset_target_project() -> None:
    APP_FILE.write_text(BUGGY_APP_SOURCE, encoding="utf-8")
    TARGET_TEST_FILE.write_text(BUGGY_TEST_SOURCE, encoding="utf-8")


def _run_target_tests() -> int:
    result = PythonTestTool.run_tests(TARGET_DIR)
    print(result["output"])
    return 0 if result["exit_code"] == "0" else 1


def _cat_target_files() -> int:
    files = [APP_FILE, TARGET_TEST_FILE]
    for file_path in files:
        print(f"\n=== {file_path.name} ===")
        if not file_path.exists():
            print("(missing)")
            continue
        print(file_path.read_text(encoding="utf-8"))
    return 0


def _create_run_id(mode: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{mode}-{stamp}-{uuid4().hex[:8]}"


def run_solve_mode(task: str, reset_target: bool) -> int:
    run_id = _create_run_id("solve")
    report_count_before = _get_report_count()
    engine_graph = load_graph(ENGINE_GRAPH_PATH)
    memory_graph = load_graph(MEMORY_GRAPH_PATH)
    merge_bpmn_definitions(engine_graph, PROCESS_FILES["solve"])

    engine = RDFProcessEngine(engine_graph, engine_graph)
    for topic, handler in build_handlers(task, reset_target, run_id).items():
        engine.register_topic_handler(topic, handler)

    process_uri = "http://example.org/bpmn/MinimalCodingAgentProcess"
    instance = engine.start_process_instance(
        process_uri,
        start_event_id="StartEvent_AgentFix",
    )

    engine_graph.serialize(ENGINE_GRAPH_PATH, format="turtle")
    memory_graph.serialize(MEMORY_GRAPH_PATH, format="turtle")

    report_count_after = _get_report_count()
    report = _load_report_for_run(run_id)
    if report_count_after <= report_count_before:
        print("Warning: no new report generated for this solve run.")
        report = {
            "run_id": run_id,
            "task": task,
            "success": False,
            "repair_exit_code": "-1",
            "repair_output": "No report generated for solve run.",
            "patch_applied": False,
        }
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
        run_id=run_id,
    )

    return 0 if success else 1


def run_build_mode(task: str) -> int:
    run_id = _create_run_id("build")
    report_count_before = _get_report_count()
    engine_graph = load_graph(ENGINE_GRAPH_PATH)
    memory_graph = load_graph(MEMORY_GRAPH_PATH)
    merge_bpmn_definitions(engine_graph, PROCESS_FILES["build"])

    engine = RDFProcessEngine(engine_graph, engine_graph)
    for topic, handler in build_build_handlers(task, run_id).items():
        engine.register_topic_handler(topic, handler)

    process_uri = "http://example.org/bpmn/MinimalCodingAgentBuildProcess"
    instance = engine.start_process_instance(
        process_uri,
        start_event_id="StartEvent_AgentBuild",
    )

    engine_graph.serialize(ENGINE_GRAPH_PATH, format="turtle")
    memory_graph.serialize(MEMORY_GRAPH_PATH, format="turtle")

    report_count_after = _get_report_count()
    report = _load_report_for_run(run_id)
    if report_count_after <= report_count_before:
        print("Warning: no new report generated for this build run.")
        report = {
            "run_id": run_id,
            "task": task,
            "build_success": False,
            "build_exit_code": "-1",
            "build_output": "No report generated for build run.",
        }
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
        run_id=run_id,
    )

    return 0 if success else 1


def run_autonomous_mode(task: str) -> int:
    """Run autonomous agent that keeps trying until success or max iterations."""
    run_id = _create_run_id("auto")
    print(f"Starting Autonomous Mode: '{task}'")
    print("This agent will keep trying until it succeeds or hits max iterations.\n")

    engine_graph = load_graph(ENGINE_GRAPH_PATH)
    memory_graph = load_graph(MEMORY_GRAPH_PATH)
    merge_bpmn_definitions(engine_graph, PROCESS_FILES["auto"])

    engine = RDFProcessEngine(engine_graph, engine_graph)
    for topic, handler in build_autonomous_handlers(task, run_id).items():
        engine.register_topic_handler(topic, handler)

    process_uri = "http://example.org/bpmn/AutonomousAgentProcess"
    instance = engine.start_process_instance(
        process_uri,
        start_event_id="StartEvent_Autonomous",
    )

    engine_graph.serialize(ENGINE_GRAPH_PATH, format="turtle")
    memory_graph.serialize(MEMORY_GRAPH_PATH, format="turtle")

    print("\n" + "=" * 50)
    print("AUTONOMOUS AGENT FINISHED")
    print("=" * 50)

    test_result = PythonTestTool.run_tests(TARGET_DIR)
    success = test_result["exit_code"] == "0"
    add_run(
        "auto",
        task,
        success,
        {
            "exit_code": test_result["exit_code"],
            "output": test_result["output"][:500],
        },
        run_id=run_id,
    )
    return 0 if success else 1


def run_interactive_mode() -> int:
    print("=" * 60)
    print("SPEAR Minimal Coding Agent - Interactive Mode")
    print("Type naturally - the agent will map input to commands.")
    print("=" * 60)
    print(format_help())

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Parse intent from natural language
        intent_data = parse_intent(user_input)

        # Execute the intent
        success, cmd = execute_intent(intent_data, None)

        if not success:
            print(cmd)
            continue

        if cmd == "help":
            print(format_help())
            continue

        if cmd == "quit":
            print("Goodbye!")
            break

        try:
            parsed = parse_args(shlex.split(cmd))
        except SystemExit:
            print(f"Invalid command generated from input: {cmd}")
            continue

        exit_code = execute_args(parsed)
        if exit_code != 0:
            print(f"Command failed with exit code {exit_code}")

    return 0


def execute_args(args: argparse.Namespace) -> int:
    if args.command == "search":
        return print_search_results(args.query, args.max_results)
    if args.command == "solve":
        solve_task = args.task or (" ".join(args.task_text).strip() if args.task_text else "")
        solve_task = solve_task or DEFAULT_SOLVE_TASK
        return run_solve_mode(solve_task, args.reset_target)
    if args.command == "build":
        return run_build_mode(" ".join(args.task).strip())
    if args.command == "auto":
        task = " ".join(args.task).strip() if args.task else DEFAULT_AUTO_TASK
        return run_autonomous_mode(task or DEFAULT_AUTO_TASK)
    if args.command == "reset":
        _reset_target_project()
        print("Target project reset to known buggy state.")
        return 0
    if args.command == "tests":
        return _run_target_tests()
    if args.command == "cat":
        return _cat_target_files()
    if args.command == "history":
        _print_history()
        return 0
    if args.command == "interactions":
        _print_interactions()
        return 0
    if args.command == "explain":
        if args.query:
            result = llm_generate_explanation(args.query)
            print(result)
        elif args.type == "last":
            print(explain_last_run(run_id=args.run_id))
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
            content = " ".join(args.content).strip() if args.content else ""
            if content:
                uri = write_note(content, note_type="note")
                print(f"Written: {uri}")
            else:
                print("Usage: scratch write <content>")
        elif args.action == "search":
            query = " ".join(args.content).strip() if args.content else ""
            if query:
                notes = search_notes(query)
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
        from handlers.approval_audit import log_approval_event

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
            tool_args = {}
            if args.args:
                try:
                    tool_args = json.loads(args.args)
                except:
                    print(f"Invalid JSON: {args.args}")
                    return 1
            if not isinstance(tool_args, dict):
                print("Tool arguments must be a JSON object.")
                return 1

            approval_mode = (
                args.approval_mode
                or os.getenv("SPEAR_APPROVAL_MODE", DEFAULT_APPROVAL_MODE)
            ).strip().lower()
            if approval_mode not in {"prompt", "auto", "deny"}:
                approval_mode = DEFAULT_APPROVAL_MODE
            approval_user = (
                args.approval_user or os.getenv("SPEAR_APPROVAL_USER", "")
            ).strip()
            tool_args.setdefault("_approval_mode", approval_mode)
            if approval_user:
                tool_args.setdefault("approval_user", approval_user)

            result = call_tool(args.tool, tool_args)

            if isinstance(result, dict) and result.get("approval_required"):
                if approval_mode == "auto":
                    tool_args["approved"] = True
                    tool_args["_approval_mode"] = "auto"
                    result = call_tool(args.tool, tool_args)
                elif approval_mode == "prompt":
                    if sys.stdin is not None and sys.stdin.isatty():
                        print(
                            "Approval required:",
                            result.get("error", "Risky action blocked"),
                        )
                        reply = builtins.input("Approve this action? [y/N]: ").strip().lower()
                        if reply in {"y", "yes"}:
                            tool_args["approved"] = True
                            tool_args["_approval_mode"] = "prompt"
                            result = call_tool(args.tool, tool_args)
                        else:
                            log_approval_event(
                                action=str(result.get("action", args.tool)),
                                decision="denied",
                                risk_level=str(result.get("risk_level", "unknown")),
                                rationale=str(result.get("rationale", "User denied prompt")),
                                mode="prompt",
                                tool_name=args.tool,
                                actor=approval_user,
                                policy_min_risk=str(
                                    (
                                        result.get("details", {})
                                        if isinstance(result.get("details"), dict)
                                        else {}
                                    ).get("policy_min_risk", "")
                                ),
                                details=result.get("details")
                                if isinstance(result.get("details"), dict)
                                else {},
                            )
                            result = {
                                "success": False,
                                "error": "Action denied by user.",
                            }
                    else:
                        log_approval_event(
                            action=str(result.get("action", args.tool)),
                            decision="denied",
                            risk_level=str(result.get("risk_level", "unknown")),
                            rationale="Approval required but stdin is not interactive.",
                            mode="prompt_non_interactive",
                            tool_name=args.tool,
                            actor=approval_user,
                            policy_min_risk=str(
                                (
                                    result.get("details", {})
                                    if isinstance(result.get("details"), dict)
                                    else {}
                                ).get("policy_min_risk", "")
                            ),
                            details=result.get("details")
                            if isinstance(result.get("details"), dict)
                            else {},
                        )
                        result = {
                            "success": False,
                            "error": (
                                "Approval required but stdin is not interactive. "
                                "Use --approval-mode auto/deny or include "
                                "'approved': true in tool args."
                            ),
                        }
                else:
                    log_approval_event(
                        action=str(result.get("action", args.tool)),
                        decision="denied",
                        risk_level=str(result.get("risk_level", "unknown")),
                        rationale="Action denied by approval policy (--approval-mode deny).",
                        mode="deny",
                        tool_name=args.tool,
                        actor=approval_user,
                        policy_min_risk=str(
                            (
                                result.get("details", {})
                                if isinstance(result.get("details"), dict)
                                else {}
                            ).get("policy_min_risk", "")
                        ),
                        details=result.get("details")
                        if isinstance(result.get("details"), dict)
                        else {},
                    )
                    result = {
                        "success": False,
                        "error": "Action denied by approval policy (--approval-mode deny).",
                    }
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
        task = " ".join(args.task).strip()
        subtasks = decompose_task(task)
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


def main() -> int:
    args = parse_args()
    return execute_args(args)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
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
        "task_text",
        nargs="*",
        help="Task description (positional form)",
    )
    solve_cmd.add_argument(
        "--task",
        default=None,
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
        nargs="+",
        help="Task description for what to build",
    )

    auto_cmd = sub.add_parser("auto", help="Autonomous mode - keeps trying until done")
    auto_cmd.add_argument("task", nargs="*", help="Vague task description")

    sub.add_parser("reset", help="Reset target project to known buggy state")
    sub.add_parser("tests", help="Run tests in target project")
    sub.add_parser("cat", help="Show target project files")

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
    explain_cmd.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Explain a specific run id (applies to 'last')",
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
        "content",
        nargs="*",
        help="Content for write action or search query",
    )

    mcp_cmd = sub.add_parser("tools", help="MCP tool operations")
    mcp_cmd.add_argument("action", nargs="?", default="list", choices=["list", "call"])
    mcp_cmd.add_argument("tool", nargs="?", help="Tool name to call")
    mcp_cmd.add_argument("args", nargs="?", help="Tool arguments as JSON")
    mcp_cmd.add_argument(
        "--approval-mode",
        choices=["prompt", "auto", "deny"],
        default=DEFAULT_APPROVAL_MODE,
        help="How to handle approval-required tool calls (default: prompt).",
    )
    mcp_cmd.add_argument(
        "--approval-user",
        default="",
        help="Actor identifier for approval audit events.",
    )

    skill_cmd = sub.add_parser("skills", help="Skill import operations")
    skill_cmd.add_argument(
        "action", nargs="?", default="list", choices=["list", "import", "search"]
    )
    skill_cmd.add_argument(
        "target", nargs="?", help="File/directory to import or search query"
    )

    sub_parse = sub.add_parser("decompose", help="Decompose a task into subtasks")
    sub_parse.add_argument("task", nargs="+", help="Task to decompose")

    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
