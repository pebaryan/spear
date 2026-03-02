"""Handler that logs fix attempts to RDF for history-aware retries."""

from datetime import datetime
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

AG = Namespace("http://example.org/agent/")
PROC = Namespace("http://example.org/process/")


def handle(context) -> None:
    """Log the fix attempt to RDF for future decision-making."""
    task = context.get_variable("task") or "unknown"
    error_type = context.get_variable("error_type") or "unknown"
    strategy = context.get_variable("strategy_result") or "unknown"
    attempt = context.get_variable("retry_count") or "0"
    success = context.get_variable("repair_success") or "false"
    run_id = context.get_variable("run_id") or ""

    from .common import TARGET_DIR, PythonTestTool

    result = PythonTestTool.run_tests(TARGET_DIR)
    output = result["output"][:500]
    exit_code = result["exit_code"]

    history_path = Path(__file__).resolve().parent.parent / "session_history.ttl"
    g = Graph()
    if history_path.exists():
        try:
            g.parse(history_path, format="turtle")
        except Exception:
            pass

    run_count = len(list(g.subjects(RDF.type, AG.Attempt)))
    run_uri = URIRef(f"http://example.org/session/attempt/{run_count}")

    g.add((run_uri, RDF.type, AG.Attempt))
    g.add((run_uri, AG.command, Literal("solve")))
    g.add((run_uri, AG.task, Literal(str(task)[:200])))
    g.add((run_uri, AG.success, Literal(str(success).lower())))
    g.add((run_uri, AG.exitCode, Literal(exit_code)))
    g.add((run_uri, AG.errorType, Literal(error_type)))
    g.add((run_uri, AG.strategy, Literal(strategy)))
    g.add((run_uri, AG.attempt, Literal(attempt)))
    g.add((run_uri, AG.outputSummary, Literal(output)))
    if run_id:
        g.add((run_uri, AG.runId, Literal(str(run_id))))
    g.add(
        (
            run_uri,
            AG.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )

    try:
        g.serialize(history_path, format="turtle")
    except Exception:
        pass

    context.set_variable("attempt_logged", f"Logged run {run_count} to RDF")
