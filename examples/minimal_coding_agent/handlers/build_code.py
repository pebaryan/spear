"""Handler that builds new code from scratch based on task description."""

import json
from typing import Callable

from .common import (
    TARGET_DIR,
    PythonTestTool,
    llm_build_code,
    Scratchpad,
    log_approach_choice,
)


def make_handler(task: str) -> Callable:
    def handle(context) -> None:
        context.set_variable("build_task", task)

        scratchpad = Scratchpad()
        scratchpad.think(f"Starting build task: {task}", tags=["task", "start"])

        if log_approach_choice:
            try:
                log_approach_choice(
                    task=task,
                    chosen_approach="Generate code from scratch with LLM",
                    rationale="Task requires creating new functionality, LLM can generate both implementation and tests",
                    alternatives=[
                        "Use template",
                        "Copy existing code",
                        "Manual implementation",
                    ],
                )
            except Exception:
                pass

        try:
            result = llm_build_code(task, TARGET_DIR)

            if result["success"]:
                scratchpad.think(
                    "Build succeeded! Tests passing.", tags=["success", "result"]
                )
                context.set_variable("build_success", "true")
                context.set_variable("build_output", result["output"])
                context.set_variable("build_exit_code", "0")
                context.set_variable("success", "true")
                context.set_variable(
                    "build_steps_json", json.dumps(result["steps"], indent=2)
                )
            else:
                scratchpad.think(
                    f"Build failed: {result.get('output', 'Unknown error')[:100]}",
                    tags=["failure", "result"],
                )
                context.set_variable("build_success", "false")
                context.set_variable("build_output", result["output"])
                context.set_variable("build_exit_code", result.get("exit_code", "1"))
                context.set_variable("success", "false")
                context.set_variable(
                    "build_steps_json", json.dumps(result["steps"], indent=2)
                )

        except Exception as e:
            scratchpad.think(
                f"Build error: {str(e)[:100]}", tags=["error", "exception"]
            )
            context.set_variable("build_success", "false")
            context.set_variable("build_output", str(e))
            context.set_variable("build_exit_code", "1")
            context.set_variable("success", "false")
            context.set_variable(
                "build_steps_json",
                json.dumps([{"stage": "build_error", "error": str(e)}], indent=2),
            )

    return handle
