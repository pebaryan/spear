import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from rdflib import Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD, RDFS

AG = Namespace("http://example.org/agent#")
VAR = Namespace("http://example.org/variables/")
PROV = Namespace("http://www.w3.org/ns/prov#")

ROOT = Path(__file__).resolve().parents[2]  # demo-agent-provenance
TARGET_APP = ROOT / "target_app"
APP_FILE = TARGET_APP / "app.py"
TESTS_FILE = TARGET_APP / "tests.py"

BLOCKED_CMDS = ("curl", "wget", "rm -rf", "pip install")


def _set_status(context, status: str):
    context.set_variable("last_status", status)


def reset_demo_fixture():
    """Ensure each run starts from the buggy calculator state."""
    text = APP_FILE.read_text()
    buggy_text = text.replace("return total / count", "return total / (count + 1)")
    if buggy_text != text:
        APP_FILE.write_text(buggy_text)


def _bind_graph_namespaces(context):
    context.g.bind("ag", AG, replace=True)
    context.g.bind("prov", PROV, replace=True)
    context.g.bind("var", VAR, replace=True)


def _count_actions_for_tool(context, tool: str) -> int:
    count = 0
    for action in context.g.subjects(RDF.type, AG.Action):
        if (action, PROV.wasAssociatedWith, context.inst) not in context.g:
            continue
        if (action, AG.tool, Literal(tool)) in context.g:
            count += 1
    return count


def _log_action(context, label: str, tool: str, status: str, reason: str = None, command: str = None, targets=None):
    _bind_graph_namespaces(context)
    action = URIRef(f"http://example.org/agent/action/{uuid4()}")
    context.g.add((action, RDF.type, AG.Action))
    context.g.add((action, RDFS.label, Literal(label)))
    context.g.add((action, AG.tool, Literal(tool)))
    context.g.add((action, AG.status, Literal(status)))
    context.g.add((action, PROV.wasAssociatedWith, context.inst))
    context.g.add(
        (
            action,
            PROV.startedAtTime,
            Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime),
        )
    )
    if reason:
        context.g.add((action, AG.reason, Literal(reason)))
    if command:
        context.g.add((action, AG.command, Literal(command)))
    if targets:
        for target in targets:
            context.g.add((action, PROV.used, target))
    return action


def handle_run_tests(context):
    """Run pytest on target_app and store result."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "target_app/tests.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    context.set_variable("tests_output", proc.stdout + proc.stderr)
    context.set_variable("tests_exit_code", proc.returncode, datatype=XSD.integer)
    status = "passed" if proc.returncode == 0 else "failed"
    run_phase = "baseline" if _count_actions_for_tool(context, "pytest") == 0 else "post-fix"
    _log_action(
        context=context,
        label=f"run pytest ({run_phase})",
        tool="pytest",
        status=status,
        targets=[URIRef(f"file://{APP_FILE.resolve()}"), URIRef(f"file://{TESTS_FILE.resolve()}")],
    )
    _set_status(context, status)


def handle_blocked_cmd(context):
    """Simulate a blocked command according to policy."""
    cmd = "curl http://example.com"
    for blocked in BLOCKED_CMDS:
        if cmd.startswith(blocked):
            reason = f"policy: blocked {blocked}"
            context.set_variable("blocked_reason", reason)
            context.set_variable("blocked_command", cmd)
            _log_action(
                context=context,
                label="blocked shell command",
                tool="shell",
                status="blocked",
                reason=reason,
                command=cmd,
            )
            _set_status(context, "blocked")
            return
    # If not blocked, execute (not expected in demo)
    subprocess.run(cmd, shell=True, check=False)
    _log_action(
        context=context,
        label="shell command executed",
        tool="shell",
        status="executed",
        command=cmd,
    )
    _set_status(context, "executed")


def handle_apply_fix(context):
    """Apply code fix and adjust test expectation."""
    text = APP_FILE.read_text()
    updated_text = text.replace("return total / (count + 1)", "return total / count")
    if updated_text != text:
        APP_FILE.write_text(updated_text)

    tests = TESTS_FILE.read_text()
    updated_tests = tests.replace(
        "with pytest.raises(ZeroDivisionError):", "with pytest.raises(ValueError):"
    )
    if updated_tests != tests:
        TESTS_FILE.write_text(updated_tests)

    _log_action(
        context=context,
        label="apply local fix",
        tool="edit",
        status="completed",
        targets=[URIRef(f"file://{APP_FILE.resolve()}"), URIRef(f"file://{TESTS_FILE.resolve()}")],
    )
    _set_status(context, "fixed")
