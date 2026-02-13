"""Sub-agent dispatcher for parallel task execution.

This enables the agent to:
1. Decompose tasks into subtasks
2. Dispatch sub-agents to execute subtasks
3. Aggregate results from sub-agents
"""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

try:
    from dotenv import load_dotenv

    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except Exception:
    pass

try:
    from litellm import completion
except Exception:
    completion = None


BASE_DIR = Path(__file__).resolve().parent.parent

AG = Namespace("http://example.org/agent/")
SUB = Namespace("http://example.org/subtask/")

_namespaces = {
    "ag": AG,
    "sub": SUB,
    "rdf": RDF,
    "xsd": XSD,
}


def decompose_task(task: str) -> List[Dict[str, str]]:
    """Break a complex task into smaller subtasks using LLM."""
    if completion is None:
        return [{"task": task, "description": "Single task - no decomposition"}]

    model = os.getenv("LITELLM_MODEL", "gpt-4o")
    provider = os.getenv("LITELLM_PROVIDER")
    api_key = os.getenv("LITELLM_API_KEY")
    api_base = os.getenv("LITELLM_API_BASE")

    if provider and "/" not in model:
        model = f"{provider}/{model}"

    prompt = f"""Break down this task into 2-5 smaller, independent subtasks that can be executed in parallel or sequence.

Task: {task}

Respond with a JSON array of subtasks, each with:
- "task": short task name
- "description": what this subtask does
- "depends_on": (optional) array of subtask names this depends on

Example format:
[
  {{"task": "setup", "description": "Initialize project structure"}},
  {{"task": "implement_core", "description": "Implement core functionality", "depends_on": ["setup"]}},
  {{"task": "write_tests", "description": "Write unit tests", "depends_on": ["implement_core"]}}
]

Respond ONLY with JSON, no explanation."""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        api_base=api_base,
        api_key=api_key,
    )

    content = response["choices"][0]["message"]["content"].strip()
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    import json

    try:
        subtasks = json.loads(content)
        return subtasks
    except json.JSONDecodeError:
        return [
            {"task": task, "description": "Decomposition failed, using single task"}
        ]


def execute_subtask(
    subtask: Dict[str, str],
    executor_fn: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    """Execute a single subtask using the provided executor function."""
    task_name = subtask.get("task", "unnamed")
    description = subtask.get("description", "")

    result = {
        "subtask": task_name,
        "description": description,
        "start_time": datetime.now().isoformat(),
    }

    try:
        output = executor_fn(description)
        result["success"] = output.get("success", False)
        result["output"] = output.get("output", "")
        result["exit_code"] = output.get("exit_code", "0")
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["exit_code"] = "1"

    result["end_time"] = datetime.now().isoformat()

    return result


def dispatch_subagents(
    task: str,
    executor_fn: Callable[[str], Dict[str, Any]],
    max_parallel: int = 3,
) -> Dict[str, Any]:
    """Dispatch sub-agents to execute subtasks.

    Args:
        task: The main task to decompose
        executor_fn: Function that executes a subtask (takes description, returns result dict)
        max_parallel: Maximum parallel subtasks (default 3)

    Returns:
        Dictionary with decomposition and results
    """
    subtasks = decompose_task(task)

    results = []

    for subtask in subtasks:
        result = execute_subtask(subtask, executor_fn)
        results.append(result)

    all_success = all(r.get("success", False) for r in results)

    return {
        "main_task": task,
        "subtasks": subtasks,
        "results": results,
        "all_success": all_success,
        "success_count": sum(1 for r in results if r.get("success", False)),
        "total_subtasks": len(results),
    }


def run_parallel_subtasks(
    task_descriptions: List[str],
    executor_fn: Callable[[str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Run multiple tasks in parallel.

    Args:
        task_descriptions: List of task descriptions
        executor_fn: Function that executes a subtask

    Returns:
        List of results
    """
    import concurrent.futures

    results = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(task_descriptions)
    ) as executor:
        future_to_task = {
            executor.submit(executor_fn, desc): desc for desc in task_descriptions
        }

        for future in concurrent.futures.as_completed(future_to_task):
            desc = future_to_task[future]
            try:
                result = future.result()
                result["task"] = desc
                results.append(result)
            except Exception as e:
                results.append(
                    {
                        "task": desc,
                        "success": False,
                        "error": str(e),
                    }
                )

    return results


class SubAgentRegistry:
    """Registry of sub-agent handlers."""

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}

    def register(self, name: str, handler: Callable) -> None:
        """Register a sub-agent handler."""
        self._handlers[name] = handler

    def get(self, name: str) -> Optional[Callable]:
        """Get a handler by name."""
        return self._handlers.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agents."""
        return list(self._handlers.keys())

    def dispatch(self, agent_name: str, task: str) -> Dict[str, Any]:
        """Dispatch task to a specific sub-agent."""
        handler = self.get(agent_name)
        if handler is None:
            return {
                "success": False,
                "error": f"Unknown agent: {agent_name}",
            }

        try:
            return handler(task)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }


_global_registry = SubAgentRegistry()


def get_subagent_registry() -> SubAgentRegistry:
    """Get the global sub-agent registry."""
    return _global_registry


def register_subagent(name: str, handler: Callable) -> None:
    """Register a sub-agent in the global registry."""
    _global_registry.register(name, handler)
