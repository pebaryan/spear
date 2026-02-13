"""Handler that applies test-validated repair candidates."""

import json

from .common import TARGET_DIR
from .repair import auto_repair_project

def handle(context) -> None:
    result = auto_repair_project(TARGET_DIR, max_steps=3)
    context.set_variable("patch_applied", "true" if result.applied else "false")
    context.set_variable("repair_success", "true" if result.success else "false")
    context.set_variable("repair_exit_code", result.final_exit_code)
    context.set_variable("repair_output", result.final_output)
    context.set_variable("repair_steps_json", json.dumps(result.steps, indent=2))
