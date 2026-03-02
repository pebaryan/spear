"""Retry policy selection helpers for solve-loop strategy decisions."""

from __future__ import annotations

import os
from typing import Any, Dict, List


def get_policy_profile() -> str:
    profile = str(os.getenv("SPEAR_RETRY_POLICY_PROFILE", "standard") or "").strip().lower()
    if profile in {"standard", "aggressive", "conservative", "auto"}:
        return profile
    return "standard"


def classify_failure(error_type: str, output: str = "") -> str:
    normalized = str(error_type or "").strip()
    static_errors = {
        "SyntaxError",
        "IndentationError",
        "ImportError",
        "NameError",
        "FileNotFoundError",
    }
    runtime_errors = {
        "AssertionError",
        "TestFailure",
        "ValueError",
        "TypeError",
        "ZeroDivisionError",
        "IndexError",
        "KeyError",
        "UnknownError",
    }

    if normalized in static_errors:
        return "static"
    if normalized in runtime_errors:
        return "runtime"

    text = str(output or "").lower()
    if "syntaxerror" in text or "indentationerror" in text or "importerror" in text:
        return "static"
    if "assertionerror" in text or "failed" in text:
        return "runtime"
    return "unknown"


def _select_profile_from_stats(
    stats: Dict[str, Dict[str, int]],
    fallback_profile: str = "standard",
) -> str:
    candidates = ["standard", "aggressive", "conservative"]
    best_profile = fallback_profile if fallback_profile in candidates else "standard"
    best_score = float("-inf")

    for profile in candidates:
        row = stats.get(profile, {})
        runs = int(row.get("runs", 0) or 0)
        success = int(row.get("success", 0) or 0)
        if runs <= 0:
            continue
        rate = success / runs
        score = rate + min(runs, 20) * 0.001
        if score > best_score:
            best_score = score
            best_profile = profile
        elif score == best_score:
            # Prefer standard over non-standard when tie remains.
            if best_profile != "standard" and profile == "standard":
                best_profile = profile
    return best_profile


def _infer_profile_from_reports(
    failure_class: str,
    fallback_profile: str = "standard",
) -> Dict[str, Any]:
    stats = {
        "standard": {"runs": 0, "success": 0},
        "aggressive": {"runs": 0, "success": 0},
        "conservative": {"runs": 0, "success": 0},
    }

    try:
        from .run_report import AG, load_report_graph
    except Exception:
        return {
            "profile": fallback_profile,
            "reason": "run_report unavailable; using fallback profile",
            "stats": stats,
        }

    try:
        graph = load_report_graph()
    except Exception:
        return {
            "profile": fallback_profile,
            "reason": "failed to load run report graph; using fallback profile",
            "stats": stats,
        }

    for report in graph.subjects(AG.retryPolicyProfile, None):
        profile_node = graph.value(report, AG.retryPolicyProfile)
        class_node = graph.value(report, AG.retryPolicyClass)
        success_node = graph.value(report, AG.success)
        if not profile_node or not class_node or success_node is None:
            continue
        profile = str(profile_node).strip().lower()
        klass = str(class_node).strip().lower()
        if profile not in stats:
            continue
        if klass != str(failure_class or "").strip().lower():
            continue
        stats[profile]["runs"] += 1
        if str(success_node).strip().lower() == "true":
            stats[profile]["success"] += 1

    selected = _select_profile_from_stats(stats, fallback_profile=fallback_profile)
    total_runs = sum(int(v.get("runs", 0) or 0) for v in stats.values())
    if total_runs == 0:
        reason = (
            f"no historical policy stats for class={failure_class}; "
            f"fallback={fallback_profile}"
        )
    else:
        reason = (
            f"selected {selected} from historical stats for class={failure_class}: "
            f"standard={stats['standard']}, aggressive={stats['aggressive']}, "
            f"conservative={stats['conservative']}"
        )
    return {"profile": selected, "reason": reason, "stats": stats}


def choose_retry_plan(
    *,
    error_type: str,
    output: str,
    attempt: int,
    history: List[Dict[str, Any]] | None = None,
    policy_profile: str = "",
) -> Dict[str, Any]:
    profile = str(policy_profile or get_policy_profile()).strip().lower()
    if profile not in {"standard", "aggressive", "conservative", "auto"}:
        profile = "standard"

    failure_class = classify_failure(error_type, output)
    auto_reason = ""
    auto_stats: Dict[str, Dict[str, int]] = {}
    if profile == "auto":
        inferred = _infer_profile_from_reports(
            failure_class=failure_class,
            fallback_profile="standard",
        )
        profile = str(inferred.get("profile", "standard"))
        auto_reason = str(inferred.get("reason", ""))
        raw_stats = inferred.get("stats", {})
        if isinstance(raw_stats, dict):
            auto_stats = {
                key: value
                for key, value in raw_stats.items()
                if isinstance(value, dict)
            }
    history = history or []
    prior_failures = sum(1 for item in history if not bool(item.get("success")))

    strategy = "llm_fix"
    fallback_max_steps = 4
    llm_enabled = True

    if attempt >= 3:
        strategy = "escalate"
        fallback_max_steps = 8
        llm_enabled = False
    elif profile == "aggressive":
        if failure_class == "static" and attempt >= 0:
            strategy = "different_approach"
            fallback_max_steps = 6
            llm_enabled = False
        elif failure_class == "runtime" and attempt >= 1:
            strategy = "different_approach"
            fallback_max_steps = 6
            llm_enabled = False
    elif profile == "conservative":
        if failure_class == "static" and attempt >= 2:
            strategy = "different_approach"
            fallback_max_steps = 6
            llm_enabled = False
        elif failure_class == "runtime" and attempt >= 3:
            strategy = "escalate"
            fallback_max_steps = 8
            llm_enabled = False
    else:  # standard
        if failure_class == "static" and attempt >= 1:
            strategy = "different_approach"
            fallback_max_steps = 6
            llm_enabled = False
        elif failure_class == "runtime" and attempt >= 2:
            strategy = "different_approach"
            fallback_max_steps = 6
            llm_enabled = False

    rationale = (
        f"profile={profile}, class={failure_class}, attempt={attempt}, "
        f"prior_failures={prior_failures}, strategy={strategy}"
    )
    if auto_reason:
        rationale = f"{rationale}; auto_reason={auto_reason}"

    return {
        "profile": profile,
        "failure_class": failure_class,
        "strategy": strategy,
        "fallback_max_steps": int(fallback_max_steps),
        "llm_enabled": bool(llm_enabled),
        "rationale": rationale,
        "auto_reason": auto_reason,
        "auto_stats": auto_stats,
    }
