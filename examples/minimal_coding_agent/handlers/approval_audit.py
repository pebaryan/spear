"""RDF audit log for approval-gated actions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, XSD

from .redaction import redact_object, redact_text

BASE_DIR = Path(__file__).resolve().parent.parent
APPROVAL_GRAPH_PATH = BASE_DIR / "approval_events.ttl"

APPROVAL = Namespace("http://example.org/approval/")

_namespaces = {
    "approval": APPROVAL,
    "rdf": RDF,
    "xsd": XSD,
}


def _create_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_approval_graph() -> Graph:
    g = _create_graph()
    if APPROVAL_GRAPH_PATH.exists():
        g.parse(APPROVAL_GRAPH_PATH, format="turtle")
    return g


def save_approval_graph(g: Graph) -> None:
    g.serialize(APPROVAL_GRAPH_PATH, format="turtle")


def _event_count(g: Graph) -> int:
    return sum(1 for _ in g.subjects(RDF.type, APPROVAL.Event))


def log_approval_event(
    *,
    action: str,
    decision: str,
    risk_level: str,
    rationale: str = "",
    mode: str = "",
    tool_name: str = "",
    run_id: str = "",
    actor: str = "",
    policy_min_risk: str = "",
    authz_provider: str = "",
    authz_decision_id: str = "",
    authz_policy_id: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> str:
    g = load_approval_graph()
    event_id = _event_count(g)
    uri = APPROVAL[f"event/{event_id}"]

    safe_details = redact_object(details or {})
    g.add((uri, RDF.type, APPROVAL.Event))
    g.add((uri, APPROVAL.timestamp, Literal(datetime.now().isoformat(), datatype=XSD.dateTime)))
    g.add((uri, APPROVAL.action, Literal(redact_text(action))))
    g.add((uri, APPROVAL.decision, Literal(redact_text(decision))))
    g.add((uri, APPROVAL.riskLevel, Literal(redact_text(risk_level))))
    if rationale:
        g.add((uri, APPROVAL.rationale, Literal(redact_text(rationale))))
    if mode:
        g.add((uri, APPROVAL.mode, Literal(redact_text(mode))))
    if tool_name:
        g.add((uri, APPROVAL.toolName, Literal(redact_text(tool_name))))
    if run_id:
        g.add((uri, APPROVAL.runId, Literal(redact_text(run_id))))
    if actor:
        g.add((uri, APPROVAL.actor, Literal(redact_text(actor))))
    if policy_min_risk:
        g.add((uri, APPROVAL.policyMinRisk, Literal(redact_text(policy_min_risk))))
    if authz_provider:
        g.add((uri, APPROVAL.authzProvider, Literal(redact_text(authz_provider))))
    if authz_decision_id:
        g.add((uri, APPROVAL.authzDecisionId, Literal(redact_text(authz_decision_id))))
    if authz_policy_id:
        g.add((uri, APPROVAL.authzPolicyId, Literal(redact_text(authz_policy_id))))
    if safe_details:
        payload = json.dumps(safe_details)
        if len(payload) > 2000:
            payload = payload[:2000] + "... [truncated]"
        g.add((uri, APPROVAL.details, Literal(payload)))

    save_approval_graph(g)
    return str(uri)


def get_approval_events(limit: int = 20, run_id: str = "") -> List[Dict[str, Any]]:
    g = load_approval_graph()
    events: List[Dict[str, Any]] = []
    for event in g.subjects(RDF.type, APPROVAL.Event):
        if run_id:
            value = g.value(event, APPROVAL.runId)
            if not value or str(value) != run_id:
                continue
        row = {
            "uri": str(event),
            "timestamp": str(g.value(event, APPROVAL.timestamp) or ""),
            "action": str(g.value(event, APPROVAL.action) or ""),
            "decision": str(g.value(event, APPROVAL.decision) or ""),
            "risk_level": str(g.value(event, APPROVAL.riskLevel) or ""),
            "rationale": str(g.value(event, APPROVAL.rationale) or ""),
            "mode": str(g.value(event, APPROVAL.mode) or ""),
            "tool_name": str(g.value(event, APPROVAL.toolName) or ""),
            "run_id": str(g.value(event, APPROVAL.runId) or ""),
            "actor": str(g.value(event, APPROVAL.actor) or ""),
            "policy_min_risk": str(g.value(event, APPROVAL.policyMinRisk) or ""),
            "authz_provider": str(g.value(event, APPROVAL.authzProvider) or ""),
            "authz_decision_id": str(g.value(event, APPROVAL.authzDecisionId) or ""),
            "authz_policy_id": str(g.value(event, APPROVAL.authzPolicyId) or ""),
            "details": str(g.value(event, APPROVAL.details) or ""),
        }
        events.append(redact_object(row))
    events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return events[:limit]
