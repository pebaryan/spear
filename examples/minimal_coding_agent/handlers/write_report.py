"""Handler that writes a machine-readable run report."""

import json
from typing import Any, Dict, List

from .common import REPORT_FILE, literal_to_bool, literal_to_int, literal_to_text
from .run_report import save_report as save_rdf_report


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
    build_task = context.get_variable("build_task")
    is_build_mode = build_task is not None

    report = {
        "task": literal_to_text(context.get_variable("task"))
        or literal_to_text(build_task),
    }

    if is_build_mode:
        report["command"] = "build"
        report["build_task"] = literal_to_text(build_task)
        report["build_success"] = literal_to_bool(context.get_variable("build_success"))
        report["build_output"] = literal_to_text(context.get_variable("build_output"))
        report["build_exit_code"] = str(
            literal_to_int(context.get_variable("build_exit_code"), -1)
        )
        report["build_steps"] = _load_repair_steps(
            literal_to_text(context.get_variable("build_steps_json"))
        )
        report["after"] = {
            "exit_code": str(
                literal_to_int(context.get_variable("build_exit_code"), -1)
            ),
            "output": literal_to_text(context.get_variable("build_output")),
        }
    else:
        report["command"] = "solve"
        report["before"] = {
            "exit_code": str(
                literal_to_int(context.get_variable("before_exit_code"), -1)
            ),
            "output": literal_to_text(context.get_variable("before_output")),
        }
        report["after"] = {
            "exit_code": str(
                literal_to_int(context.get_variable("after_exit_code"), -1)
            ),
            "output": literal_to_text(context.get_variable("after_output")),
        }
        report["query"] = literal_to_text(context.get_variable("search_query"))
        report["failure_summary"] = literal_to_text(
            context.get_variable("failure_summary")
        )
        report["search_results"] = _load_search_results(
            literal_to_text(context.get_variable("search_results_json"))
        )
        report["patch_applied"] = literal_to_bool(context.get_variable("patch_applied"))
        report["repair_success"] = literal_to_bool(
            context.get_variable("repair_success")
        )
        report["repair_exit_code"] = str(
            literal_to_int(context.get_variable("repair_exit_code"), -1)
        )
        report["repair_output"] = literal_to_text(context.get_variable("repair_output"))
        report["repair_steps"] = _load_repair_steps(
            literal_to_text(context.get_variable("repair_steps_json"))
        )
        report["reset_applied"] = literal_to_bool(context.get_variable("reset_applied"))
        report["success"] = literal_to_bool(context.get_variable("success"))

    save_rdf_report(report)
    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    context.set_variable("report_path", str(REPORT_FILE))
