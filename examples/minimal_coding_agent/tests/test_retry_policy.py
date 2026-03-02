"""Tests for retry policy profile and failure-class strategy selection."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers.retry_policy import (  # noqa: E402
    choose_retry_plan,
    classify_failure,
    get_policy_profile,
)


def test_classify_failure_static_and_runtime():
    assert classify_failure("SyntaxError", "") == "static"
    assert classify_failure("AssertionError", "") == "runtime"


def test_choose_retry_plan_standard_switches_static_after_first_retry():
    first = choose_retry_plan(
        error_type="SyntaxError",
        output="SyntaxError in app.py",
        attempt=0,
        history=[],
        policy_profile="standard",
    )
    second = choose_retry_plan(
        error_type="SyntaxError",
        output="SyntaxError in app.py",
        attempt=1,
        history=[],
        policy_profile="standard",
    )
    assert first["strategy"] == "llm_fix"
    assert second["strategy"] == "different_approach"
    assert second["llm_enabled"] is False


def test_choose_retry_plan_aggressive_switches_runtime_earlier():
    first = choose_retry_plan(
        error_type="AssertionError",
        output="assert 1 == 2",
        attempt=0,
        history=[],
        policy_profile="aggressive",
    )
    second = choose_retry_plan(
        error_type="AssertionError",
        output="assert 1 == 2",
        attempt=1,
        history=[],
        policy_profile="aggressive",
    )
    assert first["strategy"] == "llm_fix"
    assert second["strategy"] == "different_approach"
    assert int(second["fallback_max_steps"]) >= 6


def test_get_policy_profile_accepts_auto(monkeypatch):
    monkeypatch.setenv("SPEAR_RETRY_POLICY_PROFILE", "auto")
    assert get_policy_profile() == "auto"


def test_choose_retry_plan_auto_uses_inferred_profile(monkeypatch):
    from handlers import retry_policy as rp

    monkeypatch.setattr(
        rp,
        "_infer_profile_from_reports",
        lambda failure_class, fallback_profile="standard": {
            "profile": "aggressive",
            "reason": "aggressive historically best",
            "stats": {"aggressive": {"runs": 5, "success": 5}},
        },
    )

    plan = choose_retry_plan(
        error_type="AssertionError",
        output="assert 1 == 2",
        attempt=1,
        history=[],
        policy_profile="auto",
    )
    assert plan["profile"] == "aggressive"
    assert plan["strategy"] == "different_approach"
    assert "auto_reason" in plan
