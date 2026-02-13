"""Topic handler registry for the SPEAR minimal coding agent."""

from .apply_fix import handle as apply_fix
from .build_code import make_handler as make_build_code
from .reset_target import make_handler as make_reset_target
from .run_tests import handle_after as run_tests_after
from .run_tests import handle_before as run_tests_before
from .summarize_failure import handle as summarize_failure
from .web_search import handle as web_search
from .write_report import handle as write_report


def build_handlers(task: str, reset_target: bool):
    return {
        "maybe_reset_target": make_reset_target(task, reset_target),
        "run_tests_before": run_tests_before,
        "summarize_failure": summarize_failure,
        "web_search": web_search,
        "apply_fix": apply_fix,
        "run_tests_after": run_tests_after,
        "write_report": write_report,
    }


def build_build_handlers(task: str):
    return {
        "build_code": make_build_code(task),
        "run_tests_after": run_tests_after,
        "write_report": write_report,
    }
