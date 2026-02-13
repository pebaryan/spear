"""MCP (Model Context Protocol) tool integration for the coding agent.

This module enables:
1. Registering MCP tools
2. Calling MCP tools during execution
3. Tool result tracking in provenance
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
MCP_LOG_PATH = BASE_DIR / "mcp_calls.ttl"

AG = Namespace("http://example.org/agent/")
MCP = Namespace("http://example.org/mcp/")

_namespaces = {
    "ag": AG,
    "mcp": MCP,
    "rdf": RDF,
    "xsd": XSD,
}


def _create_mcp_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_mcp_graph() -> Graph:
    g = _create_mcp_graph()
    if MCP_LOG_PATH.exists():
        g.parse(MCP_LOG_PATH, format="turtle")
    return g


def save_mcp_graph(g: Graph) -> None:
    g.serialize(MCP_LOG_PATH, format="turtle")


def _get_call_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, MCP.Call):
        count += 1
    return count


class MCPTool:
    """Represents an MCP tool."""

    def __init__(self, name: str, description: str, input_schema: Dict = None):
        self.name = name
        self.description = description
        self.input_schema = input_schema or {}
        self._handler: Optional[Callable] = None

    def handler(self, func: Callable) -> Callable:
        """Decorator to register the tool handler."""
        self._handler = func
        return func

    def execute(self, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute the tool with given arguments."""
        if self._handler is None:
            return {"error": f"No handler registered for tool: {self.name}"}

        try:
            result = self._handler(arguments or {})
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


class MCPToolRegistry:
    """Registry of available MCP tools."""

    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        """Register an MCP tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[MCPTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        """List all registered tools."""
        return [
            {"name": t.name, "description": t.description} for t in self._tools.values()
        ]

    def call(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call a tool by name."""
        tool = self.get(tool_name)
        if tool is None:
            return {"error": f"Unknown tool: {tool_name}"}

        return tool.execute(arguments)


_global_registry = MCPToolRegistry()


def get_mcp_registry() -> MCPToolRegistry:
    """Get the global MCP tool registry."""
    return _global_registry


def register_tool(name: str, description: str, input_schema: Dict = None):
    """Decorator to register an MCP tool."""

    def decorator(func: Callable) -> Callable:
        tool = MCPTool(name, description, input_schema)
        tool._handler = func
        _global_registry.register(tool)
        return func

    return decorator


def call_mcp_tool(
    tool_name: str,
    arguments: Dict[str, Any] = None,
    context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Call an MCP tool and log the call to RDF."""
    g = load_mcp_graph()

    call_id = _get_call_count(g)
    call_uri = MCP[f"call/{call_id}"]

    g.add((call_uri, RDF.type, MCP.Call))
    g.add(
        (
            call_uri,
            MCP.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((call_uri, MCP.toolName, Literal(tool_name)))

    if arguments:
        args_json = json.dumps(arguments)
        if len(args_json) > 1000:
            args_json = args_json[:1000] + "... [truncated]"
        g.add((call_uri, MCP.arguments, Literal(args_json)))

    tool = _global_registry.get(tool_name)
    if tool is None:
        g.add((call_uri, MCP.status, Literal("error")))
        g.add((call_uri, MCP.error, Literal(f"Unknown tool: {tool_name}")))
        save_mcp_graph(g)
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    try:
        result = tool.execute(arguments)

        if result.get("success"):
            g.add((call_uri, MCP.status, Literal("success")))
            result_str = json.dumps(result.get("result", {}))
            if len(result_str) > 2000:
                result_str = result_str[:2000] + "... [truncated]"
            g.add((call_uri, MCP.result, Literal(result_str)))
        else:
            g.add((call_uri, MCP.status, Literal("error")))
            error = result.get("error", "Unknown error")
            g.add((call_uri, MCP.error, Literal(error)))

        save_mcp_graph(g)
        return result

    except Exception as e:
        g.add((call_uri, MCP.status, Literal("exception")))
        g.add((call_uri, MCP.exception, Literal(str(e))))
        save_mcp_graph(g)
        return {"success": False, "error": str(e)}


def get_mcp_calls(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent MCP tool calls."""
    g = load_mcp_graph()

    calls = []
    for call in g.subjects(RDF.type, MCP.Call):
        data = {
            "uri": str(call),
            "timestamp": str(g.value(call, MCP.timestamp) or ""),
            "tool_name": str(g.value(call, MCP.toolName) or ""),
            "status": str(g.value(call, MCP.status) or ""),
            "arguments": str(g.value(call, MCP.arguments) or ""),
            "result": str(g.value(call, MCP.result) or ""),
        }

        error = g.value(call, MCP.error)
        if error:
            data["error"] = str(error)

        calls.append(data)

    calls.sort(key=lambda x: x["timestamp"], reverse=True)
    return calls[:limit]


def get_mcp_summary() -> Dict[str, Any]:
    """Get summary of MCP tool usage."""
    g = load_mcp_graph()

    calls = list(g.subjects(RDF.type, MCP.Call))

    by_tool = {}
    by_status = {}

    for call in calls:
        tool_name = g.value(call, MCP.toolName)
        status = g.value(call, MCP.status)

        if tool_name:
            t = str(tool_name)
            by_tool[t] = by_tool.get(t, 0) + 1

        if status:
            s = str(status)
            by_status[s] = by_status.get(s, 0) + 1

    return {
        "total_calls": len(calls),
        "by_tool": by_tool,
        "by_status": by_status,
    }
