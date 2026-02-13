"""RDF-based session history tracker for minimal coding agent."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_GRAPH_PATH = BASE_DIR / "session_history.ttl"

AG = Namespace("http://example.org/agent/")
SESS = Namespace("http://example.org/session/")
PROC = Namespace("http://example.org/process/")

_namespaces = {
    "ag": AG,
    "sess": SESS,
    "proc": PROC,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}


def _create_history_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_history_graph() -> Graph:
    g = _create_history_graph()
    if HISTORY_GRAPH_PATH.exists():
        g.parse(HISTORY_GRAPH_PATH, format="turtle")
    return g


def save_history_graph(g: Graph) -> None:
    g.serialize(HISTORY_GRAPH_PATH, format="turtle")


def _get_run_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, AG.Run):
        count += 1
    return count


def add_run(command: str, task: str, success: bool, details: Dict[str, Any]) -> None:
    g = load_history_graph()

    run_id = _get_run_count(g)
    run_uri = SESS[f"run/{run_id}"]

    g.add((run_uri, RDF.type, AG.Run))
    g.add((run_uri, AG.command, Literal(command)))
    g.add((run_uri, AG.task, Literal(task)))
    g.add((run_uri, AG.success, Literal(success, datatype=XSD.boolean)))
    g.add(
        (
            run_uri,
            AG.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )

    if "exit_code" in details:
        g.add((run_uri, AG.exitCode, Literal(details["exit_code"])))

    if "output" in details:
        output = details["output"]
        if len(output) > 500:
            output = output[:500]
        g.add((run_uri, AG.outputSummary, Literal(output)))

    if command == "build":
        process_uri = PROC.MinimalCodingAgentBuildProcess
        g.add((run_uri, AG.process, process_uri))
    else:
        process_uri = PROC.MinimalCodingAgentProcess
        g.add((run_uri, AG.process, process_uri))

    save_history_graph(g)


def get_history(limit: int = 10) -> List[Dict[str, Any]]:
    g = load_history_graph()

    runs = []
    for run in g.subjects(RDF.type, AG.Run):
        timestamp = g.value(run, AG.timestamp)
        command = g.value(run, AG.command)
        task = g.value(run, AG.task)
        success = g.value(run, AG.success)
        exit_code = g.value(run, AG.exitCode)
        output = g.value(run, AG.outputSummary)

        runs.append(
            {
                "uri": str(run),
                "timestamp": str(timestamp) if timestamp else "",
                "command": str(command) if command else "",
                "task": str(task) if task else "",
                "success": str(success).lower() == "true" if success else False,
                "exit_code": str(exit_code) if exit_code else "-1",
                "output": str(output) if output else "",
            }
        )

    runs.sort(key=lambda x: x["timestamp"], reverse=True)
    return runs[:limit]


def clear_history() -> None:
    g = _create_history_graph()
    save_history_graph(g)


def query_history(sparql: str) -> List[Dict[str, Any]]:
    g = load_history_graph()

    results = []
    for row in g.query(sparql):
        result = {}
        for var in row.labels:
            result[var] = str(row[var]) if row[var] else None
        results.append(result)
    return results


def get_runs_by_command(command: str) -> List[Dict[str, Any]]:
    sparql = f"""
    PREFIX ag: <http://example.org/agent/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    
    SELECT ?run ?timestamp ?task ?success ?exitCode
    WHERE {{
        ?run a ag:Run .
        ?run ag:command "{command}" .
        ?run ag:timestamp ?timestamp .
        ?run ag:task ?task .
        ?run ag:success ?success .
        OPTIONAL {{ ?run ag:exitCode ?exitCode }}
    }}
    ORDER BY DESC(?timestamp)
    """
    return query_history(sparql)


def get_failed_runs() -> List[Dict[str, Any]]:
    sparql = """
    PREFIX ag: <http://example.org/agent/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    
    SELECT ?run ?timestamp ?command ?task ?exitCode
    WHERE {
        ?run a ag:Run .
        ?run ag:timestamp ?timestamp .
        ?run ag:command ?command .
        ?run ag:task ?task .
        ?run ag:success false .
        OPTIONAL { ?run ag:exitCode ?exitCode }
    }
    ORDER BY DESC(?timestamp)
    """
    return query_history(sparql)
