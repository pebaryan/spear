"""Security tests for secret redaction in provenance logs."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers import llm_provenance as lp  # noqa: E402
from handlers import mcp_tools  # noqa: E402
from handlers import run_report as rr  # noqa: E402
from handlers.redaction import REDACTED, redact_object, redact_text  # noqa: E402


def test_redact_text_masks_common_secret_patterns():
    text = (
        "OPENAI_API_KEY=abc123\n"
        "Authorization: Bearer token-value\n"
        '{"api_key":"secret"}\n'
        "sk-abcdefghijklmnopqrstuvwxyz123456"
    )
    redacted = redact_text(text)
    assert "abc123" not in redacted
    assert "token-value" not in redacted
    assert '"api_key":"secret"' not in redacted
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in redacted
    assert REDACTED in redacted


def test_redact_object_masks_sensitive_keys():
    payload = {
        "api_key": "abc",
        "nested": {"password": "p@ss", "safe": "value"},
        "tokens": ["Authorization: Bearer tkn"],
    }
    redacted = redact_object(payload)
    assert redacted["api_key"] == REDACTED
    assert redacted["nested"]["password"] == REDACTED
    assert redacted["nested"]["safe"] == "value"
    assert "tkn" not in redacted["tokens"][0]


def test_redaction_profile_off_disables_masking(monkeypatch):
    monkeypatch.setenv("SPEAR_REDACTION_PROFILE", "off")
    text = "OPENAI_API_KEY=abc123 Authorization: Bearer token-value"
    redacted = redact_text(text)
    assert redacted == text


def test_redaction_profile_strict_masks_url_and_cookie(monkeypatch):
    monkeypatch.setenv("SPEAR_REDACTION_PROFILE", "strict")
    text = (
        "https://example.org?q=ok&access_token=raw-token\n"
        "Cookie: sessionid=abc; csrftoken=xyz"
    )
    redacted = redact_text(text)
    assert "raw-token" not in redacted
    assert "sessionid=abc" not in redacted
    assert REDACTED in redacted


def test_redaction_extra_sensitive_keys(monkeypatch):
    monkeypatch.setenv("SPEAR_REDACTION_PROFILE", "balanced")
    monkeypatch.setenv("SPEAR_REDACTION_EXTRA_KEYS", "private_note")
    payload = {"private_note": "top secret"}
    redacted = redact_object(payload)
    assert redacted["private_note"] == REDACTED


def test_run_report_redacts_sensitive_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "REPORT_GRAPH_PATH", tmp_path / "run_reports.ttl")
    rr.save_report(
        {
            "task": "fix",
            "command": "solve",
            "run_id": "rid-redact-1",
            "success": True,
            "failure_summary": "OPENAI_API_KEY=shhh",
            "repair_output": "Authorization: Bearer super-token",
            "query": '{"api_key":"secret"}',
        }
    )

    loaded = rr.load_report_by_run_id("rid-redact-1")
    assert "shhh" not in loaded.get("failure_summary", "")
    assert "super-token" not in loaded.get("repair_output", "")
    assert "secret" not in loaded.get("query", "")
    assert REDACTED in loaded.get("failure_summary", "")


def test_llm_provenance_redacts_prompt_and_response(monkeypatch, tmp_path):
    monkeypatch.setattr(lp, "LLM_LOG_PATH", tmp_path / "llm_interactions.ttl")

    lp.log_fix_interaction(
        source_code="print('ok')",
        error_message="OPENAI_API_KEY=local-secret",
        prompt="Authorization: Bearer token-123",
        response='{"password":"abc"}',
        model="test-model",
        success=True,
        metadata={"token": "raw-token"},
        run_id="rid-redact-2",
    )

    interactions = lp.get_interactions(limit=5)
    combined = "\n".join(
        f"{item.get('prompt', '')}\n{item.get('response', '')}" for item in interactions
    )
    assert "token-123" not in combined
    assert '"password":"abc"' not in combined
    assert REDACTED in combined


def test_mcp_log_redacts_arguments_and_result(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_tools, "MCP_LOG_PATH", tmp_path / "mcp_calls.ttl")

    tool = mcp_tools.MCPTool("secret_echo_test", "Echoes payload")

    @tool.handler
    def _handler(args):
        return {"password": "hidden", "echo": args.get("token", "")}

    mcp_tools.get_mcp_registry().register(tool)
    mcp_tools.call_mcp_tool(
        "secret_echo_test",
        {"api_key": "abc123", "token": "raw-token"},
    )

    calls = mcp_tools.get_mcp_calls(limit=5)
    assert calls
    first = calls[0]
    assert "abc123" not in first.get("arguments", "")
    assert "raw-token" not in first.get("arguments", "")
    assert "hidden" not in first.get("result", "")
    assert REDACTED in first.get("arguments", "") or REDACTED in first.get("result", "")
