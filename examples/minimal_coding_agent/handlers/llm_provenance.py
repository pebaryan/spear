"""RDF-based LLM interaction tracker for detailed provenance."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
LLM_LOG_PATH = BASE_DIR / "llm_interactions.ttl"

AG = Namespace("http://example.org/agent/")
LLM = Namespace("http://example.org/llm/")
TOOL = Namespace("http://example.org/tool/")
PROC = Namespace("http://example.org/process/")

_namespaces = {
    "ag": AG,
    "llm": LLM,
    "tool": TOOL,
    "proc": PROC,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}


def _create_llm_log_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_llm_log_graph() -> Graph:
    g = _create_llm_log_graph()
    if LLM_LOG_PATH.exists():
        g.parse(LLM_LOG_PATH, format="turtle")
    return g


def save_llm_log_graph(g: Graph) -> None:
    g.serialize(LLM_LOG_PATH, format="turtle")


def _get_interaction_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, LLM.Interaction):
        count += 1
    return count


def log_llm_interaction(
    prompt: str,
    response: str,
    model: str,
    metadata: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Log an LLM interaction to RDF."""
    g = load_llm_log_graph()

    interaction_id = _get_interaction_count(g)
    interaction_uri = LLM[f"interaction/{interaction_id}"]

    g.add((interaction_uri, RDF.type, LLM.Interaction))
    g.add(
        (
            interaction_uri,
            LLM.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((interaction_uri, LLM.model, Literal(model)))

    if len(prompt) > 5000:
        prompt = prompt[:5000] + "... [truncated]"
    g.add((interaction_uri, LLM.prompt, Literal(prompt)))

    if len(response) > 10000:
        response = response[:10000] + "... [truncated]"
    g.add((interaction_uri, LLM.response, Literal(response)))

    if metadata:
        if "temperature" in metadata:
            g.add((interaction_uri, LLM.temperature, Literal(metadata["temperature"])))
        if "usage" in metadata:
            usage = metadata["usage"]
            if isinstance(usage, dict):
                for key, value in usage.items():
                    g.add((interaction_uri, LLM[f"usage_{key}"], Literal(str(value))))
        if "finish_reason" in metadata:
            g.add(
                (interaction_uri, LLM.finishReason, Literal(metadata["finish_reason"]))
            )

    if tool_calls:
        for idx, tool_call in enumerate(tool_calls):
            tool_uri = LLM[f"interaction/{interaction_id}/tool/{idx}"]
            g.add((tool_uri, RDF.type, TOOL.Call))
            g.add((tool_uri, LLM.calledAt, interaction_uri))

            if "name" in tool_call:
                g.add((tool_uri, TOOL.name, Literal(tool_call["name"])))
            if "arguments" in tool_call:
                args = tool_call["arguments"]
                if isinstance(args, str) and len(args) > 1000:
                    args = args[:1000] + "... [truncated]"
                g.add((tool_uri, TOOL.arguments, Literal(str(args))))
            if "result" in tool_call:
                result = tool_call["result"]
                if isinstance(result, str) and len(result) > 2000:
                    result = result[:2000] + "... [truncated]"
                g.add((tool_uri, TOOL.result, Literal(str(result))))

    save_llm_log_graph(g)

    return str(interaction_uri)


def log_build_interaction(
    task: str,
    prompt: str,
    response: str,
    model: str,
    success: bool,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Log a build code LLM interaction."""
    g = load_llm_log_graph()

    interaction_id = _get_interaction_count(g)
    interaction_uri = LLM[f"build/{interaction_id}"]

    g.add((interaction_uri, RDF.type, LLM.BuildInteraction))
    g.add(
        (
            interaction_uri,
            LLM.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((interaction_uri, LLM.model, Literal(model)))
    g.add((interaction_uri, LLM.task, Literal(task)))
    g.add((interaction_uri, LLM.success, Literal(success, datatype=XSD.boolean)))

    if len(prompt) > 5000:
        prompt = prompt[:5000] + "... [truncated]"
    g.add((interaction_uri, LLM.prompt, Literal(prompt)))

    if len(response) > 10000:
        response = response[:10000] + "... [truncated]"
    g.add((interaction_uri, LLM.response, Literal(response)))

    if metadata:
        if "temperature" in metadata:
            g.add((interaction_uri, LLM.temperature, Literal(metadata["temperature"])))
        if "usage" in metadata:
            usage = metadata["usage"]
            if isinstance(usage, dict):
                for key, value in usage.items():
                    g.add((interaction_uri, LLM[f"usage_{key}"], Literal(str(value))))

    save_llm_log_graph(g)

    return str(interaction_uri)


def log_fix_interaction(
    source_code: str,
    error_message: str,
    prompt: str,
    response: str,
    model: str,
    success: bool,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Log a fix code LLM interaction."""
    g = load_llm_log_graph()

    interaction_id = _get_interaction_count(g)
    interaction_uri = LLM[f"fix/{interaction_id}"]

    g.add((interaction_uri, RDF.type, LLM.FixInteraction))
    g.add(
        (
            interaction_uri,
            LLM.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((interaction_uri, LLM.model, Literal(model)))
    g.add((interaction_uri, LLM.success, Literal(success, datatype=XSD.boolean)))

    if len(source_code) > 2000:
        source_code = source_code[:2000] + "... [truncated]"
    g.add((interaction_uri, LLM.sourceCode, Literal(source_code)))

    if len(error_message) > 1000:
        error_message = error_message[:1000] + "... [truncated]"
    g.add((interaction_uri, LLM.errorMessage, Literal(error_message)))

    if len(prompt) > 3000:
        prompt = prompt[:3000] + "... [truncated]"
    g.add((interaction_uri, LLM.prompt, Literal(prompt)))

    if len(response) > 5000:
        response = response[:5000] + "... [truncated]"
    g.add((interaction_uri, LLM.response, Literal(response)))

    if metadata:
        if "temperature" in metadata:
            g.add((interaction_uri, LLM.temperature, Literal(metadata["temperature"])))

    save_llm_log_graph(g)

    return str(interaction_uri)


def get_interactions(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent LLM interactions."""
    g = load_llm_log_graph()

    interactions = []
    for interaction in g.subjects(RDF.type, LLM.Interaction):
        data = {
            "uri": str(interaction),
            "timestamp": str(g.value(interaction, LLM.timestamp) or ""),
            "model": str(g.value(interaction, LLM.model) or ""),
            "prompt": str(g.value(interaction, LLM.prompt) or ""),
            "response": str(g.value(interaction, LLM.response) or ""),
        }
        success = g.value(interaction, LLM.success)
        if success:
            data["success"] = str(success).lower() == "true"
        interactions.append(data)

    for interaction in g.subjects(RDF.type, LLM.BuildInteraction):
        data = {
            "uri": str(interaction),
            "timestamp": str(g.value(interaction, LLM.timestamp) or ""),
            "model": str(g.value(interaction, LLM.model) or ""),
            "prompt": str(g.value(interaction, LLM.prompt) or ""),
            "response": str(g.value(interaction, LLM.response) or ""),
            "task": str(g.value(interaction, LLM.task) or ""),
        }
        success = g.value(interaction, LLM.success)
        if success:
            data["success"] = str(success).lower() == "true"
        interactions.append(data)

    for interaction in g.subjects(RDF.type, LLM.FixInteraction):
        data = {
            "uri": str(interaction),
            "timestamp": str(g.value(interaction, LLM.timestamp) or ""),
            "model": str(g.value(interaction, LLM.model) or ""),
            "prompt": str(g.value(interaction, LLM.prompt) or ""),
            "response": str(g.value(interaction, LLM.response) or ""),
        }
        success = g.value(interaction, LLM.success)
        if success:
            data["success"] = str(success).lower() == "true"
        interactions.append(data)

    interactions.sort(key=lambda x: x["timestamp"], reverse=True)
    return interactions[:limit]


def query_interactions(sparql: str) -> List[Dict[str, Any]]:
    """Query LLM interactions with custom SPARQL."""
    g = load_llm_log_graph()

    results = []
    for row in g.query(sparql):
        result = {}
        for var in row.labels:
            result[var] = str(row[var]) if row[var] else None
        results.append(result)
    return results
