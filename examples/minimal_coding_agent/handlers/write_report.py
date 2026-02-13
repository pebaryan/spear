"""Handler that writes a machine-readable run report."""

import json
from typing import Any, Dict, List

from .common import REPORT_FILE, literal_to_bool, literal_to_int, literal_to_text


def _load_search_results(payload: str) -> List[Dict[str, Any]]:
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except Exception:
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _load_repair_steps(payload: str) -> List[Dict[str, Any]]:
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except Exception:
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def handle(context) -> None:
    report = {
        "task": literal_to_text(context.get_variable("task")),
        "before": {
            "exit_code": str(literal_to_int(context.get_variable("before_exit_code"), -1)),
            "output": literal_to_text(context.get_variable("before_output")),
        },
        "after": {
            "exit_code": str(literal_to_int(context.get_variable("after_exit_code"), -1)),
            "output": literal_to_text(context.get_variable("after_output")),
        },
        "query": literal_to_text(context.get_variable("search_query")),
        "failure_summary": literal_to_text(context.get_variable("failure_summary")),
        "search_results": _load_search_results(
            literal_to_text(context.get_variable("search_results_json"))
        ),
        "patch_applied": literal_to_bool(context.get_variable("patch_applied")),
        "repair_success": literal_to_bool(context.get_variable("repair_success")),
        "repair_exit_code": str(literal_to_int(context.get_variable("repair_exit_code"), -1)),
        "repair_output": literal_to_text(context.get_variable("repair_output")),
        "repair_steps": _load_repair_steps(
            literal_to_text(context.get_variable("repair_steps_json"))
        ),
        "reset_applied": literal_to_bool(context.get_variable("reset_applied")),
        "success": literal_to_bool(context.get_variable("success")),
    }

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    context.set_variable("report_path", str(REPORT_FILE))
