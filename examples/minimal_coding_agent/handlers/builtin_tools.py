"""Built-in MCP tools for the coding agent.

These tools can be used by the agent during execution.
"""

import subprocess
from pathlib import Path

from .mcp_tools import register_tool, get_mcp_registry, call_mcp_tool


BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = BASE_DIR / "target_project"


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

    test_path = args.get("path", str(TARGET_DIR))
    verbose = "-v" if args.get("verbose") else ""

    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, verbose, "--tb=short"],
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
    file_path = Path(args.get("path", ""))

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
    file_path = Path(args.get("path", ""))

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(args.get("content", ""), encoding="utf-8")

    return {
        "path": str(file_path),
        "size": len(args.get("content", "")),
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
    name="bash",
    description="Execute a bash command.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "cwd": {"type": "string", "description": "Working directory"},
        },
    },
)
def bash_tool(args: dict) -> dict:
    """Execute a bash command."""
    import sys

    command = args.get("command", "")
    cwd = args.get("cwd", str(BASE_DIR))

    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def register_all_tools():
    """Register all built-in tools."""
    run_tests_tool
    read_file_tool
    write_file_tool
    web_search_tool
    bash_tool


def list_available_tools():
    """List all available MCP tools."""
    registry = get_mcp_registry()
    return registry.list_tools()


def call_tool(tool_name: str, arguments: dict = None) -> dict:
    """Call an MCP tool."""
    return call_mcp_tool(tool_name, arguments or {})
