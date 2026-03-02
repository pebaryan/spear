"""Handlers to execute tests before and after patching."""

from rdflib import XSD

from .common import PythonTestTool, TARGET_DIR


def handle_before(context) -> None:
    result = PythonTestTool.run_tests(TARGET_DIR)
    context.set_variable("before_exit_code", result["exit_code"])
    context.set_variable("before_output", result["output"])


def handle_after(context) -> None:
    result = PythonTestTool.run_tests(TARGET_DIR)
    context.set_variable("after_exit_code", result["exit_code"])
    context.set_variable("after_output", result["output"])
    success = result["exit_code"] == "0"
    context.set_variable(
        "success", "true" if success else "false", datatype=XSD.boolean
    )
    context.set_variable(
        "repair_success", "true" if success else "false", datatype=XSD.boolean
    )
