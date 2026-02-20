"""Unit tests for minimal coding agent handlers."""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSkillImport:
    """Tests for skill import functionality."""

    def test_parse_markdown_skill(self):
        """Test parsing markdown skill."""
        from handlers.skill_import import parse_markdown_skill

        markdown = """# Test Skill

Description: A test skill for unit testing.

## Examples

- Example 1: Do something
- Example 2: Do another thing
"""
        skill = parse_markdown_skill(markdown, "test.md")

        assert skill["title"] == "Test Skill"
        assert "test skill" in skill["description"].lower()
        assert len(skill["examples"]) == 2

    def test_parse_markdown_skill_with_code(self):
        """Test parsing markdown with code blocks."""
        from handlers.skill_import import parse_markdown_skill

        markdown = """# Code Skill

Description: Skill with code examples.

```python
def hello():
    print("hello")
```

## Examples

- Run the code
"""
        skill = parse_markdown_skill(markdown, "code.md")

        assert skill["title"] == "Code Skill"


class TestArtifactTracker:
    """Tests for artifact tracker."""

    def test_compute_hash(self):
        """Test content hash computation."""
        from handlers.artifact_tracker import _compute_hash

        hash1 = _compute_hash("hello world")
        hash2 = _compute_hash("hello world")
        hash3 = _compute_hash("different")

        assert hash1 == hash2
        assert hash1 != hash3


class TestMCP:
    """Tests for MCP tools."""

    def test_tool_registry(self):
        """Test MCP tool registry."""
        from handlers.mcp_tools import MCPTool, MCPToolRegistry

        registry = MCPToolRegistry()

        tool = MCPTool("test_tool", "A test tool")

        @tool.handler
        def test_handler(args):
            return {"result": "success"}

        registry.register(tool)

        assert registry.get("test_tool") is not None
        tool_names = [t["name"] for t in registry.list_tools()]
        assert "test_tool" in tool_names

    def test_call_tool(self):
        """Test calling a tool."""
        from handlers.mcp_tools import MCPTool, MCPToolRegistry

        registry = MCPToolRegistry()

        tool = MCPTool("echo", "Echo tool")

        @tool.handler
        def echo_handler(args):
            return {"echo": args.get("message", "")}

        registry.register(tool)

        result = registry.call("echo", {"message": "hello"})

        assert result["success"] is True
        assert result["result"]["echo"] == "hello"

    def test_tool_error_is_not_marked_success(self):
        """Tool handler error payload should map to success=False."""
        from handlers.mcp_tools import MCPTool

        tool = MCPTool("broken", "Returns an error payload")

        @tool.handler
        def broken_handler(args):
            return {"error": "broken"}

        result = tool.execute({})
        assert result["success"] is False
        assert "broken" in result["error"]


class TestSubagent:
    """Tests for sub-agent functionality."""

    def test_task_decomposition_fallback(self):
        """Test task decomposition when LLM not available."""
        from handlers.subagent import decompose_task

        result = decompose_task("test task")

        assert isinstance(result, list)
        assert len(result) >= 1

    def test_run_parallel_subtasks_empty(self):
        """Empty input should return empty results without raising."""
        from handlers.subagent import run_parallel_subtasks

        result = run_parallel_subtasks([], lambda task: {"success": True})
        assert result == []


class TestBuiltinTools:
    """Tests for built-in tools."""

    def test_list_tools(self):
        """Test listing available tools."""
        from handlers.builtin_tools import register_all_tools, list_available_tools

        register_all_tools()
        tools = list_available_tools()

        tool_names = [t["name"] for t in tools]

        assert "run_tests" in tool_names
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "web_search" in tool_names
        assert "bash" in tool_names


class TestExplanationEngine:
    """Tests for explanation engine."""

    def test_generate_explanation(self):
        """Test explanation generation."""
        from handlers.explanation_engine import explain_last_run

        result = explain_last_run()

        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
