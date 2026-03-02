"""Built-in MCP tools for the coding agent."""

import os
import re
import shlex
import subprocess
from pathlib import Path

from .approval import (
    classify_shell_risk,
    classify_write_file_risk,
    enforce_approval_if_needed,
)
from .mcp_tools import register_tool, get_mcp_registry, call_mcp_tool


BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = BASE_DIR / "target_project"
DEFAULT_SHELL_ALLOWED_COMMANDS = {
    "cat",
    "dir",
    "echo",
    "findstr",
    "get-childitem",
    "get-content",
    "get-location",
    "git",
    "ls",
    "pip",
    "pwd",
    "py",
    "pytest",
    "python",
    "python3",
    "rg",
    "type",
    "whoami",
    "write-output",
}


def _resolve_agent_path(path_value: str) -> Path:
    raw = (path_value or "").strip()
    if not raw:
        raise ValueError("Path is required")

    path = Path(raw)
    if not path.is_absolute():
        path = TARGET_DIR / path

    resolved = path.resolve()
    base = BASE_DIR.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Path escapes agent workspace: {resolved}")
    return resolved


def _resolve_workspace_path(path_value: str) -> Path:
    raw = (path_value or "").strip()
    if not raw:
        return BASE_DIR.resolve()

    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path

    resolved = path.resolve()
    base = BASE_DIR.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Path escapes agent workspace: {resolved}")
    return resolved


@register_tool(
    name="run_tests",
    description="Run pytest tests in the target project. Returns test results.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to test directory (default: target_project)",
            },
            "verbose": {"type": "boolean", "description": "Verbose output"},
        },
    },
)
def run_tests_tool(args: dict) -> dict:
    """Run pytest tests."""
    import sys

    test_path_arg = args.get("path", str(TARGET_DIR))
    try:
        test_path = str(_resolve_agent_path(test_path_arg))
    except ValueError as exc:
        return {"error": str(exc)}

    command = [sys.executable, "-m", "pytest", test_path, "--tb=short"]
    if args.get("verbose"):
        command.append("-v")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@register_tool(
    name="read_file",
    description="Read a file from the filesystem.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file"},
            "limit": {"type": "number", "description": "Limit lines read"},
        },
    },
)
def read_file_tool(args: dict) -> dict:
    """Read a file."""
    try:
        file_path = _resolve_agent_path(args.get("path", ""))
    except ValueError as exc:
        return {"error": str(exc)}

    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}

    content = file_path.read_text(encoding="utf-8")

    limit = args.get("limit")
    if limit:
        lines = content.split("\n")[:limit]
        content = "\n".join(lines)

    return {
        "path": str(file_path),
        "content": content,
        "size": len(content),
    }


@register_tool(
    name="write_file",
    description="Write content to a file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file"},
            "content": {"type": "string", "description": "Content to write"},
        },
    },
)
def write_file_tool(args: dict) -> dict:
    """Write a file."""
    try:
        file_path = _resolve_agent_path(args.get("path", ""))
    except ValueError as exc:
        return {"error": str(exc)}

    content = args.get("content", "")
    existed = file_path.exists()
    changed = True
    if existed:
        try:
            changed = file_path.read_text(encoding="utf-8") != str(content)
        except Exception:
            changed = True

    risk_level, rationale = classify_write_file_risk(
        file_path=file_path,
        target_dir=TARGET_DIR,
        existed=existed,
        changed=changed,
    )
    approval = enforce_approval_if_needed(
        action="write_file",
        risk_level=risk_level,
        rationale=rationale,
        args={**args, "tool_name": "write_file"},
        details={"path": str(file_path), "changed": bool(changed)},
    )
    if approval is not None:
        return approval

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    return {
        "path": str(file_path),
        "size": len(content),
        "risk_level": risk_level,
    }


@register_tool(
    name="web_search",
    description="Search the web for information.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "number", "description": "Max results (default 5)"},
        },
    },
)
def web_search_tool(args: dict) -> dict:
    """Search the web using Brave API."""
    import os

    query = args.get("query", "")
    max_results = args.get("max_results", 5)

    try:
        from handlers.common import WebSearchTool

        tool = WebSearchTool()
        results = tool.search(query, max_results=max_results)

        return {
            "results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet} for r in results
            ]
        }
    except Exception as e:
        return {"error": str(e)}


@register_tool(
    name="git_status",
    description="Show git status for the current workspace or subdirectory.",
    input_schema={
        "type": "object",
        "properties": {
            "cwd": {"type": "string", "description": "Working directory (default: agent root)"},
        },
    },
)
def git_status_tool(args: dict) -> dict:
    """Run `git status --short` in a workspace-safe directory."""
    try:
        cwd = str(_resolve_workspace_path(args.get("cwd", "")))
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=False,
        )
    except Exception as exc:
        return {"error": str(exc)}

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@register_tool(
    name="git_diff",
    description="Show git diff (optionally for one file).",
    input_schema={
        "type": "object",
        "properties": {
            "cwd": {"type": "string", "description": "Working directory (default: agent root)"},
            "path": {"type": "string", "description": "Optional file path to limit diff"},
            "staged": {"type": "boolean", "description": "Show staged diff"},
        },
    },
)
def git_diff_tool(args: dict) -> dict:
    """Run `git diff` with optional staged flag and file scope."""
    try:
        cwd_path = _resolve_workspace_path(args.get("cwd", ""))
    except ValueError as exc:
        return {"error": str(exc)}

    command = ["git", "diff"]
    if args.get("staged"):
        command.append("--staged")

    target = (args.get("path", "") or "").strip()
    if target:
        try:
            target_path = _resolve_workspace_path(str(Path(cwd_path) / target))
        except ValueError as exc:
            return {"error": str(exc)}
        command.extend(["--", str(target_path)])

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            shell=False,
        )
    except Exception as exc:
        return {"error": str(exc)}

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _is_enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _shell_tool_enabled() -> bool:
    return _is_enabled(os.getenv("SPEAR_ALLOW_SHELL_TOOL", "")) or _is_enabled(
        os.getenv("SPEAR_ALLOW_BASH_TOOL", "")
    )


def _shell_allow_unsafe() -> bool:
    return _is_enabled(os.getenv("SPEAR_SHELL_ALLOW_UNSAFE", ""))


def _normalized_command_name(token: str) -> str:
    cleaned = (token or "").strip().strip('"').strip("'")
    if not cleaned:
        return ""
    name = Path(cleaned).name or cleaned
    lowered = name.lower()
    for suffix in (".exe", ".cmd", ".bat", ".com"):
        if lowered.endswith(suffix):
            lowered = lowered[: -len(suffix)]
            break
    return lowered


def _extract_primary_command(command: str, mode: str) -> str:
    raw = (command or "").strip()
    if not raw:
        return ""

    if mode == "argv":
        parts = shlex.split(raw, posix=(os.name != "nt"))
        return _normalized_command_name(parts[0]) if parts else ""

    candidate = raw
    if candidate.startswith("&"):
        candidate = candidate[1:].lstrip()
    match = re.match(r"""^["']?([A-Za-z0-9_./:\\-]+)""", candidate)
    if not match:
        return ""
    return _normalized_command_name(match.group(1))


def _command_allowlist() -> set[str]:
    configured = os.getenv("SPEAR_SHELL_ALLOWED_COMMANDS", "").strip()
    if not configured:
        return set(DEFAULT_SHELL_ALLOWED_COMMANDS)

    values = re.split(r"[,\s]+", configured)
    allowed = {_normalized_command_name(value) for value in values if value.strip()}
    return {item for item in allowed if item}


def _has_forbidden_operators(command: str, mode: str) -> bool:
    if mode == "argv":
        return False
    return bool(re.search(r"(\&\&|\|\||;|`|\$\(|\||>|<)", command))


def _run_argv(command: str, cwd: str) -> subprocess.CompletedProcess:
    parts = shlex.split(command, posix=(os.name != "nt"))
    if not parts:
        raise ValueError("No command provided")
    return subprocess.run(parts, cwd=cwd, capture_output=True, text=True, shell=False)


def _run_cmd(command: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cmd", "/c", command], cwd=cwd, capture_output=True, text=True, shell=False
    )


def _run_powershell(command: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=cwd,
        capture_output=True,
        text=True,
        shell=False,
    )


def _run_sh(command: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", "-lc", command], cwd=cwd, capture_output=True, text=True, shell=False
    )


@register_tool(
    name="shell",
    description="Execute shell command in a platform-agnostic way.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "cwd": {"type": "string", "description": "Working directory"},
            "mode": {
                "type": "string",
                "description": "Execution mode: auto|argv|powershell|cmd|sh",
            },
        },
    },
)
def shell_tool(args: dict) -> dict:
    """Execute shell command with cross-platform mode selection."""
    command = (args.get("command", "") or "").strip()
    cwd_value = args.get("cwd", str(BASE_DIR))
    mode = (args.get("mode", "auto") or "auto").strip().lower()

    if not _shell_tool_enabled():
        return {
            "error": (
                "shell tool is disabled. Set SPEAR_ALLOW_SHELL_TOOL=true "
                "(or legacy SPEAR_ALLOW_BASH_TOOL=true) to enable."
            )
        }
    if not command:
        return {"error": "No command provided"}

    try:
        cwd = str(_resolve_agent_path(cwd_value))
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        if mode == "auto":
            mode = "powershell" if os.name == "nt" else "sh"

        if not _shell_allow_unsafe():
            if _has_forbidden_operators(command, mode):
                return {
                    "error": (
                        "Command rejected by safety policy: shell operators are not "
                        "allowed in this mode. Use mode='argv' for simple commands."
                    )
                }

            primary = _extract_primary_command(command, mode)
            allowed = _command_allowlist()
            if not primary or primary not in allowed:
                return {
                    "error": (
                        f"Command rejected by allowlist policy: '{primary or command}'. "
                        f"Allowed commands: {', '.join(sorted(allowed))}. "
                        "Set SPEAR_SHELL_ALLOW_UNSAFE=true to bypass in trusted environments."
                    )
                }

        risk_level, rationale = classify_shell_risk(command)
        approval = enforce_approval_if_needed(
            action="shell",
            risk_level=risk_level,
            rationale=rationale,
            args={**args, "tool_name": "shell"},
            details={"command": command, "mode": mode},
        )
        if approval is not None:
            return approval

        if mode == "argv":
            result = _run_argv(command, cwd)
        elif mode == "powershell":
            result = _run_powershell(command, cwd)
        elif mode == "cmd":
            result = _run_cmd(command, cwd)
        elif mode == "sh":
            if os.name == "nt":
                return {"error": "Mode 'sh' is not supported on Windows"}
            result = _run_sh(command, cwd)
        else:
            return {"error": f"Unsupported mode: {mode}"}
    except FileNotFoundError as exc:
        return {"error": f"Shell runtime not found for mode '{mode}': {exc}"}
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "mode": mode,
        "risk_level": risk_level,
    }


@register_tool(
    name="bash",
    description="Legacy alias for shell tool. Prefer tool 'shell'.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "cwd": {"type": "string", "description": "Working directory"},
            "mode": {
                "type": "string",
                "description": "Execution mode: auto|argv|powershell|cmd|sh",
            },
        },
    },
)
def bash_tool(args: dict) -> dict:
    """Backward-compatible alias for shell tool."""
    return shell_tool(args)


def register_all_tools():
    """Register all built-in tools."""
    run_tests_tool
    read_file_tool
    write_file_tool
    web_search_tool
    git_status_tool
    git_diff_tool
    shell_tool
    bash_tool


def list_available_tools():
    """List all available MCP tools."""
    registry = get_mcp_registry()
    return registry.list_tools()


def call_tool(tool_name: str, arguments: dict = None) -> dict:
    """Call an MCP tool."""
    return call_mcp_tool(tool_name, arguments or {})
