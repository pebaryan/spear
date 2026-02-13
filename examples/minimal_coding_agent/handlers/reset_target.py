"""Handler for seeding runtime inputs and resetting the demo fixture."""

from .common import APP_FILE, BUGGY_APP_SOURCE


def make_handler(task: str, reset_target: bool):
    def handle(context) -> None:
        # Seed run inputs in-instance because engine-level initial vars get cleared
        # by the current instance persistence implementation.
        context.set_variable("task", task)
        context.set_variable("reset_target", "true" if reset_target else "false")
        if reset_target:
            APP_FILE.write_text(BUGGY_APP_SOURCE, encoding="utf-8")
            context.set_variable("reset_applied", "true")
        else:
            context.set_variable("reset_applied", "false")

    return handle
