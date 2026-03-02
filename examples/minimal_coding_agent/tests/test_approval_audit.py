"""Tests for approval audit logging."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers import approval as ap  # noqa: E402
from handlers import approval_audit as aa  # noqa: E402


def test_enforce_approval_logs_request(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setattr(aa, "APPROVAL_GRAPH_PATH", tmp_path / "approval_events.ttl")

    result = ap.enforce_approval_if_needed(
        action="shell",
        risk_level="high",
        rationale="dangerous command",
        args={"_approval_mode": "prompt", "tool_name": "shell"},
        details={"command": "git reset --hard"},
    )

    assert isinstance(result, dict)
    assert result.get("approval_required") is True
    events = aa.get_approval_events(limit=5)
    assert events
    assert events[0]["decision"] == "requested"
    assert events[0]["action"] == "shell"


def test_enforce_approval_logs_approved(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setattr(aa, "APPROVAL_GRAPH_PATH", tmp_path / "approval_events.ttl")

    result = ap.enforce_approval_if_needed(
        action="write_file",
        risk_level="medium",
        rationale="overwrite file",
        args={
            "approved": True,
            "_approval_mode": "auto",
            "tool_name": "write_file",
            "run_id": "run-1",
        },
        details={"path": "app.py"},
    )

    assert result is None
    events = aa.get_approval_events(limit=5)
    assert events
    assert events[0]["decision"] == "approved"
    assert events[0]["mode"] == "auto"
    assert events[0]["run_id"] == "run-1"


def test_policy_min_risk_skips_medium_when_set_to_high(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setenv("SPEAR_APPROVAL_MIN_RISK", "high")
    monkeypatch.setattr(aa, "APPROVAL_GRAPH_PATH", tmp_path / "approval_events.ttl")

    result = ap.enforce_approval_if_needed(
        action="write_file",
        risk_level="medium",
        rationale="overwrite",
        args={},
        details={"path": "app.py"},
    )
    assert result is None
    events = aa.get_approval_events(limit=5)
    assert events == []


def test_policy_override_per_action_and_actor(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setenv("SPEAR_APPROVAL_MIN_RISK", "high")
    monkeypatch.setenv("SPEAR_APPROVAL_MIN_RISK_SHELL", "low")
    monkeypatch.setattr(aa, "APPROVAL_GRAPH_PATH", tmp_path / "approval_events.ttl")

    result = ap.enforce_approval_if_needed(
        action="shell",
        risk_level="low",
        rationale="policy override test",
        args={"approval_user": "alice", "_approval_mode": "prompt"},
        details={"command": "python --version"},
    )
    assert isinstance(result, dict)
    assert result.get("approval_required") is True

    events = aa.get_approval_events(limit=5)
    assert events
    assert events[0]["decision"] == "requested"
    assert events[0]["actor"] == "alice"
    assert events[0]["policy_min_risk"] == "low"
