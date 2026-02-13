"""RDF-based reasoning trace for self-introspective agent.

This module tracks the agent's decision-making process, enabling:
- Decision reasoning (why I chose approach X)
- Self-questioning (why did I do X?)
- Explanation generation (I fixed it because...)
- Causal chain reasoning
- Meta-cognition (reflection on patterns)
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
REASONING_LOG_PATH = BASE_DIR / "reasoning_trace.ttl"

AG = Namespace("http://example.org/agent/")
REASON = Namespace("http://example.org/reasoning/")
LLM = Namespace("http://example.org/llm/")
ART = Namespace("http://example.org/artifact/")

_namespaces = {
    "ag": AG,
    "reason": REASON,
    "llm": LLM,
    "art": ART,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}


def _create_reasoning_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_reasoning_graph() -> Graph:
    g = _create_reasoning_graph()
    if REASONING_LOG_PATH.exists():
        g.parse(REASONING_LOG_PATH, format="turtle")
    return g


def save_reasoning_graph(g: Graph) -> None:
    g.serialize(REASONING_LOG_PATH, format="turtle")


def _get_reasoning_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, REASON.Decision):
        count += 1
    return count


def log_decision(
    decision_type: str,
    context: str,
    rationale: str,
    alternatives_considered: Optional[List[str]] = None,
    chosen_approach: Optional[str] = None,
    confidence: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Log a decision with reasoning."""
    g = load_reasoning_graph()

    decision_id = _get_reasoning_count(g)
    decision_uri = REASON[f"decision/{decision_id}"]

    g.add((decision_uri, RDF.type, REASON.Decision))
    g.add(
        (
            decision_uri,
            REASON.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((decision_uri, REASON.decisionType, Literal(decision_type)))
    g.add((decision_uri, REASON.context, Literal(context)))
    g.add((decision_uri, REASON.rationale, Literal(rationale)))

    if chosen_approach:
        g.add((decision_uri, REASON.chosenApproach, Literal(chosen_approach)))

    if confidence is not None:
        g.add(
            (decision_uri, REASON.confidence, Literal(confidence, datatype=XSD.float))
        )

    if alternatives_considered:
        for idx, alt in enumerate(alternatives_considered):
            g.add((decision_uri, REASON.consideredAlternative, Literal(alt)))

    if metadata:
        for key, value in metadata.items():
            g.add((decision_uri, REASON[key], Literal(str(value))))

    save_reasoning_graph(g)

    return str(decision_uri)


def log_approach_choice(
    task: str,
    chosen_approach: str,
    rationale: str,
    alternatives: Optional[List[str]] = None,
) -> str:
    """Log why the agent chose a particular approach."""
    return log_decision(
        decision_type="approach_selection",
        context=f"Task: {task}",
        rationale=rationale,
        alternatives_considered=alternatives,
        chosen_approach=chosen_approach,
    )


def log_code_change_reason(
    change_type: str,
    file_path: str,
    reason: str,
    before_state: Optional[str] = None,
    after_state: Optional[str] = None,
) -> str:
    """Log why a specific code change was made."""
    return log_decision(
        decision_type="code_change",
        context=f"File: {file_path}, Change: {change_type}",
        rationale=reason,
    )


def log_fix_strategy(
    bug_description: str,
    strategy: str,
    rationale: str,
    alternative_strategies: Optional[List[str]] = None,
) -> str:
    """Log the strategy for fixing a bug."""
    return log_decision(
        decision_type="fix_strategy",
        context=f"Bug: {bug_description}",
        rationale=rationale,
        alternatives_considered=alternative_strategies,
        chosen_approach=strategy,
    )


def log_self_correction(
    action: str,
    reason_for_correction: str,
    what_was_wrong: str,
    correction_made: str,
) -> str:
    """Log a self-correction during execution."""
    g = load_reasoning_graph()

    correction_id = _get_reasoning_count(g)
    correction_uri = REASON[f"correction/{correction_id}"]

    g.add((correction_uri, RDF.type, REASON.SelfCorrection))
    g.add(
        (
            correction_uri,
            REASON.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((correction_uri, REASON.action, Literal(action)))
    g.add((correction_uri, REASON.reasonForCorrection, Literal(reason_for_correction)))
    g.add((correction_uri, REASON.whatWasWrong, Literal(what_was_wrong)))
    g.add((correction_uri, REASON.correctionMade, Literal(correction_made)))

    save_reasoning_graph(g)

    return str(correction_uri)


def generate_explanation(run_uri: str = None) -> str:
    """Generate natural language explanation from reasoning trace."""
    g = load_reasoning_graph()

    explanations = []

    decisions = list(g.subjects(RDF.type, REASON.Decision))
    corrections = list(g.subjects(RDF.type, REASON.SelfCorrection))

    if decisions:
        explanations.append("## Decision Log\n")
        for decision in decisions[-5:]:
            decision_type = g.value(decision, REASON.decisionType)
            rationale = g.value(decision, REASON.rationale)
            chosen = g.value(decision, REASON.chosenApproach)

            exp = f"- **Type:** {decision_type}\n"
            if chosen:
                exp += f"  - Chosen approach: {chosen}\n"
            exp += f"  - Rationale: {rationale}\n"
            explanations.append(exp)

    if corrections:
        explanations.append("\n## Self-Corrections\n")
        for correction in corrections[-5:]:
            action = g.value(correction, REASON.action)
            wrong = g.value(correction, REASON.whatWasWrong)
            correction_made = g.value(correction, REASON.correctionMade)

            exp = f"- Action: {action}\n"
            exp += f"  - What was wrong: {wrong}\n"
            exp += f"  - Correction: {correction_made}\n"
            explanations.append(exp)

    if not explanations:
        return "No reasoning trace available."

    return "".join(explanations)


def query_reasoning(sparql: str) -> List[Dict[str, Any]]:
    """Query reasoning trace with SPARQL."""
    g = load_reasoning_graph()

    results = []
    for row in g.query(sparql):
        result = {}
        for var in row.labels:
            result[var] = str(row[var]) if row[var] else None
        results.append(result)
    return results


def get_self_corrections(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent self-corrections."""
    g = load_reasoning_graph()

    corrections = []
    for correction in g.subjects(RDF.type, REASON.SelfCorrection):
        data = {
            "timestamp": str(g.value(correction, REASON.timestamp) or ""),
            "action": str(g.value(correction, REASON.action) or ""),
            "reason": str(g.value(correction, REASON.reasonForCorrection) or ""),
            "what_was_wrong": str(g.value(correction, REASON.whatWasWrong) or ""),
            "correction": str(g.value(correction, REASON.correctionMade) or ""),
        }
        corrections.append(data)

    corrections.sort(key=lambda x: x["timestamp"], reverse=True)
    return corrections[:limit]
