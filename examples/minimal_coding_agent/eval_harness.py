#!/usr/bin/env python3
"""Scenario-based evaluation harness for the minimal coding agent."""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import agent
from handlers.common import REPORT_FILE
from handlers.session_history import get_history

BASE_DIR = Path(__file__).resolve().parent
EVAL_DIR = BASE_DIR / "evals"
TREND_CSV = EVAL_DIR / "trend.csv"
LATEST_MD = EVAL_DIR / "latest_summary.md"

DEFAULT_SCENARIOS = {
    "solve_baseline": {
        "mode": "solve",
        "task": "Fix the failing tests in target_project/app.py",
        "reset_target": True,
        "requires_llm": False,
    },
    "build_baseline": {
        "mode": "build",
        "task": "Create a running_average(total, count) function that raises ValueError for count <= 0 and provide pytest tests.",
        "reset_target": True,
        "requires_llm": True,
    },
    "auto_baseline": {
        "mode": "auto",
        "task": "Fix the failing tests in target_project/app.py",
        "reset_target": True,
        "requires_llm": True,
    },
}


def run_agent_command(argv: List[str]) -> int:
    args = agent.parse_args(argv)
    return agent.execute_args(args)


def load_report(report_file: Path = REPORT_FILE) -> Dict[str, Any]:
    if not report_file.exists():
        return {}
    try:
        return json.loads(report_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def latest_run_id_for_command(command: str) -> str:
    for entry in get_history(limit=50):
        if entry.get("command") == command and entry.get("run_id"):
            return str(entry["run_id"])
    return ""


def aggregate_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    skipped = sum(1 for item in results if item.get("skipped"))
    executed = total - skipped
    successful = sum(1 for item in results if item.get("success") is True)
    durations = [
        float(item.get("duration_sec", 0.0))
        for item in results
        if isinstance(item.get("duration_sec"), (int, float)) and not item.get("skipped")
    ]

    by_scenario: Dict[str, Dict[str, Any]] = {}
    for item in results:
        scenario = item.get("scenario", "unknown")
        entry = by_scenario.setdefault(
            scenario, {"total": 0, "executed": 0, "skipped": 0, "success": 0}
        )
        entry["total"] += 1
        if item.get("skipped"):
            entry["skipped"] += 1
            continue
        entry["executed"] += 1
        if item.get("success") is True:
            entry["success"] += 1

    for scenario, entry in by_scenario.items():
        total_count = entry["executed"]
        entry["success_rate"] = (
            round((entry["success"] / total_count) * 100.0, 2) if total_count else 0.0
        )

    avg_duration = round(sum(durations) / len(durations), 3) if durations else 0.0

    return {
        "total_runs": total,
        "executed_runs": executed,
        "skipped_runs": skipped,
        "successful_runs": successful,
        "success_rate": round((successful / executed) * 100.0, 2) if executed else 0.0,
        "avg_duration_sec": avg_duration,
        "by_scenario": by_scenario,
    }


def _run_solve_scenario(task: str, reset_target: bool) -> Dict[str, Any]:
    pre_test_exit = None
    if reset_target:
        run_agent_command(["reset"])
        pre_test_exit = run_agent_command(["tests"])

    solve_argv = ["solve", "--task", task]
    if reset_target:
        solve_argv.append("--reset-target")

    started = time.perf_counter()
    solve_exit = run_agent_command(solve_argv)
    duration = round(time.perf_counter() - started, 3)

    post_test_exit = run_agent_command(["tests"])
    report = load_report()

    return {
        "mode": "solve",
        "task": task,
        "duration_sec": duration,
        "pre_test_exit_code": pre_test_exit,
        "command_exit_code": solve_exit,
        "post_test_exit_code": post_test_exit,
        "report_success": report.get("success"),
        "strategy_result": report.get("strategy_result"),
        "retry_policy_profile": report.get("retry_policy_profile"),
        "retry_policy_requested": report.get("retry_policy_requested"),
        "retry_policy_class": report.get("retry_policy_class"),
        "repair_exit_code": report.get("repair_exit_code"),
        "run_id": report.get("run_id", "") or latest_run_id_for_command("solve"),
        "success": solve_exit == 0 and post_test_exit == 0,
        "skipped": False,
    }


def _run_build_scenario(task: str, reset_target: bool) -> Dict[str, Any]:
    pre_test_exit = None
    if reset_target:
        run_agent_command(["reset"])
        pre_test_exit = run_agent_command(["tests"])

    started = time.perf_counter()
    build_exit = run_agent_command(["build", *task.split()])
    duration = round(time.perf_counter() - started, 3)

    post_test_exit = run_agent_command(["tests"])
    report = load_report()

    result = {
        "mode": "build",
        "task": task,
        "duration_sec": duration,
        "pre_test_exit_code": pre_test_exit,
        "command_exit_code": build_exit,
        "post_test_exit_code": post_test_exit,
        "report_success": report.get("build_success"),
        "build_exit_code": report.get("build_exit_code"),
        "run_id": report.get("run_id", "") or latest_run_id_for_command("build"),
        "success": build_exit == 0 and post_test_exit == 0,
        "skipped": False,
    }
    return result


def _run_auto_scenario(task: str, reset_target: bool) -> Dict[str, Any]:
    pre_test_exit = None
    if reset_target:
        run_agent_command(["reset"])
        pre_test_exit = run_agent_command(["tests"])

    started = time.perf_counter()
    auto_exit = run_agent_command(["auto", *task.split()])
    duration = round(time.perf_counter() - started, 3)

    post_test_exit = run_agent_command(["tests"])

    result = {
        "mode": "auto",
        "task": task,
        "duration_sec": duration,
        "pre_test_exit_code": pre_test_exit,
        "command_exit_code": auto_exit,
        "post_test_exit_code": post_test_exit,
        "report_success": None,
        "run_id": latest_run_id_for_command("auto"),
        "success": auto_exit == 0 and post_test_exit == 0,
        "skipped": False,
    }
    return result


def run_scenario(scenario_name: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
    mode = scenario.get("mode", "solve")
    task = scenario.get("task", "")
    reset_target = bool(scenario.get("reset_target", True))

    if mode == "solve":
        result = _run_solve_scenario(task=task, reset_target=reset_target)
    elif mode == "build":
        result = _run_build_scenario(task=task, reset_target=reset_target)
    elif mode == "auto":
        result = _run_auto_scenario(task=task, reset_target=reset_target)
    else:
        raise ValueError(f"Unsupported scenario mode: {mode}")

    result["requires_llm"] = bool(scenario.get("requires_llm", False))
    return result


def _append_trend_rows(
    csv_path: Path,
    created_at: str,
    deterministic: bool,
    policy_profile: str,
    results: List[Dict[str, Any]],
) -> None:
    headers = [
        "created_at",
        "deterministic",
        "policy_profile",
        "scenario",
        "iteration",
        "mode",
        "task",
        "skipped",
        "skip_reason",
        "success",
        "duration_sec",
        "run_id",
        "pre_test_exit_code",
        "command_exit_code",
        "post_test_exit_code",
        "report_success",
    ]

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        if write_header:
            writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "created_at": created_at,
                    "deterministic": str(deterministic).lower(),
                    "policy_profile": item.get("policy_profile", policy_profile),
                    "scenario": item.get("scenario", ""),
                    "iteration": item.get("iteration", ""),
                    "mode": item.get("mode", ""),
                    "task": item.get("task", ""),
                    "skipped": str(bool(item.get("skipped"))).lower(),
                    "skip_reason": item.get("skip_reason", ""),
                    "success": (
                        ""
                        if item.get("success") is None
                        else str(bool(item.get("success"))).lower()
                    ),
                    "duration_sec": item.get("duration_sec", ""),
                    "run_id": item.get("run_id", ""),
                    "pre_test_exit_code": item.get("pre_test_exit_code", ""),
                    "command_exit_code": item.get("command_exit_code", ""),
                    "post_test_exit_code": item.get("post_test_exit_code", ""),
                    "report_success": (
                        ""
                        if item.get("report_success") is None
                        else str(bool(item.get("report_success"))).lower()
                    ),
                }
            )


def _read_recent_trend_rows(csv_path: Path, limit: int = 10) -> List[Dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[-limit:]


def build_markdown_summary(
    payload: Dict[str, Any], recent_rows: List[Dict[str, str]]
) -> str:
    summary = payload["summary"]
    lines = [
        "# Evaluation Summary",
        "",
        f"- Created: `{payload['created_at']}`",
        f"- Deterministic: `{payload['deterministic']}`",
        f"- Policy profile: `{payload.get('policy_profile', 'standard')}`",
        f"- Scenarios: `{', '.join(payload['scenarios'])}`",
        f"- Repeats: `{payload['repeats']}`",
        "",
        "## Aggregate",
        "",
        f"- Total runs: `{summary['total_runs']}`",
        f"- Executed runs: `{summary['executed_runs']}`",
        f"- Skipped runs: `{summary['skipped_runs']}`",
        f"- Successful runs: `{summary['successful_runs']}`",
        f"- Success rate: `{summary['success_rate']}%`",
        f"- Avg duration: `{summary['avg_duration_sec']}s`",
        "",
        "## By Scenario",
        "",
        "| Scenario | Executed | Skipped | Success | Success Rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for scenario, data in summary["by_scenario"].items():
        lines.append(
            f"| {scenario} | {data['executed']} | {data['skipped']} | {data['success']} | {data['success_rate']}% |"
        )

    lines.extend(
        [
            "",
            "## Recent Trend Rows",
            "",
            "| created_at | scenario | iter | mode | skipped | success | duration_sec | run_id |",
            "|---|---|---:|---|---|---|---:|---|",
        ]
    )
    for row in recent_rows:
        lines.append(
            f"| {row.get('created_at', '')} | {row.get('scenario', '')} | {row.get('iteration', '')} | "
            f"{row.get('mode', '')} | {row.get('skipped', '')} | {row.get('success', '')} | "
            f"{row.get('duration_sec', '')} | {row.get('run_id', '')} |"
        )
    if not recent_rows:
        lines.append("| (none) |  |  |  |  |  |  |  |")

    policy_stats: Dict[tuple, Dict[str, int]] = {}
    for row in recent_rows:
        if str(row.get("skipped", "")).lower() == "true":
            continue
        scenario = str(row.get("scenario", "") or "")
        profile = str(row.get("policy_profile", "") or "standard")
        if not scenario:
            continue
        key = (scenario, profile)
        stats = policy_stats.setdefault(key, {"runs": 0, "success": 0})
        stats["runs"] += 1
        if str(row.get("success", "")).lower() == "true":
            stats["success"] += 1

    if policy_stats:
        lines.extend(
            [
                "",
                "## Policy Trend",
                "",
                "| Scenario | Policy | Runs | Success Rate |",
                "|---|---|---:|---:|",
            ]
        )
        for (scenario, profile), stats in sorted(policy_stats.items()):
            runs = int(stats["runs"])
            success = int(stats["success"])
            rate = round((success / runs) * 100.0, 2) if runs else 0.0
            lines.append(f"| {scenario} | {profile} | {runs} | {rate}% |")

    return "\n".join(lines) + "\n"


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate minimal coding agent")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(DEFAULT_SCENARIOS.keys()),
        help="Scenario to run (repeat flag for multiple)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="How many times to run each scenario",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Force deterministic mode by disabling LLM fixes",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default: evals/eval_<timestamp>.json)",
    )
    parser.add_argument(
        "--policy-profile",
        type=str,
        default=os.getenv("SPEAR_RETRY_POLICY_PROFILE", "standard"),
        help="Retry policy profile to evaluate (standard|aggressive|conservative).",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)

    if args.repeats < 1:
        print("--repeats must be >= 1")
        return 2

    if args.deterministic:
        os.environ["SPEAR_DISABLE_LLM_FIX"] = "true"
    os.environ["SPEAR_RETRY_POLICY_PROFILE"] = str(args.policy_profile or "standard")

    scenario_names = args.scenario or ["solve_baseline"]

    all_results: List[Dict[str, Any]] = []
    for scenario_name in scenario_names:
        scenario = DEFAULT_SCENARIOS[scenario_name]
        for iteration in range(1, args.repeats + 1):
            print(f"\n=== Running {scenario_name} ({iteration}/{args.repeats}) ===")
            if args.deterministic and scenario.get("requires_llm"):
                result = {
                    "scenario": scenario_name,
                    "iteration": iteration,
                    "mode": scenario.get("mode", ""),
                    "task": scenario.get("task", ""),
                    "requires_llm": True,
                    "skipped": True,
                    "skip_reason": "requires_llm",
                    "success": None,
                    "duration_sec": 0.0,
                    "run_id": "",
                }
                all_results.append(result)
                print("SKIP requires LLM in deterministic mode")
                continue

            result = run_scenario(scenario_name, scenario)
            result["scenario"] = scenario_name
            result["iteration"] = iteration
            result["policy_profile"] = (
                str(result.get("retry_policy_profile", "")).strip()
                or str(args.policy_profile or "standard")
            )
            all_results.append(result)
            status = "PASS" if result["success"] else "FAIL"
            print(
                f"{status} duration={result['duration_sec']}s "
                f"run_id={result.get('run_id', '')}"
            )

    summary = aggregate_results(all_results)
    created_at = datetime.now().isoformat()
    payload = {
        "created_at": created_at,
        "deterministic": bool(args.deterministic),
        "scenarios": scenario_names,
        "repeats": args.repeats,
        "summary": summary,
        "policy_profile": str(args.policy_profile or "standard"),
        "results": all_results,
    }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = (
        Path(args.output)
        if args.output
        else EVAL_DIR / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    latest_path = EVAL_DIR / "latest_eval.json"
    latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _append_trend_rows(
        csv_path=TREND_CSV,
        created_at=created_at,
        deterministic=bool(args.deterministic),
        policy_profile=str(args.policy_profile or "standard"),
        results=all_results,
    )
    recent_rows = _read_recent_trend_rows(TREND_CSV, limit=10)
    LATEST_MD.write_text(
        build_markdown_summary(payload, recent_rows), encoding="utf-8"
    )

    print("\n=== Summary ===")
    print(
        f"success_rate={summary['success_rate']}% "
        f"({summary['successful_runs']}/{summary['executed_runs']})"
    )
    print(f"avg_duration={summary['avg_duration_sec']}s")
    if summary["skipped_runs"]:
        print(f"skipped={summary['skipped_runs']}")
    print(f"report={output_path}")
    print(f"trend_csv={TREND_CSV}")
    print(f"summary_md={LATEST_MD}")

    return 0 if summary["successful_runs"] == summary["executed_runs"] else 1


if __name__ == "__main__":
    sys.exit(main())
