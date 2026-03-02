"""Handler for initializing the agent process with task context."""

from rdflib import XSD

from .common import APP_FILE, BUGGY_APP_SOURCE, BUGGY_TEST_SOURCE, TARGET_DIR


def make_handler(task: str, reset_target: bool, run_id: str):
    def handle(context) -> None:
        context.set_variable("task", task)
        context.set_variable("run_id", run_id)
        context.set_variable("reset_target", "true" if reset_target else "false")

        if context.get_variable("retry_count") is None:
            context.set_variable("retry_count", "0", datatype=XSD.integer)

        if reset_target:
            APP_FILE.write_text(BUGGY_APP_SOURCE, encoding="utf-8")
            (TARGET_DIR / "test_app.py").write_text(BUGGY_TEST_SOURCE, encoding="utf-8")
            context.set_variable("reset_applied", "true")
            context.set_variable("initial_state", "buggy")
        else:
            context.set_variable("reset_applied", "false")
            context.set_variable("initial_state", "current")

        context.set_variable("process_start", "true")
        context.set_variable("error_type", "None")
        context.set_variable("strategy_result", "none")

    return handle
