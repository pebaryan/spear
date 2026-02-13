"""Self-introspective explanation engine for the coding agent.

This module generates natural language explanations from provenance data,
enabling the agent to explain its decisions and actions.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

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

    return graphs


def explain_last_run() -> str:
    """Generate a natural language explanation of the last run."""
    graphs = _load_all_graphs()

    if "reports" not in graphs:
        return "No run data available."

    g = graphs["reports"]

    reports = list(g.subjects(RDF.type, AG.RunReport))
    if not reports:
        return "No reports found."

    latest_report = sorted(reports, key=lambda x: str(x))[-1]

    parts = []

    task = g.value(latest_report, AG.task)
    build_task = g.value(latest_report, AG.buildTask)
    command = g.value(latest_report, AG.command)

    if command:
        parts.append(f"## Last Run: {command} mode")

    if task:
        parts.append(f"**Task:** {task}")
    elif build_task:
        parts.append(f"**Task:** {build_task}")

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
        interactions = list(llm_g.subjects(RDF.type, LLM.BuildInteraction))
        if not interactions:
            interactions = list(llm_g.subjects(RDF.type, LLM.FixInteraction))

        if interactions:
            latest = sorted(interactions, key=lambda x: str(x))[-1]
            prompt = g.value(latest, LLM.prompt)
            response = g.value(latest, LLM.response)

            if prompt:
                parts.append(f"\n### LLM Prompt:\n{prompt[:300]}...")
            if response:
                parts.append(
                    f"\n### LLM Response (first 300 chars):\n{response[:300]}..."
                )

    if "artifacts" in graphs:
        art_g = graphs["artifacts"]
        artifacts = list(art_g.subjects(RDF.type, ART.Artifact))

        if artifacts:
            parts.append("\n### Files Changed:")
            for artifact in artifacts[-5:]:
                path = art_g.value(artifact, ART.filePath)
                operation = art_g.value(artifact, ART.operation)
                if path and operation:
                    parts.append(f"- {path}: {operation}")

    if "reasoning" in graphs:
        reason_g = graphs["reasoning"]
        decisions = list(reason_g.subjects(RDF.type, REASON.Decision))

        if decisions:
            parts.append("\n### Reasoning:")
            for decision in decisions[-3:]:
                dtype = reason_g.value(decision, REASON.decisionType)
                rationale = reason_g.value(decision, REASON.rationale)
                if dtype and rationale:
                    parts.append(f"- {dtype}: {rationale}")

    return "\n".join(parts)


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
                parts.append(f"**Failure Summary:** {failure_summary}")

            if "llm" in graphs:
                llm_g = graphs["llm"]
                for interaction in llm_g.subjects(RDF.type, LLM.FixInteraction):
                    prompt = llm_g.value(interaction, LLM.prompt)
                    if prompt:
                        parts.append(f"\n**Fix Prompt:**\n{prompt[:500]}")

    if not parts:
        return "No failure data available."

    return "\n".join(parts)


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
                parts.append(f"I modified: {path}")
            if preview:
                parts.append(f"Changed content (preview): {preview[:200]}")

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
                    parts.append(f"- *{dtype}*")
                if rationale:
                    parts.append(f"  Rationale: {rationale}")
                if chosen:
                    parts.append(f"  Chose: {chosen}")

    if len(parts) == 1:
        return "No 'why' explanation available. I haven't recorded my reasoning yet."

    return "\n".join(parts)


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
                if path:
                    parts.append(f"- {path} ({operation})")

    parts.append("\n### To perform actual what-if analysis:")
    parts.append("1. Clone current state")
    parts.append("2. Apply hypothetical change")
    parts.append("3. Run tests to see impact")
    parts.append("4. Compare results")

    return "\n".join(parts)


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
                    parts.append(f"- {action}: {wrong if wrong else ''}")

    if len(parts) == 1:
        return "Not enough data for self-reflection yet."

    return "\n".join(parts)


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

    prompt = f"""You are a self-introspective coding agent. Given the provenance data ({context}), answer the user's question.

User Question: {query}

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

    return response["choices"][0]["message"]["content"].strip()
