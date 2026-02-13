"""Handler that applies LLM-generated code fixes."""

import json
from pathlib import Path

from .common import (
    APP_FILE,
    TARGET_DIR,
    PythonTestTool,
    llm_fix_code,
    log_file_modified,
)


def handle(context) -> None:
    error_summary = context.get_variable("failure_summary")
    if error_summary:
        error_summary = str(error_summary)
    else:
        error_summary = "Tests failed"

    source_code = APP_FILE.read_text(encoding="utf-8")
    test_code = (TARGET_DIR / "test_app.py").read_text(encoding="utf-8")

    test_result = PythonTestTool.run_tests(TARGET_DIR)
    test_output = test_result["output"]

    try:
        fixed_code = llm_fix_code(source_code, error_summary, test_output, test_code)

        if log_file_modified:
            try:
                log_file_modified(
                    str(APP_FILE), fixed_code, source_code, task="fix_bugs"
                )
            except Exception:
                pass

        APP_FILE.write_text(fixed_code, encoding="utf-8")

        result = PythonTestTool.run_tests(TARGET_DIR)
        success = result["exit_code"] == "0"

        if not success:
            APP_FILE.write_text(source_code, encoding="utf-8")
            context.set_variable("patch_applied", "false")
            context.set_variable("repair_success", "false")
            context.set_variable("repair_exit_code", result["exit_code"])
            context.set_variable("repair_output", result["output"])
            context.set_variable(
                "repair_steps_json",
                json.dumps([{"stage": "llm_fix_failed_reverted"}], indent=2),
            )
        else:
            context.set_variable("patch_applied", "true")
            context.set_variable("repair_success", "true")
            context.set_variable("repair_exit_code", result["exit_code"])
            context.set_variable("repair_output", result["output"])
            context.set_variable(
                "repair_steps_json",
                json.dumps([{"stage": "llm_fix_applied"}], indent=2),
            )

    except Exception as e:
        context.set_variable("patch_applied", "false")
        context.set_variable("repair_success", "false")
        context.set_variable("repair_exit_code", "1")
        context.set_variable("repair_output", str(e))
        context.set_variable(
            "repair_steps_json",
            json.dumps([{"stage": "llm_error", "error": str(e)}], indent=2),
        )
