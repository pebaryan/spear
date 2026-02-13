import os
import sys
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Optional
from rdflib import Graph, Literal, Namespace, RDF, URIRef

BASE_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
for path in (BASE_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from src.conversion.bpmn2rdf import BPMNToRDFConverter
from src.core import RDFProcessEngine

from handlers import build_handlers
from handlers.common import llm_summary

PROCESS_DIR = os.path.join(BASE_DIR, "processes")
MEMORY_PATH = os.path.join(BASE_DIR, "memory.rdf")
ENGINE_PATH = os.path.join(BASE_DIR, "engine.rdf")
ENV_PATH = os.path.join(BASE_DIR, ".env")

BPMN_NS = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
CAMUNDA_NS = Namespace("http://camunda.org/schema/1.0/bpmn#")
AGT = Namespace("http://example.org/agent/")
MEM = Namespace("http://example.org/memory/")
SRC = Namespace("http://example.org/source/")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")


def _load_env(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value and value[0] in {"'", '"'} and value[-1:] == value[0]:
                value = value[1:-1]
            if "#" in value:
                value = value.split("#", 1)[0].strip()
            os.environ[key] = value


def _load_graph(path: str) -> Graph:
    graph = Graph()
    if os.path.exists(path):
        graph.parse(path, format="turtle")
    return graph


def _split_memory_engine_if_needed(memory_graph: Graph, engine_graph: Graph) -> None:
    if os.path.exists(ENGINE_PATH):
        return
    if not os.path.exists(MEMORY_PATH):
        return

    engine_pred_prefixes = (
        "http://dkm.fbk.eu/index.php/BPMN2_Ontology#",
        "http://camunda.org/schema/1.0/bpmn#",
        "http://example.org/di/",
        "http://www.omg.org/spec/DD/20100524/DC#",
        "http://example.org/audit/",
        "http://example.org/instance/",
        "http://example.org/token/",
    )
    engine_obj_prefixes = (
        "http://dkm.fbk.eu/index.php/BPMN2_Ontology#",
        "http://camunda.org/schema/1.0/bpmn#",
        "http://example.org/audit/",
        "http://example.org/instance/",
        "http://example.org/token/",
    )

    to_move = []
    for s, p, o in memory_graph:
        p_str = str(p)
        o_str = str(o)
        if p_str.startswith(engine_pred_prefixes):
            to_move.append((s, p, o))
            continue
        if p == RDF.type and o_str.startswith(engine_obj_prefixes):
            to_move.append((s, p, o))

    for s, p, o in to_move:
        memory_graph.remove((s, p, o))
        engine_graph.add((s, p, o))


def _merge_bpmn_definitions(
    graph: Graph, include_files: Optional[List[str]] = None
) -> None:
    graph.bind("bpmn", BPMN_NS, replace=True)
    graph.bind("camunda", CAMUNDA_NS, replace=True)
    # Remove prior BPMN element triples to avoid duplicated flows across runs.
    bpmn_base = "http://example.org/bpmn/"
    to_remove = []
    for s, p, o in graph:
        if str(s).startswith(bpmn_base):
            to_remove.append((s, p, o))
    for s, p, o in to_remove:
        graph.remove((s, p, o))
    converter = BPMNToRDFConverter()
    for filename in os.listdir(PROCESS_DIR):
        if not filename.endswith(".bpmn"):
            continue
        if include_files and filename not in include_files:
            continue
        path = os.path.join(PROCESS_DIR, filename)
        bpmn_graph = converter.parse_bpmn_to_graph(path)
        for triple in bpmn_graph:
            graph.add(triple)

    # Mirror camunda:topic to bpmn:topic for execution compatibility
    for subject, _, topic in list(graph.triples((None, CAMUNDA_NS.topic, None))):
        graph.add((subject, BPMN_NS.topic, topic))

    # Normalize lower-case BPMN element types to match engine expectations
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
        for subject, _, _ in list(graph.triples((None, None, lower_uri))):
            graph.remove((subject, RDF.type, lower_uri))
            graph.add((subject, RDF.type, upper_uri))


def run_scheduler_tick() -> None:
    _load_env(ENV_PATH)
    memory_graph = _load_graph(MEMORY_PATH)
    engine_graph = _load_graph(ENGINE_PATH)
    _split_memory_engine_if_needed(memory_graph, engine_graph)
    _merge_bpmn_definitions(engine_graph, include_files=["agent_scheduler.bpmn"])

    engine = RDFProcessEngine(engine_graph, engine_graph)
    handlers = build_handlers(engine, memory_graph)
    for topic, handler in handlers.items():
        engine.register_topic_handler(topic, handler)

    scheduler_process_uri = "http://example.org/bpmn/AgentSchedulerProcess"
    engine.start_process_instance(
        scheduler_process_uri, start_event_id="StartEvent_Scheduler"
    )

    memory_graph.serialize(MEMORY_PATH, format="turtle")
    engine_graph.serialize(ENGINE_PATH, format="turtle")

def run_agent_cycle(
    agent_uri: Optional[str] = None, variables: Optional[Dict] = None
) -> None:
    _load_env(ENV_PATH)
    if os.getenv("AGENT_VERBOSE", "").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[runner] AGENT_VERBOSE={os.getenv('AGENT_VERBOSE')}")
        print(f"[runner] BRAVE_API_KEY set={bool(os.getenv('BRAVE_API_KEY'))}")
        print(f"[runner] LITELLM_API_BASE={os.getenv('LITELLM_API_BASE')}")
    memory_graph = _load_graph(MEMORY_PATH)
    engine_graph = _load_graph(ENGINE_PATH)
    _split_memory_engine_if_needed(memory_graph, engine_graph)
    _merge_bpmn_definitions(engine_graph, include_files=["agent_cycle.bpmn"])

    engine = RDFProcessEngine(engine_graph, engine_graph)
    handlers = build_handlers(engine, memory_graph)
    verbose = os.getenv("AGENT_VERBOSE", "").strip().lower() in {"1", "true", "yes", "on"}
    for topic, handler in handlers.items():
        if verbose:
            def _wrap(h, name):
                def _wrapped(context):
                    print(f"[agent] handler: {name}")
                    return h(context)
                return _wrapped
            engine.register_topic_handler(topic, _wrap(handler, topic))
        else:
            engine.register_topic_handler(topic, handler)

    cycle_process_uri = "http://example.org/bpmn/AgentCycleProcess"
    merged_vars = dict(variables or {})
    if agent_uri:
        merged_vars["agent_uri"] = agent_uri
    initial_vars = merged_vars or None
    if verbose:
        print(f"[runner] initial_vars={initial_vars}")
    instance = engine.start_process_instance(
        cycle_process_uri,
        initial_variables=initial_vars,
        start_event_id="StartEvent_Cycle",
    )
    if verbose:
        print(f"[runner] instance status={instance.status}")
        for token in instance.tokens:
            node = token.current_node
            node_type = engine_graph.value(node, RDF.type) if node else None
            topic = engine_graph.value(node, BPMN_NS.topic) if node else None
            print(f"[runner] token {token.token_id} {token.status} {node} {node_type} {topic}")
        if merged_vars and "user_question" in merged_vars:
            inst_uri = instance.instance_uri
            var_pred = Namespace("http://example.org/variables/")["user_question"]
            var_value = engine_graph.value(inst_uri, var_pred)
            print(f"[runner] user_question var={var_value}")
            all_vars = list(engine_graph.triples((inst_uri, var_pred, None)))
            print(f"[runner] user_question triples={all_vars}")
            answer_pred = Namespace("http://example.org/variables/")["answer_text"]
            answer_value = engine_graph.value(inst_uri, answer_pred)
            print(f"[runner] answer_text var={answer_value}")
            gw = "http://example.org/bpmn/Gateway_UserQuestion"
            cond = engine_graph.value(
                URIRef("http://example.org/bpmn/Flow_GatewayToAnswer"),
                BPMN_NS.conditionQuery,
            )
            print(f"[runner] gateway conditionQuery={cond}")

    memory_graph.serialize(MEMORY_PATH, format="turtle")
    engine_graph.serialize(ENGINE_PATH, format="turtle")


def _format_dt(value) -> str:
    if value is None:
        return "unknown"
    try:
        dt = value.toPython()
        if isinstance(dt, datetime):
            return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return str(value)
    return str(value)


def print_summary(limit: int = 5) -> None:
    graph = _load_graph(MEMORY_PATH)

    agents = list(graph.triples((None, RDF.type, AGT.AgentInstance)))
    if agents:
        agent_uri = agents[0][0]
        goal = graph.value(agent_uri, AGT.currentGoal)
        last_run = graph.value(agent_uri, AGT.lastRunAt)
        next_run = graph.value(agent_uri, AGT.nextRunAt)
        print(f"Agent: {agent_uri}")
        print(f"Goal: {goal}")
        print(f"Last run: {_format_dt(last_run)}")
        print(f"Next run: {_format_dt(next_run)}")
        print("")

    notes = []
    for note, _, _ in graph.triples((None, RDF.type, MEM.Note)):
        created = graph.value(note, MEM.createdAt)
        content = graph.value(note, MEM.content)
        notes.append((created, note, content))

    notes.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    print("Latest notes:")
    for created, note, content in notes[:limit]:
        created_str = _format_dt(created)
        snippet = str(content) if content else ""
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        print(f"- {created_str} {note}: {snippet}")

    goal_snaps = []
    for snap, _, _ in graph.triples((None, RDF.type, MEM.GoalSnapshot)):
        created = graph.value(snap, MEM.createdAt)
        content = graph.value(snap, MEM.content)
        goal_snaps.append((created, snap, content))

    goal_snaps.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    print("")
    print("Goal history:")
    for created, snap, content in goal_snaps[:limit]:
        created_str = _format_dt(created)
        print(f"- {created_str} {snap}: {content}")

    query_snaps = []
    for snap, _, _ in graph.triples((None, RDF.type, MEM.QuerySnapshot)):
        created = graph.value(snap, MEM.createdAt)
        content = graph.value(snap, MEM.content)
        query_snaps.append((created, snap, content))

    query_snaps.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    print("")
    print("Query history:")
    for created, snap, content in query_snaps[:limit]:
        created_str = _format_dt(created)
        print(f"- {created_str} {snap}: {content}")

    summaries = []
    for summary, _, _ in graph.triples((None, RDF.type, MEM.Summary)):
        created = graph.value(summary, MEM.createdAt)
        content = graph.value(summary, MEM.content)
        summaries.append((created, summary, content))

    summaries.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    print("")
    print("Latest summaries:")
    for created, summary, content in summaries[:limit]:
        created_str = _format_dt(created)
        snippet = str(content) if content else ""
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        print(f"- {created_str} {summary}: {snippet}")

    results = []
    for result, _, _ in graph.triples((None, RDF.type, SRC.WebResult)):
        fetched = graph.value(result, SRC.fetchedAt)
        title = graph.value(result, SRC.title)
        url = graph.value(result, SRC.url)
        results.append((fetched, result, title, url))

    results.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    print("")
    print("Latest web results:")
    for fetched, result, title, url in results[:limit]:
        fetched_str = _format_dt(fetched)
        print(f"- {fetched_str} {result}: {title} ({url})")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenClaw SPEAR runner")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose agent logs")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run-scheduler", help="Run a scheduler tick (default)")
    cycle = sub.add_parser("run-cycle", help="Run a single agent cycle")
    cycle.add_argument("--agent-uri", default=None, help="Override agent URI")

    summary = sub.add_parser("summary", help="Print latest memory summary")
    summary.add_argument("--limit", type=int, default=5, help="Number of notes to show")

    sub.add_parser("goal-history", help="Print goal changes over time")
    sub.add_parser("query-history", help="Print search query changes over time")
    sub.add_parser("trace", help="Print latest reasoning chain (query → results → summary → reflection → goal)")

    reset = sub.add_parser("reset-memory", help="Reset memory.rdf to a clean seed")
    reset.add_argument("--keep-backup", action="store_true", help="Keep memory.rdf.bak")

    ask = sub.add_parser("ask", help="Store a prompt and run a cycle")
    ask.add_argument("prompt", help="Prompt to store and process")
    ask.add_argument("--agent-uri", default=None, help="Override agent URI")

    cleanup = sub.add_parser("cleanup-memory", help="Remove engine/audit triples and prune memory")
    cleanup.add_argument("--keep", type=int, default=50, help="Items to keep per category")
    cleanup.add_argument("--dry-run", action="store_true", help="Show counts without writing changes")

    tell = sub.add_parser("tell", help="Store user-provided information into memory")
    tell.add_argument("info", help="Information to store")

    return parser.parse_args()


def _print_goal_history(limit: int = 10) -> None:
    graph = _load_graph(MEMORY_PATH)
    goal_snaps = []
    for snap, _, _ in graph.triples((None, RDF.type, MEM.GoalSnapshot)):
        created = graph.value(snap, MEM.createdAt)
        content = graph.value(snap, MEM.content)
        goal_snaps.append((created, snap, content))

    goal_snaps.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    print("Goal history:")
    for created, snap, content in goal_snaps[:limit]:
        created_str = _format_dt(created)
        print(f"- {created_str} {snap}: {content}")


def _print_query_history(limit: int = 10) -> None:
    graph = _load_graph(MEMORY_PATH)
    query_snaps = []
    for snap, _, _ in graph.triples((None, RDF.type, MEM.QuerySnapshot)):
        created = graph.value(snap, MEM.createdAt)
        content = graph.value(snap, MEM.content)
        query_snaps.append((created, snap, content))

    query_snaps.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    print("Query history:")
    for created, snap, content in query_snaps[:limit]:
        created_str = _format_dt(created)
        print(f"- {created_str} {snap}: {content}")


def _print_trace(limit_results: int = 3) -> None:
    graph = _load_graph(MEMORY_PATH)

    # Find latest QuerySnapshot
    snaps = []
    for snap, _, _ in graph.triples((None, RDF.type, MEM.QuerySnapshot)):
        created = graph.value(snap, MEM.createdAt)
        snaps.append((created, snap))
    if not snaps:
        print("No query snapshots found.")
        return

    snaps.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
    created, snap = snaps[0]
    query_text = graph.value(snap, MEM.content)
    print("Trace (latest run):")
    print(f"Query @ { _format_dt(created) }")
    print(f"  {query_text}")

    # Results
    results = []
    for _, _, result in graph.triples((snap, MEM.hasResult, None)):
        title = graph.value(result, SRC.title)
        url = graph.value(result, SRC.url)
        results.append((result, title, url))
    if results:
        print("Results:")
        for result, title, url in results[:limit_results]:
            print(f"  - {title} ({url})")
    else:
        print("Results: none")

    # Summary
    summary_node = graph.value(snap, MEM.hasSummary)
    if summary_node:
        summary_text = graph.value(summary_node, MEM.content)
        print("Summary:")
        print(f"  {summary_text}")
    else:
        print("Summary: none")

    # Reflection
    reflection_node = graph.value(summary_node, MEM.reflectedBy) if summary_node else None
    if reflection_node:
        reflection_text = graph.value(reflection_node, MEM.content)
        new_goal = graph.value(reflection_node, MEM.updatedGoal)
        print("Reflection:")
        print(f"  {reflection_text}")
        if new_goal:
            print("Goal update:")
            print(f"  {new_goal}")
    else:
        print("Reflection: none")


def _ask_from_memory(question: str, limit: int = 5) -> str:
    _load_env(ENV_PATH)
    graph = _load_graph(MEMORY_PATH)

    agents = list(graph.triples((None, RDF.type, AGT.AgentInstance)))
    agent_uri = agents[0][0] if agents else None

    goal = graph.value(agent_uri, AGT.currentGoal) if agent_uri else None

    summaries = []
    for node, _, _ in graph.triples((None, RDF.type, MEM.Summary)):
        created = graph.value(node, MEM.createdAt)
        content = graph.value(node, MEM.content)
        summaries.append((created, content))
    summaries.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)

    reflections = []
    for node, _, _ in graph.triples((None, RDF.type, MEM.Reflection)):
        created = graph.value(node, MEM.createdAt)
        content = graph.value(node, MEM.content)
        reflections.append((created, content))
    reflections.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)

    memory_context = []
    if goal:
        memory_context.append(f"Current goal: {goal}")
    if summaries:
        memory_context.append("Recent summaries:")
        for created, content in summaries[:limit]:
            memory_context.append(f"- {_format_dt(created)} {content}")
    if reflections:
        memory_context.append("Recent reflections:")
        for created, content in reflections[:limit]:
            memory_context.append(f"- {_format_dt(created)} {content}")

    memory_block = "\n".join(memory_context)
    prompt = (
        "Answer the user's question using only the agent's memory. "
        "If memory is insufficient, say so and suggest what to search for next.\n\n"
        f"Memory:\n{memory_block}\n\n"
        f"User question: {question}\n"
    )

    answer = llm_summary(prompt)

    # Persist Q/A
    if agent_uri:
        q_node = MEM[f"UserQuestion_{int(datetime.now(timezone.utc).timestamp())}"]
        a_node = MEM[f"AgentAnswer_{int(datetime.now(timezone.utc).timestamp())}"]
        graph.add((q_node, RDF.type, MEM.UserQuestion))
        graph.add((q_node, MEM.content, Literal(question)))
        graph.add(
            (q_node, MEM.createdAt, Literal(datetime.now(timezone.utc), datatype=XSD.dateTime))
        )
        graph.add((a_node, RDF.type, MEM.AgentAnswer))
        graph.add((a_node, MEM.content, Literal(answer)))
        graph.add(
            (a_node, MEM.createdAt, Literal(datetime.now(timezone.utc), datatype=XSD.dateTime))
        )
        graph.add((agent_uri, MEM.askedQuestion, q_node))
        graph.add((agent_uri, MEM.answeredBy, a_node))
        graph.add((q_node, MEM.answer, a_node))
        graph.serialize(MEMORY_PATH, format="turtle")

    return answer


def _cleanup_memory(keep: int = 50, dry_run: bool = False) -> None:
    memory_graph = _load_graph(MEMORY_PATH)
    engine_graph = _load_graph(ENGINE_PATH)
    _split_memory_engine_if_needed(memory_graph, engine_graph)

    # Remove engine/audit/instance/di triples left in memory.
    engine_pred_prefixes = (
        "http://dkm.fbk.eu/index.php/BPMN2_Ontology#",
        "http://camunda.org/schema/1.0/bpmn#",
        "http://example.org/di/",
        "http://www.omg.org/spec/DD/20100524/DC#",
        "http://example.org/audit/",
        "http://example.org/instance/",
        "http://example.org/token/",
    )
    engine_obj_prefixes = (
        "http://dkm.fbk.eu/index.php/BPMN2_Ontology#",
        "http://camunda.org/schema/1.0/bpmn#",
        "http://example.org/audit/",
        "http://example.org/instance/",
        "http://example.org/token/",
    )
    to_remove = []
    for s, p, o in memory_graph:
        p_str = str(p)
        o_str = str(o)
        if p_str.startswith(engine_pred_prefixes):
            to_remove.append((s, p, o))
            continue
        if p == RDF.type and o_str.startswith(engine_obj_prefixes):
            to_remove.append((s, p, o))

    if dry_run:
        print(f"[runner] Would move {len(to_remove)} engine/audit triples to engine.rdf")
    else:
        for s, p, o in to_remove:
            memory_graph.remove((s, p, o))
            engine_graph.add((s, p, o))

    # Prune older items in each category.
    def _prune(category_uri, keep_count: int):
        items = []
        for node, _, _ in memory_graph.triples((None, RDF.type, category_uri)):
            created = memory_graph.value(node, MEM.createdAt)
            items.append((created, node))
        items.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
        if dry_run:
            print(f"[runner] Would prune {max(0, len(items) - keep_count)} from {category_uri}")
        else:
            for _, node in items[keep_count:]:
                memory_graph.remove((node, None, None))
                memory_graph.remove((None, None, node))

    for category in (
        MEM.Note,
        MEM.Summary,
        MEM.Reflection,
        MEM.GoalSnapshot,
        MEM.QuerySnapshot,
    ):
        _prune(category, keep)

    # Prune WebResults by keeping only those still linked from QuerySnapshots.
    linked_results = set()
    for snap, _, result in memory_graph.triples((None, MEM.hasResult, None)):
        linked_results.add(result)
    orphan_results = 0
    for result, _, _ in list(memory_graph.triples((None, RDF.type, SRC.WebResult))):
        if result not in linked_results:
            orphan_results += 1
            if not dry_run:
                memory_graph.remove((result, None, None))
                memory_graph.remove((None, None, result))
    if dry_run:
        print(f"[runner] Would remove {orphan_results} orphan WebResult nodes")
        return

    memory_graph.serialize(MEMORY_PATH, format="turtle")
    engine_graph.serialize(ENGINE_PATH, format="turtle")
    print(f"[runner] Cleaned memory (kept {keep} per category)")


def main() -> None:
    args = _parse_args()
    if args.verbose:
        os.environ["AGENT_VERBOSE"] = "true"
    if args.command == "reset-memory":
        backup_path = f"{MEMORY_PATH}.bak"
        if os.path.exists(MEMORY_PATH):
            if not args.keep_backup and os.path.exists(backup_path):
                os.remove(backup_path)
            os.replace(MEMORY_PATH, backup_path)
        seed_path = os.path.join(BASE_DIR, "memory_seed.rdf")
        if os.path.exists(seed_path):
            with open(seed_path, "r", encoding="utf-8") as src:
                seed_data = src.read()
            with open(MEMORY_PATH, "w", encoding="utf-8") as dst:
                dst.write(seed_data)
        else:
            # Fallback: write a minimal seed if no seed file exists.
            with open(MEMORY_PATH, "w", encoding="utf-8") as dst:
                dst.write(
                    "@prefix agt: <http://example.org/agent/> .\n"
                    "@prefix mem: <http://example.org/memory/> .\n"
                    "@prefix bpmn: <http://example.org/bpmn/> .\n"
                    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
                    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n"
                    "agt:Agent_1 a agt:Agent, agt:AgentInstance ;\n"
                    "    agt:currentGoal \"Discover itself and research ways to improve itself.\" ;\n"
                    "    agt:cadenceSeconds 1800 ;\n"
                    "    agt:cycleProcess bpmn:AgentCycleProcess ;\n"
                    "    agt:schedulerProcess bpmn:AgentSchedulerProcess .\n"
                )
        print(f"[runner] Reset memory at {MEMORY_PATH}")
        return
    if args.command == "run-cycle":
        run_agent_cycle(agent_uri=args.agent_uri)
        return
    if args.command == "summary":
        print_summary(limit=args.limit)
        return
    if args.command == "goal-history":
        _print_goal_history(limit=10)
        return
    if args.command == "query-history":
        _print_query_history(limit=10)
        return
    if args.command == "trace":
        _print_trace()
        return
    if args.command == "ask":
        pre_graph = _load_graph(MEMORY_PATH)
        pre_goal = None
        agents = list(pre_graph.triples((None, RDF.type, AGT.AgentInstance)))
        if agents:
            pre_goal = pre_graph.value(agents[0][0], AGT.currentGoal)

        run_agent_cycle(variables={"user_question": args.prompt})

        # Print the latest answer from memory (best effort).
        graph = _load_graph(MEMORY_PATH)
        answers = []
        for node, _, _ in graph.triples((None, RDF.type, MEM.AgentAnswer)):
            created = graph.value(node, MEM.createdAt)
            content = graph.value(node, MEM.content)
            answers.append((created, content))
        answers.sort(key=lambda item: str(item[0]) if item[0] else "", reverse=True)
        if answers and answers[0][1]:
            print(str(answers[0][1]))
        agents = list(graph.triples((None, RDF.type, AGT.AgentInstance)))
        if agents:
            post_goal = graph.value(agents[0][0], AGT.currentGoal)
            if pre_goal != post_goal:
                print(f"[runner] goal changed: {pre_goal} -> {post_goal}")
            else:
                print(f"[runner] goal unchanged: {post_goal}")
        return
    if args.command == "cleanup-memory":
        _cleanup_memory(keep=args.keep, dry_run=args.dry_run)
        return
    if args.command == "tell":
        run_agent_cycle(variables={"user_info": args.info})
        return
    run_scheduler_tick()


if __name__ == "__main__":
    main()
