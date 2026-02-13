"""Handler that builds code using sub-agents for complex tasks."""

import json
from pathlib import Path
from typing import Callable, Dict, Any

from .common import TARGET_DIR, PythonTestTool, llm_build_code, Scratchpad


def _simple_build_executor(task_description: str) -> Dict[str, Any]:
    """Simple executor that builds code for a single task."""
    project_dir = TARGET_DIR

    result = llm_build_code(task_description, project_dir)

    return {
        "success": result.get("success", False),
        "output": result.get("output", ""),
        "exit_code": result.get("exit_code", "0"),
    }


def make_complex_build_handler(task: str) -> Callable:
    """Create a handler that uses sub-agents for complex builds."""

    def handle(context) -> None:
        context.set_variable("build_task", task)

        scratchpad = Scratchpad()
        scratchpad.think(f"Starting complex build: {task}", tags=["task", "complex"])

        from .subagent import decompose_task, run_parallel_subtasks

        scratchpad.think("Decomposing task into subtasks...", tags=["decompose"])

        subtasks = decompose_task(task)

        scratchpad.think(
            f"Decomposed into {len(subtasks)} subtasks: {[s.get('task', 'unnamed') for s in subtasks]}",
            tags=["subtasks"],
        )

        if len(subtasks) == 1:
            scratchpad.think("Single task - using direct build", tags=["simple"])
            result = llm_build_code(task, TARGET_DIR)

            context.set_variable(
                "build_success", "true" if result.get("success") else "false"
            )
            context.set_variable("build_output", result.get("output", ""))
            context.set_variable("build_exit_code", result.get("exit_code", "0"))
            context.set_variable(
                "success", "true" if result.get("success") else "false"
            )
            context.set_variable(
                "build_steps_json", json.dumps(result.get("steps", []), indent=2)
            )
            return

        task_descriptions = [s.get("description", s.get("task", "")) for s in subtasks]

        context.set_variable("subtask_count", str(len(subtasks)))

        results = run_parallel_subtasks(task_descriptions, _simple_build_executor)

        success_count = sum(1 for r in results if r.get("success", False))

        scratchpad.think(
            f"Completed {success_count}/{len(subtasks)} subtasks successfully",
            tags=["subtasks", "complete"],
        )

        all_success = success_count == len(subtasks)

        combined_output = "\n\n".join(
            [
                f"Subtask {i + 1}: {r.get('task', 'unknown')}\nSuccess: {r.get('success', False)}\nOutput: {r.get('output', '')[:200]}"
                for i, r in enumerate(results)
            ]
        )

        context.set_variable("build_success", "true" if all_success else "false")
        context.set_variable("build_output", combined_output)
        context.set_variable("build_exit_code", "0" if all_success else "1")
        context.set_variable("success", "true" if all_success else "false")
        context.set_variable(
            "build_steps_json",
            json.dumps(
                {
                    "subtasks": subtasks,
                    "results": results,
                    "success_count": success_count,
                    "total": len(subtasks),
                },
                indent=2,
            ),
        )

        scratchpad.think(
            f"Complex build {'succeeded' if all_success else 'failed'}: {success_count}/{len(subtasks)}",
            tags=["result", "success" if all_success else "failure"],
        )

    return handle
