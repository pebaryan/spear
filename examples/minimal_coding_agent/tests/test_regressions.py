"""Regression tests for minimal coding agent command/runtime behavior."""

import json
import subprocess
import sys
import importlib
import builtins
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Graph, Literal, RDF, XSD

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent  # noqa: E402
from handlers import mcp_tools  # noqa: E402
from handlers.builtin_tools import (  # noqa: E402
    bash_tool,
    git_diff_tool,
    git_status_tool,
    read_file_tool,
    run_tests_tool,
    write_file_tool,
    shell_tool,
)
from handlers.nl_parser import _fallback_parse, execute_intent  # noqa: E402
from handlers.skill_import import parse_markdown_skill  # noqa: E402
from handlers.subagent import run_parallel_subtasks  # noqa: E402


def test_execute_intent_returns_executable_commands():
    ok, cmd = execute_intent({"intent": "build", "task": "make calculator"}, None)
    assert ok is True
    assert cmd == "build make calculator"

    ok, cmd = execute_intent({"intent": "solve", "task": "fix app"}, None)
    assert ok is True
    assert cmd == "solve fix app"

    ok, cmd = execute_intent({"intent": "explain", "type": "why"}, None)
    assert ok is True
    assert cmd == "explain why"


def test_fallback_parser_prioritizes_auto_requests():
    parsed = _fallback_parse("make it work")
    assert parsed["intent"] == "auto"

    parsed = _fallback_parse("search skills for debugging")
    assert parsed["intent"] == "skills"
    assert parsed["action"] == "search"
    assert parsed["query"] == "debugging"


def test_parse_args_supports_multiword_tasks():
    args = agent.parse_args(["build", "Create", "a", "calculator"])
    assert args.command == "build"
    assert args.task == ["Create", "a", "calculator"]

    args = agent.parse_args(["solve", "fix", "failing", "tests"])
    assert args.command == "solve"
    assert args.task_text == ["fix", "failing", "tests"]

    args = agent.parse_args(["explain", "last", "--run-id", "solve-123"])
    assert args.command == "explain"
    assert args.type == "last"
    assert args.run_id == "solve-123"


def test_execute_args_uses_positional_solve_task(monkeypatch):
    captured = {}

    def fake_run(task, reset_target):
        captured["task"] = task
        captured["reset"] = reset_target
        return 0

    monkeypatch.setattr(agent, "run_solve_mode", fake_run)
    args = agent.parse_args(["solve", "fix", "this"])
    rc = agent.execute_args(args)

    assert rc == 0
    assert captured["task"] == "fix this"
    assert captured["reset"] is False


def test_execute_args_explain_last_passes_run_id(monkeypatch, capsys):
    monkeypatch.setattr(agent, "explain_last_run", lambda run_id=None: f"RID={run_id}")
    args = agent.parse_args(["explain", "last", "--run-id", "solve-abc"])
    rc = agent.execute_args(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert "RID=solve-abc" in captured.out


def test_tools_call_auto_approves_when_required(monkeypatch):
    from handlers import builtin_tools

    call_sequence = []

    def fake_register():
        return None

    def fake_call(_tool, arguments):
        call_sequence.append(dict(arguments))
        if not arguments.get("approved"):
            return {
                "success": False,
                "approval_required": True,
                "error": "Approval required",
            }
        return {"success": True, "result": {"ok": True}}

    monkeypatch.setattr(builtin_tools, "register_all_tools", fake_register)
    monkeypatch.setattr(builtin_tools, "call_tool", fake_call)

    args = agent.parse_args(
        [
            "tools",
            "call",
            "write_file",
            '{"path":"app.py","content":"x"}',
            "--approval-mode",
            "auto",
        ]
    )
    rc = agent.execute_args(args)
    assert rc == 0
    assert len(call_sequence) == 2
    assert call_sequence[0].get("approved") is None
    assert call_sequence[1].get("approved") is True


def test_tools_call_prompt_approves_when_user_confirms(monkeypatch):
    from handlers import builtin_tools

    call_sequence = []

    def fake_register():
        return None

    def fake_call(_tool, arguments):
        call_sequence.append(dict(arguments))
        if not arguments.get("approved"):
            return {
                "success": False,
                "approval_required": True,
                "error": "Approval required",
            }
        return {"success": True, "result": {"ok": True}}

    monkeypatch.setattr(builtin_tools, "register_all_tools", fake_register)
    monkeypatch.setattr(builtin_tools, "call_tool", fake_call)
    monkeypatch.setattr(agent.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "y")

    args = agent.parse_args(
        [
            "tools",
            "call",
            "shell",
            '{"command":"git reset --hard","mode":"argv"}',
            "--approval-mode",
            "prompt",
        ]
    )
    rc = agent.execute_args(args)
    assert rc == 0
    assert len(call_sequence) == 2
    assert call_sequence[1].get("approved") is True


def test_tools_call_deny_mode_logs_denial(monkeypatch):
    from handlers import builtin_tools
    from handlers import approval_audit

    logged = {}

    def fake_register():
        return None

    def fake_call(_tool, _arguments):
        return {
            "success": False,
            "approval_required": True,
            "action": "shell",
            "risk_level": "high",
            "rationale": "danger",
            "details": {"command": "git reset --hard"},
            "error": "Approval required",
        }

    def fake_log(**kwargs):
        logged.update(kwargs)
        return "ok"

    monkeypatch.setattr(builtin_tools, "register_all_tools", fake_register)
    monkeypatch.setattr(builtin_tools, "call_tool", fake_call)
    monkeypatch.setattr(approval_audit, "log_approval_event", fake_log)

    args = agent.parse_args(
        [
            "tools",
            "call",
            "shell",
            '{"command":"git reset --hard","mode":"argv"}',
            "--approval-mode",
            "deny",
            "--approval-user",
            "operator1",
        ]
    )
    rc = agent.execute_args(args)
    assert rc == 0
    assert logged.get("decision") == "denied"
    assert logged.get("mode") == "deny"
    assert logged.get("actor") == "operator1"


def test_mcp_tool_execute_returns_failure_on_error_dict():
    tool = mcp_tools.MCPTool("bad", "bad")

    @tool.handler
    def _handler(_args):
        return {"error": "boom"}

    result = tool.execute({})
    assert result["success"] is False
    assert "boom" in result["error"]


def test_builtin_run_tests_omits_empty_args(monkeypatch):
    recorded = {}

    def fake_run(cmd, capture_output, text):
        recorded["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_tests_tool({"path": "examples/minimal_coding_agent/tests"})

    assert "" not in recorded["cmd"]
    assert "--tb=short" in recorded["cmd"]


def test_parallel_subtasks_handles_empty_input():
    assert run_parallel_subtasks([], lambda task: {"success": True}) == []


def test_skill_parser_accepts_numbered_patterns():
    parsed = parse_markdown_skill(
        """# Numbered Patterns

Description: test.

## Patterns

1. Use guard clause
2. Handle edge cases
""",
        "numbered.md",
    )
    assert parsed["patterns"] == ["Use guard clause", "Handle edge cases"]


def test_merge_bpmn_definitions_loads_only_selected_process():
    graph = agent.load_graph(Path("does-not-exist.ttl"))
    agent.merge_bpmn_definitions(graph, ["agent_fix_loop.bpmn"])

    camunda_topic = agent.CAMUNDA_NS.topic
    assert (None, camunda_topic, Literal("autonomous_init")) not in graph


def test_read_file_tool_resolves_relative_to_target_project():
    result = read_file_tool({"path": "app.py"})
    assert "error" not in result
    normalized = Path(result["path"]).as_posix()
    assert normalized.endswith("examples/minimal_coding_agent/target_project/app.py")


def test_read_file_tool_blocks_workspace_escape():
    result = read_file_tool({"path": "../../../README.md"})
    assert "error" in result
    assert "escapes agent workspace" in result["error"]


def test_shell_tool_disabled_by_default():
    result = shell_tool({"command": "echo hello"})
    assert "error" in result
    assert "disabled" in result["error"]


def test_bash_alias_delegates_to_shell_tool():
    result = bash_tool({"command": "echo hello"})
    assert "error" in result
    assert "shell tool is disabled" in result["error"]


def test_shell_tool_blocks_disallowed_command_when_enabled(monkeypatch):
    monkeypatch.setenv("SPEAR_ALLOW_SHELL_TOOL", "true")
    monkeypatch.delenv("SPEAR_SHELL_ALLOWED_COMMANDS", raising=False)
    monkeypatch.delenv("SPEAR_SHELL_ALLOW_UNSAFE", raising=False)

    result = shell_tool({"command": "rm -rf .", "mode": "argv"})
    assert "error" in result
    assert "allowlist policy" in result["error"]


def test_shell_tool_blocks_operator_chaining_in_string_modes(monkeypatch):
    monkeypatch.setenv("SPEAR_ALLOW_SHELL_TOOL", "true")
    monkeypatch.delenv("SPEAR_SHELL_ALLOW_UNSAFE", raising=False)

    result = shell_tool({"command": "python -m pytest; whoami", "mode": "powershell"})
    assert "error" in result
    assert "shell operators are not allowed" in result["error"]


def test_shell_tool_runs_allowed_argv_command_when_enabled(monkeypatch):
    monkeypatch.setenv("SPEAR_ALLOW_SHELL_TOOL", "true")
    monkeypatch.setenv("SPEAR_SHELL_ALLOWED_COMMANDS", "python")
    monkeypatch.delenv("SPEAR_SHELL_ALLOW_UNSAFE", raising=False)

    captured = {}

    def fake_run(cmd, cwd, capture_output, text, shell):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = shell_tool({"command": "python --version", "mode": "argv"})

    assert "error" not in result
    assert result["exit_code"] == 0
    assert captured["cmd"][0].lower().endswith("python")


def test_git_status_tool_invokes_git_status(monkeypatch):
    captured = {}

    def fake_run(cmd, cwd, capture_output, text, shell):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, " M app.py", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = git_status_tool({})
    assert result["exit_code"] == 0
    assert captured["cmd"] == ["git", "status", "--short"]


def test_git_diff_tool_supports_staged_and_path(monkeypatch):
    captured = {}

    def fake_run(cmd, cwd, capture_output, text, shell):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, "diff --git a/app.py b/app.py", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = git_diff_tool({"staged": True, "path": "target_project/app.py"})
    assert result["exit_code"] == 0
    assert captured["cmd"][0:3] == ["git", "diff", "--staged"]
    assert "--" in captured["cmd"]


def test_shell_tool_requires_approval_for_high_risk_command(monkeypatch):
    monkeypatch.setenv("SPEAR_ALLOW_SHELL_TOOL", "true")
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setenv("SPEAR_SHELL_ALLOWED_COMMANDS", "git")
    monkeypatch.delenv("SPEAR_SHELL_ALLOW_UNSAFE", raising=False)

    result = shell_tool({"command": "git reset --hard", "mode": "argv"})
    assert result.get("approval_required") is True
    assert result.get("risk_level") == "high"


def test_shell_tool_high_risk_command_runs_with_approval(monkeypatch):
    monkeypatch.setenv("SPEAR_ALLOW_SHELL_TOOL", "true")
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setenv("SPEAR_SHELL_ALLOWED_COMMANDS", "git")
    monkeypatch.delenv("SPEAR_SHELL_ALLOW_UNSAFE", raising=False)

    captured = {}

    def fake_run(cmd, cwd, capture_output, text, shell):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = shell_tool({"command": "git reset --hard", "mode": "argv", "approved": True})
    assert "error" not in result
    assert result["risk_level"] == "high"
    assert captured["cmd"][0].lower().endswith("git")


def test_write_file_requires_approval_for_overwrite(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setattr("handlers.builtin_tools.TARGET_DIR", tmp_path)
    monkeypatch.setattr(
        "handlers.builtin_tools._resolve_agent_path",
        lambda _path: tmp_path / "app.py",
    )
    file_path = tmp_path / "app.py"
    file_path.write_text("old", encoding="utf-8")

    result = write_file_tool({"path": "app.py", "content": "new"})
    assert result.get("approval_required") is True
    assert result.get("risk_level") == "medium"


def test_write_file_overwrite_runs_with_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("SPEAR_REQUIRE_APPROVALS", "true")
    monkeypatch.setattr("handlers.builtin_tools.TARGET_DIR", tmp_path)
    monkeypatch.setattr(
        "handlers.builtin_tools._resolve_agent_path",
        lambda _path: tmp_path / "app.py",
    )
    file_path = tmp_path / "app.py"
    file_path.write_text("old", encoding="utf-8")

    result = write_file_tool({"path": "app.py", "content": "new", "approved": True})
    assert "error" not in result
    assert result["risk_level"] == "medium"
    assert file_path.read_text(encoding="utf-8") == "new"


def test_run_report_load_by_run_id(monkeypatch, tmp_path):
    from handlers import run_report as rr

    monkeypatch.setattr(rr, "REPORT_GRAPH_PATH", tmp_path / "run_reports.ttl")

    rr.save_report(
        {
            "task": "first",
            "command": "solve",
            "success": True,
            "run_id": "solve-1",
            "repair_exit_code": "0",
        }
    )
    rr.save_report(
        {
            "task": "second",
            "command": "solve",
            "success": False,
            "run_id": "solve-2",
            "repair_exit_code": "1",
        }
    )

    report = rr.load_report_by_run_id("solve-2")
    assert report["run_id"] == "solve-2"
    assert report["task"] == "second"
    assert report["success"] is False


def test_run_report_roundtrips_fix_plan(monkeypatch, tmp_path):
    from handlers import run_report as rr

    monkeypatch.setattr(rr, "REPORT_GRAPH_PATH", tmp_path / "run_reports.ttl")
    rr.save_report(
        {
            "task": "t",
            "command": "solve",
            "run_id": "solve-plan-1",
            "success": True,
            "fix_plan": {
                "status": "completed",
                "steps": [{"id": "analyze", "status": "completed"}],
            },
        }
    )

    report = rr.load_report_by_run_id("solve-plan-1")
    assert report["run_id"] == "solve-plan-1"
    assert isinstance(report.get("fix_plan"), dict)
    assert report["fix_plan"].get("status") == "completed"


def test_run_report_roundtrips_retry_policy_fields(monkeypatch, tmp_path):
    from handlers import run_report as rr

    monkeypatch.setattr(rr, "REPORT_GRAPH_PATH", tmp_path / "run_reports.ttl")
    rr.save_report(
        {
            "task": "t",
            "command": "solve",
            "run_id": "solve-policy-1",
            "success": True,
            "strategy_result": "different_approach",
            "retry_policy_profile": "aggressive",
            "retry_policy_requested": "auto",
            "retry_policy_class": "runtime",
            "retry_policy_rationale": "profile=aggressive",
            "retry_policy_auto_reason": "historical stats",
        }
    )

    report = rr.load_report_by_run_id("solve-policy-1")
    assert report["run_id"] == "solve-policy-1"
    assert report.get("retry_policy_profile") == "aggressive"
    assert report.get("retry_policy_requested") == "auto"
    assert report.get("retry_policy_class") == "runtime"


def test_explain_last_run_scopes_artifacts_and_reasoning_by_run_id(monkeypatch):
    from handlers import explanation_engine as ee

    reports_g = Graph()
    report_old = ee.AG["report/0"]
    report_new = ee.AG["report/1"]
    reports_g.add((report_old, RDF.type, ee.AG.RunReport))
    reports_g.add(
        (
            report_old,
            ee.AG.timestamp,
            Literal("2026-02-14T06:00:00", datatype=XSD.dateTime),
        )
    )
    reports_g.add((report_old, ee.AG.command, Literal("solve")))
    reports_g.add((report_old, ee.AG.task, Literal("old task")))
    reports_g.add((report_old, ee.AG.runId, Literal("run-old")))
    reports_g.add((report_old, ee.AG.success, Literal(True, datatype=XSD.boolean)))

    reports_g.add((report_new, RDF.type, ee.AG.RunReport))
    reports_g.add(
        (
            report_new,
            ee.AG.timestamp,
            Literal("2026-02-14T06:00:30", datatype=XSD.dateTime),
        )
    )
    reports_g.add((report_new, ee.AG.command, Literal("solve")))
    reports_g.add((report_new, ee.AG.task, Literal("new task")))
    reports_g.add((report_new, ee.AG.runId, Literal("run-new")))
    reports_g.add((report_new, ee.AG.success, Literal(True, datatype=XSD.boolean)))

    llm_g = Graph()
    llm_old = ee.LLM["fix/0"]
    llm_new = ee.LLM["fix/1"]
    llm_g.add((llm_old, RDF.type, ee.LLM.FixInteraction))
    llm_g.add(
        (llm_old, ee.LLM.timestamp, Literal("2026-02-14T06:00:05", datatype=XSD.dateTime))
    )
    llm_g.add((llm_old, ee.LLM.runId, Literal("run-old")))
    llm_g.add((llm_old, ee.LLM.prompt, Literal("old prompt")))
    llm_g.add((llm_old, ee.LLM.response, Literal("old response")))

    llm_g.add((llm_new, RDF.type, ee.LLM.FixInteraction))
    llm_g.add(
        (llm_new, ee.LLM.timestamp, Literal("2026-02-14T06:00:20", datatype=XSD.dateTime))
    )
    llm_g.add((llm_new, ee.LLM.runId, Literal("run-new")))
    llm_g.add((llm_new, ee.LLM.prompt, Literal("new prompt")))
    llm_g.add((llm_new, ee.LLM.response, Literal("new response")))

    artifacts_g = Graph()
    art_old = ee.ART["change/0"]
    art_new = ee.ART["change/1"]
    artifacts_g.add((art_old, RDF.type, ee.ART.Artifact))
    artifacts_g.add((art_old, ee.ART.timestamp, Literal("2026-02-14T06:00:05")))
    artifacts_g.add((art_old, ee.ART.filePath, Literal("old.py")))
    artifacts_g.add((art_old, ee.ART.operation, Literal("modified")))
    artifacts_g.add((art_old, ee.ART.runId, Literal("run-old")))

    artifacts_g.add((art_new, RDF.type, ee.ART.Artifact))
    artifacts_g.add((art_new, ee.ART.timestamp, Literal("2026-02-14T06:00:20")))
    artifacts_g.add((art_new, ee.ART.filePath, Literal("new.py")))
    artifacts_g.add((art_new, ee.ART.operation, Literal("modified")))
    artifacts_g.add((art_new, ee.ART.runId, Literal("run-new")))

    reasoning_g = Graph()
    decision_old = ee.REASON["decision/0"]
    decision_new = ee.REASON["decision/1"]
    reasoning_g.add((decision_old, RDF.type, ee.REASON.Decision))
    reasoning_g.add(
        (
            decision_old,
            ee.REASON.timestamp,
            Literal("2026-02-14T06:00:05", datatype=XSD.dateTime),
        )
    )
    reasoning_g.add((decision_old, ee.REASON.decisionType, Literal("fix_strategy")))
    reasoning_g.add((decision_old, ee.REASON.rationale, Literal("old rationale")))
    reasoning_g.add((decision_old, ee.REASON.run_id, Literal("run-old")))

    reasoning_g.add((decision_new, RDF.type, ee.REASON.Decision))
    reasoning_g.add(
        (
            decision_new,
            ee.REASON.timestamp,
            Literal("2026-02-14T06:00:20", datatype=XSD.dateTime),
        )
    )
    reasoning_g.add((decision_new, ee.REASON.decisionType, Literal("fix_strategy")))
    reasoning_g.add((decision_new, ee.REASON.rationale, Literal("new rationale")))
    reasoning_g.add((decision_new, ee.REASON.run_id, Literal("run-new")))

    monkeypatch.setattr(
        ee,
        "_load_all_graphs",
        lambda: {
            "reports": reports_g,
            "llm": llm_g,
            "artifacts": artifacts_g,
            "reasoning": reasoning_g,
        },
    )

    explanation = ee.explain_last_run()
    assert "**Run ID:** run-new" in explanation
    assert "new prompt" in explanation
    assert "new.py" in explanation
    assert "new rationale" in explanation
    assert "old prompt" not in explanation
    assert "old.py" not in explanation
    assert "old rationale" not in explanation


def test_apply_fix_uses_deterministic_fallback_when_llm_fails(monkeypatch, tmp_path):
    temp_dir = tmp_path / "target"
    temp_dir.mkdir(parents=True, exist_ok=True)
    app_file = temp_dir / "app.py"
    test_file = temp_dir / "test_app.py"
    app_file.write_text("def running_average(total, count):\n    return total/(count+1)\n")
    test_file.write_text("def test_dummy():\n    assert True\n")

    monkeypatch.setattr(apply_fix_handler, "APP_FILE", app_file)
    monkeypatch.setattr(apply_fix_handler, "TARGET_DIR", temp_dir)
    monkeypatch.setattr(
        apply_fix_handler.PythonTestTool,
        "run_tests",
        staticmethod(lambda _project: {"exit_code": "1", "output": "failed"}),
    )
    monkeypatch.setattr(
        apply_fix_handler,
        "llm_fix_code",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("llm offline")),
    )
    monkeypatch.setattr(
        apply_fix_handler,
        "auto_repair_project",
        lambda _dir, max_steps=4: SimpleNamespace(
            success=True,
            applied=True,
            steps=[{"stage": "mutation_applied"}],
            final_exit_code="0",
            final_output="ok",
        ),
    )

    class Ctx:
        def __init__(self):
            self.vars = {"failure_summary": "failed tests"}

        def get_variable(self, name):
            return self.vars.get(name)

        def set_variable(self, name, value, datatype=None):
            self.vars[name] = value

    ctx = Ctx()
    apply_fix_handler.handle(ctx)

    assert ctx.vars["repair_success"] == "true"
    assert ctx.vars["patch_applied"] == "true"
    assert ctx.vars["repair_exit_code"] == "0"
    assert "llm_unavailable_fallback" in ctx.vars["repair_steps_json"]
    plan = json.loads(ctx.vars["fix_plan_json"])
    assert plan["status"] == "completed"
    step_map = {item["id"]: item["status"] for item in plan.get("steps", [])}
    assert step_map.get("analyze") == "completed"
    assert step_map.get("fallback") == "completed"


def test_apply_fix_can_skip_llm_via_env(monkeypatch, tmp_path):
    temp_dir = tmp_path / "target"
    temp_dir.mkdir(parents=True, exist_ok=True)
    app_file = temp_dir / "app.py"
    test_file = temp_dir / "test_app.py"
    app_file.write_text("def running_average(total, count):\n    return total/(count+1)\n")
    test_file.write_text("def test_dummy():\n    assert True\n")

    monkeypatch.setattr(apply_fix_handler, "APP_FILE", app_file)
    monkeypatch.setattr(apply_fix_handler, "TARGET_DIR", temp_dir)
    monkeypatch.setattr(
        apply_fix_handler.PythonTestTool,
        "run_tests",
        staticmethod(lambda _project: {"exit_code": "1", "output": "failed"}),
    )
    monkeypatch.setattr(
        apply_fix_handler,
        "llm_fix_code",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    monkeypatch.setattr(
        apply_fix_handler,
        "auto_repair_project",
        lambda _dir, max_steps=4: SimpleNamespace(
            success=True,
            applied=True,
            steps=[{"stage": "mutation_applied"}],
            final_exit_code="0",
            final_output="ok",
        ),
    )
    monkeypatch.setenv("SPEAR_DISABLE_LLM_FIX", "true")

    class Ctx:
        def __init__(self):
            self.vars = {"failure_summary": "failed tests"}

        def get_variable(self, name):
            return self.vars.get(name)

        def set_variable(self, name, value, datatype=None):
            self.vars[name] = value

    ctx = Ctx()
    apply_fix_handler.handle(ctx)
    assert ctx.vars["repair_success"] == "true"
    assert "LLM fix disabled by environment" in ctx.vars["repair_steps_json"]
    plan = json.loads(ctx.vars["fix_plan_json"])
    assert plan["status"] == "completed"
    step_map = {item["id"]: item["status"] for item in plan.get("steps", [])}
    assert step_map.get("apply") == "skipped"
    assert step_map.get("fallback") == "completed"


def test_apply_fix_policy_can_disable_llm_and_set_fallback_steps(monkeypatch, tmp_path):
    temp_dir = tmp_path / "target"
    temp_dir.mkdir(parents=True, exist_ok=True)
    app_file = temp_dir / "app.py"
    test_file = temp_dir / "test_app.py"
    app_file.write_text("def running_average(total, count):\n    return total/(count+1)\n")
    test_file.write_text("def test_dummy():\n    assert True\n")

    monkeypatch.setattr(apply_fix_handler, "APP_FILE", app_file)
    monkeypatch.setattr(apply_fix_handler, "TARGET_DIR", temp_dir)
    monkeypatch.setattr(
        apply_fix_handler.PythonTestTool,
        "run_tests",
        staticmethod(lambda _project: {"exit_code": "1", "output": "failed"}),
    )
    monkeypatch.setattr(
        apply_fix_handler,
        "llm_fix_code",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not call")),
    )

    captured = {}

    def fake_repair(_dir, max_steps=4):
        captured["max_steps"] = max_steps
        return SimpleNamespace(
            success=True,
            applied=True,
            steps=[{"stage": "mutation_applied"}],
            final_exit_code="0",
            final_output="ok",
        )

    monkeypatch.setattr(apply_fix_handler, "auto_repair_project", fake_repair)

    class Ctx:
        def __init__(self):
            self.vars = {
                "failure_summary": "failed tests",
                "chosen_strategy": "different_approach",
                "llm_enabled": "false",
                "fallback_max_steps": "7",
            }

        def get_variable(self, name):
            return self.vars.get(name)

        def set_variable(self, name, value, datatype=None):
            self.vars[name] = value

    ctx = Ctx()
    apply_fix_handler.handle(ctx)
    assert ctx.vars["repair_success"] == "true"
    assert captured["max_steps"] == 7
    plan = json.loads(ctx.vars["fix_plan_json"])
    assert plan["status"] == "completed"
    step_map = {item["id"]: item["status"] for item in plan.get("steps", [])}
    assert step_map.get("apply") == "skipped"
    assert step_map.get("fallback") == "completed"
apply_fix_handler = importlib.import_module("handlers.apply_fix")
