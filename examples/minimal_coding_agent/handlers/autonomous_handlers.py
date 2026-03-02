"""Autonomous mode handlers for self-correcting loops."""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import XSD

from .common import TARGET_DIR, PythonTestTool, llm_fix_code, llm_build_code

try:
    from litellm import completion
except Exception:
    completion = None


def make_autonomous_init_handler(user_request: str, run_id: str):
    """Initialize autonomous mode with user request."""

    def handle(context) -> None:
        context.set_variable("user_request", user_request)
        context.set_variable("run_id", run_id)
        context.set_variable("iteration", "0", datatype=XSD.integer)
        context.set_variable("all_done", "false")

        # Try to understand vague requests
        understood = _understand_request(user_request)
        context.set_variable("understood_task", understood.get("task", user_request))
        context.set_variable("task_type", understood.get("type", "unknown"))

        # Check current state
        result = PythonTestTool.run_tests(TARGET_DIR)
        exit_code = result["exit_code"]

        if exit_code == "0":
            context.set_variable("initial_state", "working")
            context.set_variable("all_done", "true")
        else:
            context.set_variable("initial_state", "broken")
            context.set_variable("current_error", _extract_error(result["output"]))

        # Initialize strategy history
        context.set_variable("strategies_tried", "[]")

    return handle


def _understand_request(request: str) -> Dict:
    """Understand vague requests using LLM."""
    if completion is None:
        return {"task": request, "type": "general"}

    model = os.getenv("LITELLM_MODEL", "gpt-4o")
    provider = os.getenv("LITELLM_PROVIDER")
    api_key = os.getenv("LITELLM_API_KEY")
    api_base = os.getenv("LITELLM_API_BASE")

    if provider and "/" not in model:
        model = f"{provider}/{model}"

    prompt = f"""Analyze this request and determine what the user wants:

Request: {request}

Determine:
1. What specific task needs to be done (be specific)
2. What type of task this is:
   - "fix_bugs" - fix failing tests or code errors
   - "build" - create new functionality
   - "improve" - enhance existing code
   - "refactor" - restructure code
   - "general" - unclear, need more info

Respond with JSON:
{{"task": "specific description", "type": "one of the types above"}}
"""
    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            api_base=api_base,
            api_key=api_key,
        )
        content = response["choices"][0]["message"]["content"].strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except Exception:
        return {"task": request, "type": "general"}


def _extract_error(output: str) -> str:
    """Extract error message from test output."""
    lines = output.split("\n")
    for line in lines:
        if "ERROR" in line or "FAILED" in line or "AssertionError" in line:
            return line.strip()[:200]
    return output[:200]


def autonomous_analyze_handler(context) -> None:
    """Analyze current state and determine if more work is needed."""
    # Check if already done
    result = PythonTestTool.run_tests(TARGET_DIR)
    exit_code = result["exit_code"]

    if exit_code == "0":
        context.set_variable("all_done", "true")
        context.set_variable("analysis", "Tests pass - work complete!")
        return

    context.set_variable("all_done", "false")

    # Get previous attempts info
    strategies_tried = context.get_variable("strategies_tried") or "[]"
    iteration = context.get_variable("iteration") or "0"

    error = _extract_error(result["output"])
    context.set_variable("current_error", error)
    context.set_variable("analysis", f"Iteration {iteration}: {error[:100]}")


def autonomous_plan_handler(context) -> None:
    """Plan the next action based on analysis."""
    task_type = context.get_variable("task_type") or "general"
    strategies_tried_str = context.get_variable("strategies_tried") or "[]"
    iteration = int(context.get_variable("iteration") or "0")

    # Available strategies
    strategies = {
        "fix_bugs": [
            "llm_fix",
            "web_search_fix",
            "simplify_approach",
            "different_test",
        ],
        "build": ["generate_code", "add_tests", "simplify"],
        "improve": ["optimize", "refactor", "add_docs"],
        "refactor": ["restructure", "simplify", "modularize"],
    }

    available = strategies.get(task_type, ["try_again"])

    # Parse what we've tried
    try:
        tried = json.loads(strategies_tried_str) if strategies_tried_str != "[]" else []
    except:
        tried = []

    # Pick a strategy we haven't tried much
    for strategy in available:
        if tried.count(strategy) < 2 and strategy not in tried[-2:]:
            chosen = strategy
            break
    else:
        chosen = available[0] if available else "try_again"

    context.set_variable("chosen_strategy", chosen)
    context.set_variable("plan", f"Attempt: {chosen} (iteration {iteration})")


def autonomous_execute_handler(context) -> None:
    """Execute the planned action."""
    strategy = context.get_variable("chosen_strategy") or "try_again"
    task_type = context.get_variable("task_type") or "general"
    run_id = context.get_variable("run_id")
    run_id = str(run_id) if run_id else None

    app_file = TARGET_DIR / "app.py"
    test_file = TARGET_DIR / "test_app.py"

    source_code = ""
    test_code = ""
    if app_file.exists():
        source_code = app_file.read_text(encoding="utf-8")
    if test_file.exists():
        test_code = test_file.read_text(encoding="utf-8")

    error = context.get_variable("current_error") or "Unknown error"

    if strategy == "llm_fix":
        try:
            fixed = llm_fix_code(
                source_code,
                error,
                "",
                test_code,
                project_dir=TARGET_DIR,
                run_id=run_id,
            )
            app_file.write_text(fixed, encoding="utf-8")
            context.set_variable("action_taken", "Applied LLM fix")
        except Exception as e:
            context.set_variable("action_taken", f"LLM fix failed: {str(e)[:100]}")

    elif strategy == "generate_code":
        task = context.get_variable("understood_task") or "Create working code"
        result = llm_build_code(task, TARGET_DIR, run_id=run_id)
        context.set_variable(
            "action_taken",
            "Generated new code" if result.get("success") else "Generation failed",
        )

    elif strategy == "try_again":
        context.set_variable("action_taken", "Retrying with same approach")

    else:
        context.set_variable("action_taken", f"Strategy: {strategy}")


def autonomous_verify_handler(context) -> None:
    """Verify the result of the action."""
    result = PythonTestTool.run_tests(TARGET_DIR)
    exit_code = result["exit_code"]

    if exit_code == "0":
        context.set_variable("action_success", "true")
        context.set_variable("verification", "Tests pass!")
    else:
        context.set_variable("action_success", "false")
        context.set_variable(
            "verification", f"Still failing: {_extract_error(result['output'])[:100]}"
        )


def autonomous_record_handler(context) -> None:
    """Record successful action."""
    strategy = context.get_variable("chosen_strategy") or "unknown"
    strategies_tried_str = context.get_variable("strategies_tried") or "[]"

    try:
        tried = json.loads(strategies_tried_str) if strategies_tried_str != "[]" else []
    except:
        tried = []

    tried.append(strategy)
    context.set_variable("strategies_tried", json.dumps(tried))
    context.set_variable("all_done", "true")
    context.set_variable("record", f"Success with strategy: {strategy}")


def autonomous_learn_handler(context) -> None:
    """Learn from failure and plan next attempt."""
    strategy = context.get_variable("chosen_strategy") or "unknown"
    strategies_tried_str = context.get_variable("strategies_tried") or "[]"
    error = context.get_variable("current_error") or ""

    try:
        tried = json.loads(strategies_tried_str) if strategies_tried_str != "[]" else []
    except:
        tried = []

    tried.append(strategy)
    context.set_variable("strategies_tried", json.dumps(tried))

    # Log what we learned
    context.set_variable(
        "learning",
        f"Strategy {strategy} failed. Error: {error[:50]}. Will try different approach.",
    )


def autonomous_increment_handler(context) -> None:
    """Increment iteration counter."""
    current = int(context.get_variable("iteration") or "0")
    context.set_variable("iteration", str(current + 1), datatype=XSD.integer)


def autonomous_report_handler(context) -> None:
    """Generate final report."""
    all_done = context.get_variable("all_done") == "true"
    iteration = context.get_variable("iteration") or "0"
    strategies_tried_str = context.get_variable("strategies_tried") or "[]"

    try:
        tried = json.loads(strategies_tried_str)
    except:
        tried = []

    result = PythonTestTool.run_tests(TARGET_DIR)
    success = result["exit_code"] == "0"

    report = {
        "success": success,
        "iterations": iteration,
        "strategies_tried": tried,
        "final_state": "Tests pass"
        if success
        else f"Failed after {iteration} iterations",
    }

    context.set_variable("final_report", json.dumps(report, indent=2))
    context.set_variable("report_json", json.dumps(report))
