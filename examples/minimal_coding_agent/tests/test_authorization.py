"""Tests for external authorization provider integration."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers import approval as ap  # noqa: E402
from handlers import approval_audit as aa  # noqa: E402
from handlers import authorization as az  # noqa: E402


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")

    def json(self):
        return self._payload


def test_http_authorization_provider_allows(monkeypatch):
    monkeypatch.setenv("SPEAR_AUTHZ_PROVIDER", "http")
    monkeypatch.setenv("SPEAR_AUTHZ_URL", "https://authz.example.test/check")

    def fake_post(url, json, headers, timeout):
        assert url == "https://authz.example.test/check"
        assert json["actor"] == "alice"
        return _FakeResponse(
            {
                "allow": True,
                "actor": "alice@idp",
                "reason": "role permits action",
                "decision_id": "dec-1",
                "policy_id": "pol-1",
            }
        )

    monkeypatch.setattr(az.httpx, "post", fake_post)

    result = az.authorize_approval(
        actor="alice",
        action="shell",
        risk_level="high",
        rationale="deploy",
        tool_name="shell",
        details={"command": "python -m pytest"},
    )
    assert result["allowed"] is True
    assert result["actor"] == "alice@idp"
    assert result["decision_id"] == "dec-1"


def test_http_authorization_provider_failure_allow_mode(monkeypatch):
    monkeypatch.setenv("SPEAR_AUTHZ_PROVIDER", "http")
    monkeypatch.setenv("SPEAR_AUTHZ_URL", "https://authz.example.test/check")
    monkeypatch.setenv("SPEAR_AUTHZ_FAIL_MODE", "allow")
    monkeypatch.setattr(
        az.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down"))
    )

    result = az.authorize_approval(
        actor="alice",
        action="write_file",
        risk_level="medium",
    )
    assert result["allowed"] is True
    assert "allow mode" in result["reason"].lower()


def test_approval_enforcement_denies_when_external_provider_denies(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setattr(aa, "APPROVAL_GRAPH_PATH", tmp_path / "approval_events.ttl")
    monkeypatch.setattr(
        ap,
        "authorize_approval",
        lambda **kwargs: {
            "allowed": False,
            "provider": "http",
            "reason": "policy denied",
            "decision_id": "dec-22",
            "policy_id": "p-9",
        },
    )

    result = ap.enforce_approval_if_needed(
        action="shell",
        risk_level="high",
        rationale="dangerous",
        args={
            "approved": True,
            "approval_user": "alice",
            "tool_name": "shell",
            "_approval_mode": "auto",
        },
        details={"command": "git reset --hard"},
    )

    assert isinstance(result, dict)
    assert result.get("approval_denied") is True
    assert "authorization provider" in result.get("error", "").lower()

    events = aa.get_approval_events(limit=5)
    assert events
    assert events[0]["decision"] == "denied"
    assert events[0]["authz_provider"] == "http"
    assert events[0]["authz_decision_id"] == "dec-22"
