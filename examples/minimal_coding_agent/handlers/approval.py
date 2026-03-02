"""Human-in-the-loop approval helpers for risky tool actions."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .approval_audit import log_approval_event
from .authorization import authorize_approval

RISK_LEVELS = {"low": 1, "medium": 2, "high": 3}


def _is_enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def approvals_required() -> bool:
    return _is_enabled(os.getenv("SPEAR_REQUIRE_APPROVALS", ""))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _is_enabled(str(value))


def _normalize_risk(value: str) -> str:
    risk = str(value or "").strip().lower()
    if risk in RISK_LEVELS:
        return risk
    return "medium"


def _approval_min_risk(action: str, args: Dict[str, Any]) -> str:
    action_name = str(action or "").strip().lower()
    action_key = re.sub(r"[^a-z0-9]+", "_", action_name).upper()

    if (args or {}).get("approval_min_risk"):
        return _normalize_risk(str((args or {}).get("approval_min_risk", "")))

    specific = os.getenv(f"SPEAR_APPROVAL_MIN_RISK_{action_key}", "").strip()
    if specific:
        return _normalize_risk(specific)

    default_value = os.getenv("SPEAR_APPROVAL_MIN_RISK", "medium")
    return _normalize_risk(default_value)


def _risk_requires_approval(risk_level: str, min_risk: str) -> bool:
    risk_rank = RISK_LEVELS.get(_normalize_risk(risk_level), 2)
    min_rank = RISK_LEVELS.get(_normalize_risk(min_risk), 2)
    return risk_rank >= min_rank


def classify_write_file_risk(
    file_path: Path, target_dir: Path, existed: bool, changed: bool
) -> Tuple[str, str]:
    """Return (risk_level, rationale) for a file write operation."""
    resolved = file_path.resolve()
    target_resolved = target_dir.resolve()
    in_target = resolved == target_resolved or target_resolved in resolved.parents

    if not in_target:
        return ("high", "Write is outside target_project")
    if existed and changed:
        return ("medium", "Overwriting existing file in target_project")
    return ("low", "Creating or idempotent write in target_project")


def classify_shell_risk(command: str) -> Tuple[str, str]:
    """Return (risk_level, rationale) for a shell command."""
    text = str(command or "").strip().lower()
    if not text:
        return ("low", "No command")

    high_patterns = [
        r"\brm\s+-",
        r"\bdel\s+",
        r"\bremove-item\b",
        r"\bgit\s+reset\b",
        r"\bgit\s+clean\b",
        r"\bformat\s+[a-z]:",
        r"\bshutdown\b",
        r"\brestart-computer\b",
    ]
    for pattern in high_patterns:
        if re.search(pattern, text):
            return ("high", f"Matched risky pattern: {pattern}")

    medium_patterns = [
        r"\bmv\b",
        r"\bmove-item\b",
        r"\bcp\b",
        r"\bcopy-item\b",
        r"\brename-item\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\bpip\s+install\b",
        r"\bgit\s+commit\b",
        r"\bgit\s+push\b",
    ]
    for pattern in medium_patterns:
        if re.search(pattern, text):
            return ("medium", f"Matched medium-risk pattern: {pattern}")

    return ("low", "Read/test-like command")


def approval_required_response(
    *,
    action: str,
    risk_level: str,
    rationale: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": f"Approval required for {action} ({risk_level} risk): {rationale}",
        "approval_required": True,
        "action": action,
        "risk_level": risk_level,
        "rationale": rationale,
    }
    if details:
        payload["details"] = details
    return payload


def enforce_approval_if_needed(
    *,
    action: str,
    risk_level: str,
    rationale: str,
    args: Dict[str, Any],
    details: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return approval-required response if gate blocks, else None."""
    mode = str((args or {}).get("_approval_mode", ""))
    run_id = str((args or {}).get("run_id", ""))
    tool_name = str((args or {}).get("tool_name", ""))
    actor = (
        str((args or {}).get("approval_user", "")).strip()
        or os.getenv("SPEAR_APPROVAL_USER", "").strip()
    )
    if not approvals_required():
        return None
    min_risk = _approval_min_risk(action, args or {})
    if not _risk_requires_approval(risk_level, min_risk):
        return None
    if _as_bool((args or {}).get("approved")):
        authz = authorize_approval(
            actor=actor,
            action=action,
            risk_level=risk_level,
            rationale=rationale,
            tool_name=tool_name,
            run_id=run_id,
            details=details or {},
        )
        actor = str(authz.get("actor", actor) or actor)
        if not bool(authz.get("allowed")):
            deny_details = dict(details or {})
            deny_details["authz_provider"] = str(authz.get("provider", ""))
            deny_details["authz_reason"] = str(authz.get("reason", ""))
            if authz.get("decision_id"):
                deny_details["authz_decision_id"] = str(authz.get("decision_id"))
            if authz.get("policy_id"):
                deny_details["authz_policy_id"] = str(authz.get("policy_id"))
            log_approval_event(
                action=action,
                decision="denied",
                risk_level=risk_level,
                rationale=f"External authorization denied: {authz.get('reason', '')}",
                mode=mode or "explicit",
                run_id=run_id,
                tool_name=tool_name,
                actor=actor,
                policy_min_risk=min_risk,
                authz_provider=str(authz.get("provider", "")),
                authz_decision_id=str(authz.get("decision_id", "")),
                authz_policy_id=str(authz.get("policy_id", "")),
                details=deny_details,
            )
            return {
                "error": f"Approval denied by authorization provider: {authz.get('reason', '')}",
                "approval_denied": True,
                "action": action,
                "risk_level": risk_level,
                "rationale": rationale,
                "details": deny_details,
            }

        approved_details = dict(details or {})
        approved_details["authz_provider"] = str(authz.get("provider", ""))
        if authz.get("reason"):
            approved_details["authz_reason"] = str(authz.get("reason"))
        if authz.get("decision_id"):
            approved_details["authz_decision_id"] = str(authz.get("decision_id"))
        if authz.get("policy_id"):
            approved_details["authz_policy_id"] = str(authz.get("policy_id"))
        log_approval_event(
            action=action,
            decision="approved",
            risk_level=risk_level,
            rationale=rationale,
            mode=mode or "explicit",
            run_id=run_id,
            tool_name=tool_name,
            actor=actor,
            policy_min_risk=min_risk,
            authz_provider=str(authz.get("provider", "")),
            authz_decision_id=str(authz.get("decision_id", "")),
            authz_policy_id=str(authz.get("policy_id", "")),
            details=approved_details,
        )
        return None
    log_approval_event(
        action=action,
        decision="requested",
        risk_level=risk_level,
        rationale=rationale,
        mode=mode or "required",
        run_id=run_id,
        tool_name=tool_name,
        actor=actor,
        policy_min_risk=min_risk,
        details=details,
    )
    response_details = dict(details or {})
    response_details["policy_min_risk"] = min_risk
    response_details["actor"] = actor
    return approval_required_response(
        action=action,
        risk_level=risk_level,
        rationale=rationale,
        details=response_details,
    )
