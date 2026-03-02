"""RDF-based run report tracker for minimal coding agent."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

from .redaction import redact_object, redact_text

BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_GRAPH_PATH = BASE_DIR / "run_reports.ttl"

AG = Namespace("http://example.org/agent/")
PROC = Namespace("http://example.org/process/")
VAR = Namespace("http://example.org/variables/")

_namespaces = {
    "ag": AG,
    "proc": PROC,
    "var": VAR,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}


def _create_report_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_report_graph() -> Graph:
    g = _create_report_graph()
    if REPORT_GRAPH_PATH.exists():
        g.parse(REPORT_GRAPH_PATH, format="turtle")
    return g


def save_report_graph(g: Graph) -> None:
    g.serialize(REPORT_GRAPH_PATH, format="turtle")


def _get_report_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, AG.RunReport):
        count += 1
    return count


def save_report(data: Dict[str, Any]) -> str:
    data = redact_object(data)
    g = load_report_graph()

    report_id = _get_report_count(g)
    report_uri = AG[f"report/{report_id}"]

    g.add((report_uri, RDF.type, AG.RunReport))
    g.add(
        (
            report_uri,
            AG.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )

    task = data.get("task", "")
    if task:
        g.add((report_uri, AG.task, Literal(task)))

    command = data.get("command")
    if command:
        g.add((report_uri, AG.command, Literal(command)))

    run_id = data.get("run_id")
    if run_id:
        g.add((report_uri, AG.runId, Literal(run_id)))

    success = data.get("success", data.get("build_success", False))
    if isinstance(success, str):
        success = success.lower() == "true"
    g.add((report_uri, AG.success, Literal(success, datatype=XSD.boolean)))

    if "before" in data:
        before = data["before"]
        before_uri = AG[f"report/{report_id}/before"]
        g.add((before_uri, RDF.type, AG.TestResult))
        g.add((before_uri, AG.exitCode, Literal(before.get("exit_code", "-1"))))
        g.add((report_uri, AG.before, before_uri))

    if "after" in data:
        after = data["after"]
        after_uri = AG[f"report/{report_id}/after"]
        g.add((after_uri, RDF.type, AG.TestResult))
        g.add((after_uri, AG.exitCode, Literal(after.get("exit_code", "-1"))))
        g.add((report_uri, AG.after, after_uri))

    if "build_task" in data:
        g.add((report_uri, AG.buildTask, Literal(data["build_task"])))

    if "build_success" in data:
        build_success = str(data["build_success"]).lower() == "true"
        g.add(
            (report_uri, AG.buildSuccess, Literal(build_success, datatype=XSD.boolean))
        )

    if "build_exit_code" in data:
        g.add((report_uri, AG.buildExitCode, Literal(data["build_exit_code"])))

    if "build_output" in data:
        output = data["build_output"]
        if len(output) > 1000:
            output = output[:1000]
        g.add((report_uri, AG.buildOutput, Literal(output)))

    if "repair_success" in data:
        repair_success = str(data["repair_success"]).lower() == "true"
        g.add(
            (
                report_uri,
                AG.repairSuccess,
                Literal(repair_success, datatype=XSD.boolean),
            )
        )

    if "repair_exit_code" in data:
        g.add((report_uri, AG.repairExitCode, Literal(data["repair_exit_code"])))

    if "patch_applied" in data:
        patch = str(data["patch_applied"]).lower() == "true"
        g.add((report_uri, AG.patchApplied, Literal(patch, datatype=XSD.boolean)))

    if "query" in data and data["query"]:
        g.add((report_uri, AG.searchQuery, Literal(data["query"])))

    if "strategy_result" in data and data["strategy_result"]:
        g.add((report_uri, AG.strategyResult, Literal(str(data["strategy_result"]))))
    if "retry_policy_profile" in data and data["retry_policy_profile"]:
        g.add(
            (
                report_uri,
                AG.retryPolicyProfile,
                Literal(str(data["retry_policy_profile"])),
            )
        )
    if "retry_policy_requested" in data and data["retry_policy_requested"]:
        g.add(
            (
                report_uri,
                AG.retryPolicyRequested,
                Literal(str(data["retry_policy_requested"])),
            )
        )
    if "retry_policy_class" in data and data["retry_policy_class"]:
        g.add(
            (report_uri, AG.retryPolicyClass, Literal(str(data["retry_policy_class"])))
        )
    if "retry_policy_rationale" in data and data["retry_policy_rationale"]:
        rationale = str(data["retry_policy_rationale"])
        if len(rationale) > 1000:
            rationale = rationale[:1000]
        g.add((report_uri, AG.retryPolicyRationale, Literal(rationale)))
    if "retry_policy_auto_reason" in data and data["retry_policy_auto_reason"]:
        auto_reason = str(data["retry_policy_auto_reason"])
        if len(auto_reason) > 1000:
            auto_reason = auto_reason[:1000]
        g.add((report_uri, AG.retryPolicyAutoReason, Literal(auto_reason)))

    if "failure_summary" in data and data["failure_summary"]:
        g.add((report_uri, AG.failureSummary, Literal(data["failure_summary"])))

    if "search_results" in data:
        results = data["search_results"]
        if isinstance(results, list):
            for idx, result in enumerate(results):
                result_uri = AG[f"report/{report_id}/search/{idx}"]
                g.add((result_uri, RDF.type, AG.SearchResult))
                if isinstance(result, dict):
                    if result.get("title"):
                        g.add((result_uri, AG.title, Literal(result["title"])))
                    if result.get("url"):
                        g.add((result_uri, AG.url, Literal(result["url"])))
                    if result.get("source"):
                        g.add((result_uri, AG.source, Literal(result["source"])))
                g.add((report_uri, AG.hasSearchResult, result_uri))

    if "artifact_summary" in data:
        artifacts = data["artifact_summary"]
        if isinstance(artifacts, list):
            for idx, item in enumerate(artifacts):
                if not isinstance(item, dict):
                    continue
                art_uri = AG[f"report/{report_id}/artifact/{idx}"]
                g.add((art_uri, RDF.type, AG.ArtifactSummary))
                if item.get("file_path"):
                    g.add((art_uri, AG.filePath, Literal(str(item["file_path"]))))
                if item.get("operation"):
                    g.add((art_uri, AG.operation, Literal(str(item["operation"]))))
                if "lines_added" in item:
                    try:
                        g.add(
                            (
                                art_uri,
                                AG.linesAdded,
                                Literal(int(item["lines_added"]), datatype=XSD.integer),
                            )
                        )
                    except Exception:
                        pass
                if "lines_removed" in item:
                    try:
                        g.add(
                            (
                                art_uri,
                                AG.linesRemoved,
                                Literal(int(item["lines_removed"]), datatype=XSD.integer),
                            )
                        )
                    except Exception:
                        pass
                g.add((report_uri, AG.hasArtifactSummary, art_uri))

    if "repair_steps" in data:
        steps = data["repair_steps"]
        if isinstance(steps, list):
            for idx, step in enumerate(steps):
                step_uri = AG[f"report/{report_id}/step/{idx}"]
                g.add((step_uri, RDF.type, AG.RepairStep))
                if isinstance(step, dict):
                    for key, value in step.items():
                        g.add((step_uri, VAR[key], Literal(str(value))))
                g.add((report_uri, AG.hasRepairStep, step_uri))

    if "build_steps" in data:
        steps = data["build_steps"]
        if isinstance(steps, list):
            for idx, step in enumerate(steps):
                step_uri = AG[f"report/{report_id}/buildstep/{idx}"]
                g.add((step_uri, RDF.type, AG.BuildStep))
                if isinstance(step, dict):
                    for key, value in step.items():
                        g.add((step_uri, VAR[key], Literal(str(value))))
                g.add((report_uri, AG.hasBuildStep, step_uri))

    if "fix_plan" in data:
        plan = data["fix_plan"]
        if isinstance(plan, dict) and plan:
            payload = json.dumps(plan)
            if len(payload) > 6000:
                payload = payload[:6000] + "... [truncated]"
            g.add((report_uri, AG.fixPlanJson, Literal(payload)))

    if "reset_applied" in data:
        reset = str(data["reset_applied"]).lower() == "true"
        g.add((report_uri, AG.resetApplied, Literal(reset, datatype=XSD.boolean)))

    save_report_graph(g)

    return str(report_uri)


def _report_to_dict(g: Graph, report_uri) -> Dict[str, Any]:
    data = {}

    task = g.value(report_uri, AG.task)
    if task:
        data["task"] = str(task)

    command = g.value(report_uri, AG.command)
    if command:
        data["command"] = str(command)

    run_id = g.value(report_uri, AG.runId)
    if run_id:
        data["run_id"] = str(run_id)

    success = g.value(report_uri, AG.success)
    if success is not None:
        data["success"] = str(success).lower() == "true"

    build_task = g.value(report_uri, AG.buildTask)
    if build_task:
        data["build_task"] = str(build_task)

    build_success = g.value(report_uri, AG.buildSuccess)
    if build_success is not None:
        data["build_success"] = str(build_success).lower() == "true"

    build_exit_code = g.value(report_uri, AG.buildExitCode)
    if build_exit_code:
        data["build_exit_code"] = str(build_exit_code)

    build_output = g.value(report_uri, AG.buildOutput)
    if build_output:
        data["build_output"] = str(build_output)

    query = g.value(report_uri, AG.searchQuery)
    if query:
        data["query"] = str(query)

    strategy_result = g.value(report_uri, AG.strategyResult)
    if strategy_result:
        data["strategy_result"] = str(strategy_result)

    retry_policy_profile = g.value(report_uri, AG.retryPolicyProfile)
    if retry_policy_profile:
        data["retry_policy_profile"] = str(retry_policy_profile)

    retry_policy_requested = g.value(report_uri, AG.retryPolicyRequested)
    if retry_policy_requested:
        data["retry_policy_requested"] = str(retry_policy_requested)

    retry_policy_class = g.value(report_uri, AG.retryPolicyClass)
    if retry_policy_class:
        data["retry_policy_class"] = str(retry_policy_class)

    retry_policy_rationale = g.value(report_uri, AG.retryPolicyRationale)
    if retry_policy_rationale:
        data["retry_policy_rationale"] = str(retry_policy_rationale)

    retry_policy_auto_reason = g.value(report_uri, AG.retryPolicyAutoReason)
    if retry_policy_auto_reason:
        data["retry_policy_auto_reason"] = str(retry_policy_auto_reason)

    failure_summary = g.value(report_uri, AG.failureSummary)
    if failure_summary:
        data["failure_summary"] = str(failure_summary)

    patch_applied = g.value(report_uri, AG.patchApplied)
    if patch_applied is not None:
        data["patch_applied"] = str(patch_applied).lower() == "true"

    repair_success = g.value(report_uri, AG.repairSuccess)
    if repair_success is not None:
        data["repair_success"] = str(repair_success).lower() == "true"

    repair_exit_code = g.value(report_uri, AG.repairExitCode)
    if repair_exit_code:
        data["repair_exit_code"] = str(repair_exit_code)

    reset_applied = g.value(report_uri, AG.resetApplied)
    if reset_applied is not None:
        data["reset_applied"] = str(reset_applied).lower() == "true"

    before_uri = g.value(report_uri, AG.before)
    if before_uri:
        exit_code = g.value(before_uri, AG.exitCode)
        data["before"] = {"exit_code": str(exit_code) if exit_code else "-1"}

    after_uri = g.value(report_uri, AG.after)
    if after_uri:
        exit_code = g.value(after_uri, AG.exitCode)
        data["after"] = {"exit_code": str(exit_code) if exit_code else "-1"}

    search_results = []
    for result_uri in g.objects(report_uri, AG.hasSearchResult):
        result = {}
        title = g.value(result_uri, AG.title)
        url = g.value(result_uri, AG.url)
        source = g.value(result_uri, AG.source)
        if title:
            result["title"] = str(title)
        if url:
            result["url"] = str(url)
        if source:
            result["source"] = str(source)
        if result:
            search_results.append(result)
    if search_results:
        data["search_results"] = search_results

    artifact_summary = []
    for art_uri in g.objects(report_uri, AG.hasArtifactSummary):
        item = {}
        file_path = g.value(art_uri, AG.filePath)
        operation = g.value(art_uri, AG.operation)
        lines_added = g.value(art_uri, AG.linesAdded)
        lines_removed = g.value(art_uri, AG.linesRemoved)
        if file_path:
            item["file_path"] = str(file_path)
        if operation:
            item["operation"] = str(operation)
        if lines_added is not None:
            try:
                item["lines_added"] = int(lines_added)
            except Exception:
                pass
        if lines_removed is not None:
            try:
                item["lines_removed"] = int(lines_removed)
            except Exception:
                pass
        if item:
            artifact_summary.append(item)
    if artifact_summary:
        data["artifact_summary"] = artifact_summary

    repair_steps = []
    for step_uri in g.objects(report_uri, AG.hasRepairStep):
        step = {}
        for _, pred, obj in g.triples((step_uri, None, None)):
            key = str(pred).split("/")[-1]
            step[key] = str(obj)
        if step:
            repair_steps.append(step)
    if repair_steps:
        data["repair_steps"] = repair_steps

    build_steps = []
    for step_uri in g.objects(report_uri, AG.hasBuildStep):
        step = {}
        for _, pred, obj in g.triples((step_uri, None, None)):
            key = str(pred).split("/")[-1]
            step[key] = str(obj)
        if step:
            build_steps.append(step)
    if build_steps:
        data["build_steps"] = build_steps

    fix_plan = g.value(report_uri, AG.fixPlanJson)
    if fix_plan:
        try:
            parsed = json.loads(str(fix_plan))
            if isinstance(parsed, dict):
                data["fix_plan"] = parsed
        except Exception:
            data["fix_plan"] = {"raw": str(fix_plan)}

    return redact_object(data)


def load_latest_report() -> Dict[str, Any]:
    g = load_report_graph()

    latest = None
    latest_time = None

    for report in g.subjects(RDF.type, AG.RunReport):
        timestamp = g.value(report, AG.timestamp)
        if timestamp:
            if latest_time is None or str(timestamp) > latest_time:
                latest_time = str(timestamp)
                latest = report

    if not latest:
        return {}

    return _report_to_dict(g, latest)


def load_report_by_run_id(run_id: str) -> Dict[str, Any]:
    if not run_id:
        return {}

    g = load_report_graph()
    latest = None
    latest_time = None
    run_literal = Literal(run_id)

    for report in g.subjects(AG.runId, run_literal):
        timestamp = g.value(report, AG.timestamp)
        ts = str(timestamp or "")
        if latest_time is None or ts > latest_time:
            latest_time = ts
            latest = report

    if not latest:
        return {}

    return _report_to_dict(g, latest)


def query_reports(sparql: str) -> List[Dict[str, Any]]:
    g = load_report_graph()

    results = []
    for row in g.query(sparql):
        result = {}
        for var in row.labels:
            result[var] = redact_text(str(row[var])) if row[var] else None
        results.append(result)
    return results


def get_failed_reports() -> List[Dict[str, Any]]:
    sparql = """
    PREFIX ag: <http://example.org/agent/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    
    SELECT ?report ?timestamp ?task ?success
    WHERE {
        ?report a ag:RunReport .
        ?report ag:timestamp ?timestamp .
        ?report ag:success false .
        OPTIONAL { ?report ag:task ?task }
    }
    ORDER BY DESC(?timestamp)
    LIMIT 20
    """
    return query_reports(sparql)
