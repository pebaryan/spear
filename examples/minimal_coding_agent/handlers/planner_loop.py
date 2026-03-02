"""Structured plan/apply/verify loop helpers for solve mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class PlanStep:
    id: str
    title: str
    status: str = "pending"
    started_at: str = ""
    ended_at: str = ""
    note: str = ""


def _now() -> str:
    return datetime.now().isoformat()


def create_fix_plan(
    *,
    run_id: str,
    task: str,
    strategy: str,
    attempt: int,
) -> Dict[str, Any]:
    return {
        "run_id": str(run_id or ""),
        "created_at": _now(),
        "task": str(task or "fix failing tests"),
        "strategy": str(strategy or "llm_fix"),
        "attempt": int(attempt),
        "status": "in_progress",
        "steps": [
            PlanStep(id="analyze", title="Analyze failure context").__dict__,
            PlanStep(id="apply", title="Apply candidate repair").__dict__,
            PlanStep(id="verify", title="Run verification tests").__dict__,
            PlanStep(id="fallback", title="Fallback deterministic repair").__dict__,
        ],
        "summary": "",
        "completed_at": "",
    }


def _find_step(plan: Dict[str, Any], step_id: str) -> Dict[str, Any] | None:
    for step in plan.get("steps", []):
        if isinstance(step, dict) and str(step.get("id")) == str(step_id):
            return step
    return None


def set_step_status(
    plan: Dict[str, Any],
    step_id: str,
    status: str,
    note: str = "",
) -> Dict[str, Any]:
    step = _find_step(plan, step_id)
    if step is None:
        return plan
    normalized = str(status or "").strip().lower() or "pending"
    if normalized == "in_progress" and not step.get("started_at"):
        step["started_at"] = _now()
    if normalized in {"completed", "failed", "skipped"}:
        if not step.get("started_at"):
            step["started_at"] = _now()
        step["ended_at"] = _now()
    step["status"] = normalized
    if note:
        step["note"] = str(note)
    return plan


def finalize_plan(plan: Dict[str, Any], success: bool, summary: str = "") -> Dict[str, Any]:
    plan["status"] = "completed" if bool(success) else "failed"
    plan["completed_at"] = _now()
    if summary:
        plan["summary"] = str(summary)
    return plan

