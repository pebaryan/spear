"""Handler that analyzes errors and queries RDF for relevant skills/patterns."""

import re
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, URIRef

from .common import TARGET_DIR, PythonTestTool
from .retry_policy import choose_retry_plan, get_policy_profile

AG = Namespace("http://example.org/agent/")
SK = Namespace("http://example.org/skill/")


def parse_error_type(error_output: str) -> str:
    """Extract error type from test output."""
    error_patterns = [
        (r"ImportError", "ImportError"),
        (r"AttributeError", "AttributeError"),
        (r"TypeError", "TypeError"),
        (r"ValueError", "ValueError"),
        (r"NameError", "NameError"),
        (r"SyntaxError", "SyntaxError"),
        (r"IndentationError", "IndentationError"),
        (r"ZeroDivisionError", "ZeroDivisionError"),
        (r"IndexError", "IndexError"),
        (r"KeyError", "KeyError"),
        (r"FileNotFoundError", "FileNotFoundError"),
        (r"AssertionError", "AssertionError"),
        (r"pytest\.failed", "TestFailure"),
    ]
    for pattern, error_type in error_patterns:
        if re.search(pattern, error_output, re.IGNORECASE):
            return error_type
    return "UnknownError"


def query_skills_for_error(error_type: str) -> List[Dict[str, str]]:
    """Query skills RDF for relevant fix patterns."""
    from pathlib import Path

    skills_path = Path(__file__).resolve().parent.parent / "skills.ttl"
    g = Graph()
    if skills_path.exists():
        g.parse(skills_path, format="turtle")

    results = []
    for skill in g.subjects(RDF.type, SK.Skill):
        skill_type = g.value(skill, SK.appliesTo)
        if skill_type and error_type.lower() in str(skill_type).lower():
            results.append(
                {
                    "uri": str(skill),
                    "title": str(g.value(skill, SK.title) or ""),
                    "description": str(g.value(skill, SK.description) or ""),
                    "patterns": str(g.value(skill, SK.patterns) or ""),
                }
            )
    return results


def query_history_for_similar_errors(
    error_type: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """Query session history for similar errors and what worked."""
    from pathlib import Path

    history_path = Path(__file__).resolve().parent.parent / "session_history.ttl"
    g = Graph()
    if history_path.exists():
        g.parse(history_path, format="turtle")

    query = f"""
    PREFIX ag: <http://example.org/agent/>
    PREFIX proc: <http://example.org/process/>
    SELECT ?run ?task ?success ?errorType ?outputSummary
    WHERE {{
        ?run a ag:Run .
        ?run ag:command "solve" .
        ?run ag:success ?success .
        ?run ag:task ?task .
        OPTIONAL {{ ?run ag:errorType ?errorType }}
        OPTIONAL {{ ?run ag:outputSummary ?outputSummary }}
    }}
    ORDER BY DESC(?run)
    LIMIT {limit}
    """
    results = g.query(query)
    return [
        {
            "run": str(row.run),
            "task": str(row.task),
            "success": str(row.success) == "true" if row.success else False,
            "error_type": str(row.errorType) if row.errorType else None,
            "summary": str(row.outputSummary)[:200] if row.outputSummary else "",
        }
        for row in results
    ]


def get_retry_strategy(history: List[Dict], attempt: int) -> str:
    """Query RDF to determine best retry strategy based on history."""
    if not history:
        return "llm_fix"

    failed_strategies = set()
    successful_strategies = set()

    for entry in history:
        if not entry.get("success"):
            failed_strategies.add(entry.get("error_type", "unknown"))
        else:
            successful_strategies.add(entry.get("error_type", "unknown"))

    if attempt >= 3:
        return "escalate"
    elif attempt >= 2:
        return "different_approach"
    else:
        return "llm_fix"


def handle(context) -> None:
    """Analyze error and query RDF for relevant skills and history."""
    result = PythonTestTool.run_tests(TARGET_DIR)
    output = result["output"]
    exit_code = result["exit_code"]

    context.set_variable("before_exit_code", exit_code)
    context.set_variable("before_output", output)

    if exit_code == "0":
        context.set_variable("error_analysis", "no_error")
        context.set_variable("error_type", "None")
        context.set_variable("relevant_skills", "[]")
        context.set_variable("similar_history", "[]")
        context.set_variable("chosen_strategy", "none_needed")
        context.set_variable("success", "true")
        context.set_variable("repair_success", "true")
        context.set_variable("repair_exit_code", "0")
        context.set_variable("repair_output", output)
        context.set_variable("patch_applied", "false")
        context.set_variable("repair_steps_json", "[]")
        return

    error_type = parse_error_type(output)
    context.set_variable("error_type", error_type)

    skills = query_skills_for_error(error_type)
    skills_json = str(skills) if skills else "[]"
    context.set_variable("relevant_skills", skills_json)

    history = query_history_for_similar_errors(error_type)
    history_json = str(history)[:500] if history else "[]"
    context.set_variable("similar_history", history_json)

    attempt = context.get_variable("retry_count")
    if attempt is None:
        attempt = "0"
    try:
        attempt_num = int(attempt)
    except (ValueError, TypeError):
        attempt_num = 0

    requested_policy_profile = get_policy_profile()
    plan = choose_retry_plan(
        error_type=error_type,
        output=output,
        attempt=attempt_num,
        history=history,
        policy_profile=requested_policy_profile,
    )
    strategy = str(plan.get("strategy", "llm_fix"))
    context.set_variable("chosen_strategy", strategy)
    context.set_variable("retry_policy_requested", requested_policy_profile)
    context.set_variable("retry_policy_profile", str(plan.get("profile", requested_policy_profile)))
    context.set_variable("retry_policy_class", str(plan.get("failure_class", "unknown")))
    context.set_variable("retry_policy_rationale", str(plan.get("rationale", "")))
    context.set_variable("retry_policy_auto_reason", str(plan.get("auto_reason", "")))
    context.set_variable("fallback_max_steps", str(plan.get("fallback_max_steps", 4)))
    context.set_variable(
        "llm_enabled",
        "true" if bool(plan.get("llm_enabled", True)) else "false",
    )

    context.set_variable(
        "error_analysis",
        (
            f"Error type: {error_type}, Skills found: {len(skills)}, "
            f"History: {len(history)} entries, Strategy: {strategy}, "
            f"Policy: {plan.get('profile', requested_policy_profile)}"
        ),
    )
