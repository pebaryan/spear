"""External authorization provider integration for approval decisions."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import httpx


def _provider() -> str:
    value = str(os.getenv("SPEAR_AUTHZ_PROVIDER", "none") or "").strip().lower()
    if value in {"none", "http"}:
        return value
    return "none"


def _fail_mode() -> str:
    value = str(os.getenv("SPEAR_AUTHZ_FAIL_MODE", "deny") or "").strip().lower()
    if value in {"allow", "deny"}:
        return value
    return "deny"


def _require_actor() -> bool:
    value = str(os.getenv("SPEAR_AUTHZ_REQUIRE_ACTOR", "true") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _timeout_seconds() -> float:
    raw = str(os.getenv("SPEAR_AUTHZ_TIMEOUT_SEC", "3") or "").strip()
    try:
        parsed = float(raw)
    except ValueError:
        parsed = 3.0
    return max(0.2, min(parsed, 30.0))


def _headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    token = str(os.getenv("SPEAR_AUTHZ_TOKEN", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = str(os.getenv("SPEAR_AUTHZ_HEADERS_JSON", "") or "").strip()
    if raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                for key, value in payload.items():
                    headers[str(key)] = str(value)
        except Exception:
            pass
    return headers


def _allow_due_to_failure(reason: str) -> Dict[str, Any]:
    if _fail_mode() == "allow":
        return {
            "allowed": True,
            "provider": _provider(),
            "reason": f"Authorization provider failure in allow mode: {reason}",
            "failure": True,
        }
    return {
        "allowed": False,
        "provider": _provider(),
        "reason": f"Authorization provider failure in deny mode: {reason}",
        "failure": True,
    }


def authorize_approval(
    *,
    actor: str,
    action: str,
    risk_level: str,
    rationale: str = "",
    tool_name: str = "",
    run_id: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Authorize a potentially approved action via configured external provider."""
    provider = _provider()
    normalized_actor = str(actor or "").strip()

    if provider == "none":
        return {"allowed": True, "provider": "none", "reason": "No external provider"}

    if _require_actor() and not normalized_actor:
        return {
            "allowed": False,
            "provider": provider,
            "reason": "Missing actor for external authorization",
        }

    if provider == "http":
        url = str(os.getenv("SPEAR_AUTHZ_URL", "") or "").strip()
        if not url:
            return _allow_due_to_failure("SPEAR_AUTHZ_URL is not configured")

        payload = {
            "actor": normalized_actor,
            "action": str(action or ""),
            "risk_level": str(risk_level or ""),
            "rationale": str(rationale or ""),
            "tool_name": str(tool_name or ""),
            "run_id": str(run_id or ""),
            "details": details or {},
        }

        try:
            response = httpx.post(
                url,
                json=payload,
                headers=_headers(),
                timeout=_timeout_seconds(),
            )
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            return _allow_due_to_failure(str(exc))

        allow_value: Any = False
        if isinstance(body, dict):
            if "allow" in body:
                allow_value = body.get("allow")
            else:
                decision = str(body.get("decision", "")).strip().lower()
                allow_value = decision in {"allow", "approved", "permit", "true", "yes"}

        canonical_actor = (
            str(body.get("actor", "")).strip()
            if isinstance(body, dict) and body.get("actor")
            else normalized_actor
        )
        reason = (
            str(body.get("reason", "")).strip()
            if isinstance(body, dict) and body.get("reason")
            else ""
        )
        decision_id = (
            str(body.get("decision_id", "")).strip()
            if isinstance(body, dict) and body.get("decision_id")
            else ""
        )
        policy_id = (
            str(body.get("policy_id", "")).strip()
            if isinstance(body, dict) and body.get("policy_id")
            else ""
        )

        allowed = bool(allow_value)
        return {
            "allowed": allowed,
            "provider": provider,
            "reason": reason or ("Authorized" if allowed else "Denied by external provider"),
            "actor": canonical_actor,
            "decision_id": decision_id,
            "policy_id": policy_id,
        }

    return {"allowed": True, "provider": "none", "reason": "Unknown provider fallback"}

