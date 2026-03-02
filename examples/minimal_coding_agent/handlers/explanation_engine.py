"""Self-introspective explanation engine for the coding agent.

This module generates natural language explanations from provenance data,
enabling the agent to explain its decisions and actions.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

from .redaction import redact_text

try:
    from dotenv import load_dotenv

    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except Exception:
    pass

try:
    from litellm import completion
except Exception:
    completion = None


BASE_DIR = Path(__file__).resolve().parent.parent

AG = Namespace("http://example.org/agent/")
REASON = Namespace("http://example.org/reasoning/")
LLM = Namespace("http://example.org/llm/")
ART = Namespace("http://example.org/artifact/")
APPROVAL = Namespace("http://example.org/approval/")


def _latest_subject_by_timestamp(g: Graph, rdf_type: URIRef, ts_pred: URIRef):
    latest = None
    latest_ts = ""
    for subject in g.subjects(RDF.type, rdf_type):
        ts = str(g.value(subject, ts_pred) or "")
        if ts > latest_ts:
            latest_ts = ts
            latest = subject
    return latest


def _parse_iso(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _filter_subjects_by_run_id(
    g: Graph, subjects: List[URIRef], run_id: str, predicates: List[URIRef]
) -> List[URIRef]:
    if not run_id:
        return subjects
    filtered: List[URIRef] = []
    for subject in subjects:
        for predicate in predicates:
            value = g.value(subject, predicate)
            if value and str(value) == run_id:
                filtered.append(subject)
                break
    return filtered


def _load_all_graphs() -> Dict[str, Graph]:
    """Load all provenance graphs."""
    graphs = {}

    session_path = BASE_DIR / "session_history.ttl"
    if session_path.exists():
        g = Graph()
        g.parse(session_path, format="turtle")
        graphs["session"] = g

    reports_path = BASE_DIR / "run_reports.ttl"
    if reports_path.exists():
        g = Graph()
        g.parse(reports_path, format="turtle")
        graphs["reports"] = g

    llm_path = BASE_DIR / "llm_interactions.ttl"
    if llm_path.exists():
        g = Graph()
        g.parse(llm_path, format="turtle")
        graphs["llm"] = g

    artifact_path = BASE_DIR / "artifact_changes.ttl"
    if artifact_path.exists():
        g = Graph()
        g.parse(artifact_path, format="turtle")
        graphs["artifacts"] = g

    reasoning_path = BASE_DIR / "reasoning_trace.ttl"
    if reasoning_path.exists():
        g = Graph()
        g.parse(reasoning_path, format="turtle")
        graphs["reasoning"] = g

    approval_path = BASE_DIR / "approval_events.ttl"
    if approval_path.exists():
        g = Graph()
        g.parse(approval_path, format="turtle")
        graphs["approval"] = g

    return graphs


def explain_last_run(run_id: Optional[str] = None) -> str:
    """Generate a natural language explanation of the last run."""
    graphs = _load_all_graphs()

    if "reports" not in graphs:
        return "No run data available."

    g = graphs["reports"]

    reports = list(g.subjects(RDF.type, AG.RunReport))
    if not reports:
        return "No reports found."
    if run_id:
        reports = _filter_subjects_by_run_id(g, reports, run_id, [AG.runId])
        if not reports:
            return redact_text(f"No report found for run_id={run_id}.")

    latest_report = max(
        reports, key=lambda x: str(g.value(x, AG.timestamp) or "")
    )

    parts = []

    task = g.value(latest_report, AG.task)
    build_task = g.value(latest_report, AG.buildTask)
    command = g.value(latest_report, AG.command)
    report_timestamp = str(g.value(latest_report, AG.timestamp) or "")
    report_run_id = str(g.value(latest_report, AG.runId) or run_id or "")

    if command:
        parts.append(f"## Last Run: {command} mode")
    if report_run_id:
        parts.append(f"**Run ID:** {report_run_id}")

    if task:
        parts.append(f"**Task:** {redact_text(str(task))}")
    elif build_task:
        parts.append(f"**Task:** {redact_text(str(build_task))}")

    success = g.value(latest_report, AG.success)
    build_success = g.value(latest_report, AG.buildSuccess)

    if success:
        outcome = str(success).lower() == "true"
    elif build_success:
        outcome = str(build_success).lower() == "true"
    else:
        outcome = False

    if outcome:
        parts.append("\n### Outcome: SUCCESS\nThe task completed successfully.")
    else:
        parts.append("\n### Outcome: FAILED\nThe task did not complete successfully.")

    if "llm" in graphs:
        llm_g = graphs["llm"]
        command_text = str(command) if command else ""
        if command_text == "solve":
            interactions = list(llm_g.subjects(RDF.type, LLM.FixInteraction))
        elif command_text == "build":
            interactions = list(llm_g.subjects(RDF.type, LLM.BuildInteraction))
        else:
            interactions = list(llm_g.subjects(RDF.type, LLM.BuildInteraction))
            interactions.extend(list(llm_g.subjects(RDF.type, LLM.FixInteraction)))

        if interactions:
            if report_run_id:
                eligible = _filter_subjects_by_run_id(
                    llm_g, interactions, report_run_id, [LLM.runId]
                )
            else:
                eligible = []
                for item in interactions:
                    ts = str(llm_g.value(item, LLM.timestamp) or "")
                    if not report_timestamp or ts <= report_timestamp:
                        eligible.append(item)
            if eligible:
                latest = max(
                    eligible, key=lambda x: str(llm_g.value(x, LLM.timestamp) or "")
                )
            else:
                latest = None

            prompt = None
            response = None
            if latest:
                latest_ts = str(llm_g.value(latest, LLM.timestamp) or "")
                report_dt = _parse_iso(report_timestamp)
                latest_dt = _parse_iso(latest_ts)
                is_relevant = True
                if report_dt and latest_dt:
                    # Keep only interactions close to this run.
                    is_relevant = abs((report_dt - latest_dt).total_seconds()) <= 180
                if is_relevant:
                    prompt = llm_g.value(latest, LLM.prompt)
                    response = llm_g.value(latest, LLM.response)

            if prompt:
                parts.append(f"\n### LLM Prompt:\n{redact_text(str(prompt)[:300])}...")
            if response:
                parts.append(
                    f"\n### LLM Response (first 300 chars):\n"
                    f"{redact_text(str(response)[:300])}..."
                )

    if "artifacts" in graphs:
        art_g = graphs["artifacts"]
        artifacts = list(art_g.subjects(RDF.type, ART.Artifact))
        if report_run_id:
            artifacts = _filter_subjects_by_run_id(
                art_g, artifacts, report_run_id, [ART.runId]
            )

        if artifacts:
            artifacts = sorted(
                artifacts, key=lambda x: str(art_g.value(x, ART.timestamp) or "")
            )
            parts.append("\n### Files Changed:")
            for artifact in artifacts[-5:]:
                path = art_g.value(artifact, ART.filePath)
                operation = art_g.value(artifact, ART.operation)
                lines_added = art_g.value(artifact, ART.linesAdded)
                lines_removed = art_g.value(artifact, ART.linesRemoved)
                if path and operation:
                    delta = ""
                    if lines_added is not None or lines_removed is not None:
                        plus = int(lines_added) if lines_added is not None else 0
                        minus = int(lines_removed) if lines_removed is not None else 0
                        delta = f" (+{plus}/-{minus})"
                    parts.append(
                        f"- {redact_text(str(path))}: "
                        f"{redact_text(str(operation))}{delta}"
                    )

    if "reasoning" in graphs:
        reason_g = graphs["reasoning"]
        decisions = list(reason_g.subjects(RDF.type, REASON.Decision))
        if report_run_id:
            decisions = _filter_subjects_by_run_id(
                reason_g, decisions, report_run_id, [REASON.run_id, REASON.runId]
            )

        if decisions:
            decisions = sorted(
                decisions,
                key=lambda x: str(reason_g.value(x, REASON.timestamp) or ""),
            )
            parts.append("\n### Reasoning:")
            for decision in decisions[-3:]:
                dtype = reason_g.value(decision, REASON.decisionType)
                rationale = reason_g.value(decision, REASON.rationale)
                if dtype and rationale:
                    parts.append(
                        f"- {redact_text(str(dtype))}: {redact_text(str(rationale))}"
                    )

    if "approval" in graphs:
        approval_g = graphs["approval"]
        events = list(approval_g.subjects(RDF.type, APPROVAL.Event))
        if report_run_id:
            events = _filter_subjects_by_run_id(
                approval_g, events, report_run_id, [APPROVAL.runId]
            )
        if events:
            events = sorted(
                events,
                key=lambda x: str(approval_g.value(x, APPROVAL.timestamp) or ""),
            )
            parts.append("\n### Approvals:")
            for event in events[-5:]:
                action = approval_g.value(event, APPROVAL.action)
                decision = approval_g.value(event, APPROVAL.decision)
                risk = approval_g.value(event, APPROVAL.riskLevel)
                mode = approval_g.value(event, APPROVAL.mode)
                actor = approval_g.value(event, APPROVAL.actor)
                policy_min = approval_g.value(event, APPROVAL.policyMinRisk)
                authz_provider = approval_g.value(event, APPROVAL.authzProvider)
                authz_decision = approval_g.value(event, APPROVAL.authzDecisionId)
                if action and decision:
                    summary = (
                        f"- {redact_text(str(action))}: {redact_text(str(decision))} "
                        f"(risk={redact_text(str(risk or 'unknown'))}, "
                        f"mode={redact_text(str(mode or 'n/a'))}, "
                        f"actor={redact_text(str(actor or 'n/a'))}, "
                        f"policy_min={redact_text(str(policy_min or 'n/a'))}, "
                        f"authz={redact_text(str(authz_provider or 'n/a'))}, "
                        f"authz_id={redact_text(str(authz_decision or 'n/a'))})"
                    )
                    parts.append(summary)

    return redact_text("\n".join(parts))


def explain_failure(file_path: str = None) -> str:
    """Explain why a failure occurred."""
    graphs = _load_all_graphs()

    parts = ["## Failure Analysis\n"]

    if "reports" in graphs:
        g = graphs["reports"]

        failed_reports = []
        for report in g.subjects(RDF.type, AG.RunReport):
            success = g.value(report, AG.success)
            build_success = g.value(report, AG.buildSuccess)

            is_failed = False
            if success:
                is_failed = str(success).lower() == "false"
            elif build_success:
                is_failed = str(build_success).lower() == "false"

            if is_failed:
                failed_reports.append(report)

        if failed_reports:
            latest = sorted(failed_reports, key=lambda x: str(x))[-1]

            failure_summary = g.value(latest, AG.failureSummary)
            if failure_summary:
                parts.append(f"**Failure Summary:** {redact_text(str(failure_summary))}")

            if "llm" in graphs:
                llm_g = graphs["llm"]
                for interaction in llm_g.subjects(RDF.type, LLM.FixInteraction):
                    prompt = llm_g.value(interaction, LLM.prompt)
                    if prompt:
                        parts.append(f"\n**Fix Prompt:**\n{redact_text(str(prompt)[:500])}")

    if not parts:
        return "No failure data available."

    return redact_text("\n".join(parts))


def generate_why_explanation(artifact_uri: str = None) -> str:
    """Generate 'why' explanation - why did I make this change?"""
    graphs = _load_all_graphs()

    parts = ["## Why Explanation\n"]

    if "artifacts" in graphs and artifact_uri:
        g = graphs["artifacts"]

        artifact = URIRef(artifact_uri) if artifact_uri else None
        if artifact:
            path = g.value(artifact, ART.filePath)
            operation = g.value(artifact, ART.operation)
            preview = g.value(artifact, ART.contentPreview)

            if path:
                parts.append(f"I modified: {redact_text(str(path))}")
            if preview:
                parts.append(f"Changed content (preview): {redact_text(str(preview)[:200])}")

    if "reasoning" in graphs:
        g = graphs["reasoning"]
        decisions = list(g.subjects(RDF.type, REASON.Decision))

        if decisions:
            parts.append("\n### My Decision Process:")
            for decision in decisions[-3:]:
                dtype = g.value(decision, REASON.decisionType)
                rationale = g.value(decision, REASON.rationale)
                chosen = g.value(decision, REASON.chosenApproach)

                if dtype:
                    parts.append(f"- *{redact_text(str(dtype))}*")
                if rationale:
                    parts.append(f"  Rationale: {redact_text(str(rationale))}")
                if chosen:
                    parts.append(f"  Chose: {redact_text(str(chosen))}")

    if len(parts) == 1:
        return "No 'why' explanation available. I haven't recorded my reasoning yet."

    return redact_text("\n".join(parts))


def generate_what_if_scaffold(action_uri: str = None) -> str:
    """Generate what-if scaffold - what would happen if I did X?"""
    graphs = _load_all_graphs()

    parts = ["## What-If Analysis Scaffold\n"]

    parts.append("To analyze 'what-if' scenarios, I examine:")
    parts.append("1. **Artifacts**: What files would be affected?")
    parts.append("2. **Dependencies**: What other parts depend on this?")
    parts.append("3. **Tests**: Which tests would validate the change?")

    if "artifacts" in graphs:
        g = graphs["artifacts"]
        artifacts = list(g.subjects(RDF.type, ART.Artifact))

        if artifacts:
            parts.append("\n### Recent Artifacts:")
            for artifact in artifacts[-5:]:
                path = g.value(artifact, ART.filePath)
                operation = g.value(artifact, ART.operation)
                lines_added = g.value(artifact, ART.linesAdded)
                lines_removed = g.value(artifact, ART.linesRemoved)
                if path:
                    delta = ""
                    if lines_added is not None or lines_removed is not None:
                        plus = int(lines_added) if lines_added is not None else 0
                        minus = int(lines_removed) if lines_removed is not None else 0
                        delta = f" (+{plus}/-{minus})"
                    parts.append(
                        f"- {redact_text(str(path))} "
                        f"({redact_text(str(operation))}{delta})"
                    )

    parts.append("\n### To perform actual what-if analysis:")
    parts.append("1. Clone current state")
    parts.append("2. Apply hypothetical change")
    parts.append("3. Run tests to see impact")
    parts.append("4. Compare results")

    return redact_text("\n".join(parts))


def generate_reflection() -> str:
    """Generate self-reflection on past runs."""
    graphs = _load_all_graphs()

    parts = ["## Self-Reflection\n"]

    if "session" in graphs:
        g = graphs["session"]

        runs = list(g.subjects(RDF.type, AG.Run))

        if runs:
            success_count = 0
            fail_count = 0

            for run in runs:
                success = g.value(run, AG.success)
                if success:
                    if str(success).lower() == "true":
                        success_count += 1
                    else:
                        fail_count += 1

            total = success_count + fail_count
            if total > 0:
                success_rate = (success_count / total) * 100
                parts.append(
                    f"**Overall Success Rate:** {success_rate:.1f}% ({success_count}/{total} runs)"
                )

                if success_rate < 50:
                    parts.append("\n### Areas for Improvement:")
                    parts.append("- Success rate is below 50%. Consider:")
                    parts.append("  1. Simplifying tasks")
                    parts.append("  2. Adding more test cases")
                    parts.append("  3. Breaking down complex problems")

    if "reasoning" in graphs:
        g = graphs["reasoning"]
        corrections = list(g.subjects(RDF.type, REASON.SelfCorrection))

        if corrections:
            parts.append(f"\n### Self-Corrections Made: {len(corrections)}")
            for correction in corrections[-3:]:
                action = g.value(correction, REASON.action)
                wrong = g.value(correction, REASON.whatWasWrong)
                if action:
                    wrong_text = redact_text(str(wrong)) if wrong else ""
                    parts.append(f"- {redact_text(str(action))}: {wrong_text}")

    if len(parts) == 1:
        return "Not enough data for self-reflection yet."

    return redact_text("\n".join(parts))


def llm_generate_explanation(query: str) -> str:
    """Use LLM to generate explanation from all provenance data."""
    if completion is None:
        return "LLM not available. Use text-based explanations instead."

    graphs = _load_all_graphs()

    context_parts = []

    if "session" in graphs:
        g = graphs["session"]
        runs = list(g.subjects(RDF.type, AG.Run))
        if runs:
            context_parts.append(f"Session history: {len(runs)} runs recorded")

    if "reports" in graphs:
        g = graphs["reports"]
        reports = list(g.subjects(RDF.type, AG.RunReport))
        if reports:
            context_parts.append(f"Run reports: {len(reports)} reports")

    if "llm" in graphs:
        g = graphs["llm"]
        interactions = list(g.subjects(RDF.type, LLM.BuildInteraction))
        interactions += list(g.subjects(RDF.type, LLM.FixInteraction))
        if interactions:
            context_parts.append(f"LLM interactions: {len(interactions)} calls")

    if "artifacts" in graphs:
        g = graphs["artifacts"]
        artifacts = list(g.subjects(RDF.type, ART.Artifact))
        if artifacts:
            context_parts.append(f"Artifacts: {len(artifacts)} file changes")

    if "reasoning" in graphs:
        g = graphs["reasoning"]
        decisions = list(g.subjects(RDF.type, REASON.Decision))
        if decisions:
            context_parts.append(f"Reasoning: {len(decisions)} decisions logged")

    context = "; ".join(context_parts)

    safe_query = redact_text(query)
    prompt = f"""You are a self-introspective coding agent. Given the provenance data ({context}), answer the user's question.

User Question: {safe_query}

Provide a thoughtful, detailed explanation that shows your reasoning process. Include relevant details from your execution history if available."""

    model = os.getenv("LITELLM_MODEL", "gpt-4o")
    provider = os.getenv("LITELLM_PROVIDER")
    api_key = os.getenv("LITELLM_API_KEY")
    api_base = os.getenv("LITELLM_API_BASE")

    if provider and "/" not in model:
        model = f"{provider}/{model}"

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        api_base=api_base,
        api_key=api_key,
    )

    return redact_text(response["choices"][0]["message"]["content"].strip())
