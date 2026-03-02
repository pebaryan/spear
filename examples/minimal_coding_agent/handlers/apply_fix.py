"""Handler that applies LLM-generated code fixes."""

import json
import os

from .common import (
    APP_FILE,
    TARGET_DIR,
    PythonTestTool,
    llm_fix_code,
    log_file_modified,
)
from .planner_loop import create_fix_plan, finalize_plan, set_step_status
from .repair import auto_repair_project


def _set_repair_result(
    context,
    patch_applied: bool,
    success: bool,
    exit_code: str,
    output: str,
    steps,
    fix_plan=None,
) -> None:
    context.set_variable("patch_applied", "true" if patch_applied else "false")
    context.set_variable("repair_success", "true" if success else "false")
    context.set_variable("repair_exit_code", str(exit_code))
    context.set_variable("repair_output", output)
    context.set_variable("repair_steps_json", json.dumps(steps, indent=2))
    if isinstance(fix_plan, dict):
        context.set_variable("fix_plan_json", json.dumps(fix_plan, indent=2))


def _run_deterministic_fallback(
    context,
    reason: str,
    fix_plan: dict | None = None,
    max_steps: int = 4,
) -> None:
    if isinstance(fix_plan, dict):
        set_step_status(
            fix_plan,
            "fallback",
            "in_progress",
            note=reason,
        )
    repair = auto_repair_project(TARGET_DIR, max_steps=max_steps)
    if isinstance(fix_plan, dict):
        set_step_status(
            fix_plan,
            "fallback",
            "completed" if repair.success else "failed",
            note="Deterministic repair completed"
            if repair.success
            else "Deterministic repair did not reach green tests",
        )
        set_step_status(
            fix_plan,
            "verify",
            "completed" if repair.success else "failed",
            note="Deterministic fallback verification",
        )
        finalize_plan(
            fix_plan,
            success=repair.success,
            summary="Fallback deterministic repair path",
        )
    _set_repair_result(
        context=context,
        patch_applied=repair.applied,
        success=repair.success,
        exit_code=repair.final_exit_code,
        output=repair.final_output,
        steps=[
            {"stage": "llm_unavailable_fallback", "reason": reason},
            *repair.steps,
        ],
        fix_plan=fix_plan,
    )


def handle(context) -> None:
    run_id = context.get_variable("run_id")
    run_id = str(run_id) if run_id else None

    error_summary = context.get_variable("failure_summary")
    if error_summary:
        error_summary = str(error_summary)
    else:
        error_summary = "Tests failed"

    source_code = APP_FILE.read_text(encoding="utf-8")
    test_code = (TARGET_DIR / "test_app.py").read_text(encoding="utf-8")
    strategy = str(context.get_variable("chosen_strategy") or "llm_fix")
    llm_enabled = str(context.get_variable("llm_enabled") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    fallback_max_steps_raw = context.get_variable("fallback_max_steps")
    try:
        fallback_max_steps = int(fallback_max_steps_raw) if fallback_max_steps_raw else 4
    except Exception:
        fallback_max_steps = 4
    fallback_max_steps = max(1, min(fallback_max_steps, 12))
    task = str(context.get_variable("task") or "Fix failing tests")
    try:
        attempt = int(context.get_variable("retry_count") or 0)
    except Exception:
        attempt = 0

    fix_plan = create_fix_plan(
        run_id=str(run_id or ""),
        task=task,
        strategy=strategy,
        attempt=attempt,
    )
    set_step_status(
        fix_plan,
        "analyze",
        "completed",
        note=f"Error summary captured: {error_summary[:120]}",
    )

    test_result = PythonTestTool.run_tests(TARGET_DIR)
    test_output = test_result["output"]

    disable_llm = os.getenv("SPEAR_DISABLE_LLM_FIX", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not llm_enabled:
        set_step_status(
            fix_plan,
            "apply",
            "skipped",
            note=f"Retry policy selected strategy={strategy}",
        )
        _run_deterministic_fallback(
            context,
            reason=f"Retry policy selected deterministic strategy: {strategy}",
            fix_plan=fix_plan,
            max_steps=fallback_max_steps,
        )
        return
    if disable_llm:
        set_step_status(
            fix_plan,
            "apply",
            "skipped",
            note="LLM fix disabled by environment",
        )
        _run_deterministic_fallback(
            context,
            reason="LLM fix disabled by environment",
            fix_plan=fix_plan,
            max_steps=fallback_max_steps,
        )
        return

    try:
        set_step_status(fix_plan, "apply", "in_progress", note="Generating LLM candidate")
        fixed_code = llm_fix_code(
            source_code,
            error_summary,
            test_output,
            test_code,
            project_dir=TARGET_DIR,
            run_id=run_id,
        )

        if log_file_modified:
            try:
                log_file_modified(
                    str(APP_FILE),
                    fixed_code,
                    source_code,
                    task="fix_bugs",
                    run_id=run_id,
                )
            except Exception:
                pass

        APP_FILE.write_text(fixed_code, encoding="utf-8")
        set_step_status(
            fix_plan,
            "apply",
            "completed",
            note="LLM candidate written to app.py",
        )
        set_step_status(fix_plan, "verify", "in_progress", note="Running tests")

        result = PythonTestTool.run_tests(TARGET_DIR)
        success = result["exit_code"] == "0"

        if not success:
            APP_FILE.write_text(source_code, encoding="utf-8")
            set_step_status(
                fix_plan,
                "verify",
                "failed",
                note="LLM candidate failed tests and was reverted",
            )
            set_step_status(
                fix_plan,
                "apply",
                "failed",
                note="LLM candidate did not pass verification",
            )
            _run_deterministic_fallback(
                context,
                reason="LLM candidate failed tests and was reverted",
                fix_plan=fix_plan,
                max_steps=fallback_max_steps,
            )
        else:
            set_step_status(
                fix_plan,
                "verify",
                "completed",
                note="LLM candidate passed tests",
            )
            set_step_status(
                fix_plan,
                "fallback",
                "skipped",
                note="Fallback not needed",
            )
            finalize_plan(
                fix_plan,
                success=True,
                summary="LLM repair candidate passed verification",
            )
            _set_repair_result(
                context=context,
                patch_applied=True,
                success=True,
                exit_code=result["exit_code"],
                output=result["output"],
                steps=[{"stage": "llm_fix_applied"}],
                fix_plan=fix_plan,
            )

    except Exception as e:
        set_step_status(
            fix_plan,
            "apply",
            "failed",
            note=f"LLM error: {e}",
        )
        _run_deterministic_fallback(
            context,
            reason=f"LLM error: {e}",
            fix_plan=fix_plan,
            max_steps=fallback_max_steps,
        )
