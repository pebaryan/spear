"""Topic handler registry for the SPEAR minimal coding agent."""

from .analyze_error import handle as analyze_error
from .apply_fix import handle as apply_fix
from .autonomous_handlers import (
    autonomous_analyze_handler,
    autonomous_execute_handler,
    autonomous_increment_handler,
    autonomous_learn_handler,
    autonomous_plan_handler,
    autonomous_record_handler,
    autonomous_report_handler,
    autonomous_verify_handler,
    make_autonomous_init_handler,
)
from .build_code import make_handler as make_build_code
from .increment_retry import handle as increment_retry
from .initialize import make_handler as make_initialize
from .log_attempt import handle as log_attempt
from .reset_target import make_handler as make_reset_target
from .run_tests import handle_after as run_tests_after
from .run_tests import handle_before as run_tests_before
from .select_strategy import handle as select_strategy
from .summarize_failure import handle as summarize_failure
from .web_search import handle as web_search
from .write_report import handle as write_report


def build_handlers(task: str, reset_target: bool, run_id: str):
    return {
        "initialize": make_initialize(task, reset_target, run_id),
        "analyze_error": analyze_error,
        "select_strategy": select_strategy,
        "apply_fix": apply_fix,
        "run_tests_after": run_tests_after,
        "log_attempt": log_attempt,
        "increment_retry": increment_retry,
        "write_report": write_report,
    }


def build_build_handlers(task: str, run_id: str):
    return {
        "build_code": make_build_code(task, run_id),
        "run_tests_after": run_tests_after,
        "write_report": write_report,
    }


def build_autonomous_handlers(user_request: str, run_id: str):
    return {
        "autonomous_init": make_autonomous_init_handler(user_request, run_id),
        "autonomous_analyze": autonomous_analyze_handler,
        "autonomous_plan": autonomous_plan_handler,
        "autonomous_execute": autonomous_execute_handler,
        "autonomous_verify": autonomous_verify_handler,
        "autonomous_record": autonomous_record_handler,
        "autonomous_learn": autonomous_learn_handler,
        "autonomous_increment": autonomous_increment_handler,
        "autonomous_report": autonomous_report_handler,
    }
