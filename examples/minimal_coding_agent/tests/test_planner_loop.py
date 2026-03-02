"""Tests for structured planner loop helpers."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers.planner_loop import (  # noqa: E402
    create_fix_plan,
    finalize_plan,
    set_step_status,
)


def test_create_fix_plan_has_expected_steps():
    plan = create_fix_plan(
        run_id="solve-1",
        task="Fix app",
        strategy="llm_fix",
        attempt=0,
    )
    assert plan["status"] == "in_progress"
    step_ids = [item["id"] for item in plan.get("steps", [])]
    assert step_ids == ["analyze", "apply", "verify", "fallback"]


def test_set_step_status_and_finalize():
    plan = create_fix_plan(
        run_id="solve-2",
        task="Fix app",
        strategy="llm_fix",
        attempt=1,
    )
    set_step_status(plan, "apply", "in_progress", note="writing candidate")
    set_step_status(plan, "apply", "completed", note="candidate written")
    finalize_plan(plan, success=True, summary="all good")

    step_map = {item["id"]: item for item in plan.get("steps", [])}
    assert step_map["apply"]["status"] == "completed"
    assert step_map["apply"]["started_at"]
    assert step_map["apply"]["ended_at"]
    assert plan["status"] == "completed"
    assert plan["summary"] == "all good"
