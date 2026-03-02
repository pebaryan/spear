#!/usr/bin/env python3
"""CI profile runner for release/ops checks of the minimal coding agent."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent
EVAL_DIR = BASE_DIR / "evals"
LATEST_PROFILE_JSON = EVAL_DIR / "ci_profile_latest.json"
LATEST_PROFILE_MD = EVAL_DIR / "ci_profile_latest.md"


def run_step(name: str, command: List[str], cwd: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    duration = round(time.perf_counter() - started, 3)
    return {
        "name": name,
        "command": command,
        "exit_code": result.returncode,
        "duration_sec": duration,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "success": result.returncode == 0,
    }


def load_latest_eval() -> Dict[str, Any]:
    path = EVAL_DIR / "latest_eval.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_profile(
    *,
    created_at: str,
    python_version: str,
    platform: str,
    steps: List[Dict[str, Any]],
    latest_eval: Dict[str, Any],
) -> Dict[str, Any]:
    ok_steps = sum(1 for step in steps if step.get("success"))
    all_ok = ok_steps == len(steps)
    eval_summary = latest_eval.get("summary", {}) if isinstance(latest_eval, dict) else {}
    return {
        "created_at": created_at,
        "python_version": python_version,
        "platform": platform,
        "success": all_ok,
        "steps_total": len(steps),
        "steps_passed": ok_steps,
        "steps": steps,
        "eval_summary": {
            "total_runs": eval_summary.get("total_runs"),
            "executed_runs": eval_summary.get("executed_runs"),
            "skipped_runs": eval_summary.get("skipped_runs"),
            "successful_runs": eval_summary.get("successful_runs"),
            "success_rate": eval_summary.get("success_rate"),
            "avg_duration_sec": eval_summary.get("avg_duration_sec"),
        },
    }


def render_markdown(profile: Dict[str, Any]) -> str:
    lines = [
        "# CI Profile Summary",
        "",
        f"- Created: `{profile.get('created_at', '')}`",
        f"- Python: `{profile.get('python_version', '')}`",
        f"- Platform: `{profile.get('platform', '')}`",
        f"- Success: `{profile.get('success', False)}`",
        (
            f"- Steps: `{profile.get('steps_passed', 0)}/"
            f"{profile.get('steps_total', 0)}`"
        ),
        "",
        "## Steps",
        "",
        "| Step | Exit | Duration (s) | Success |",
        "|---|---:|---:|---|",
    ]
    for step in profile.get("steps", []):
        lines.append(
            f"| {step.get('name', '')} | {step.get('exit_code', '')} | "
            f"{step.get('duration_sec', '')} | {step.get('success', False)} |"
        )
    if not profile.get("steps"):
        lines.append("| (none) |  |  |  |")

    eval_summary = profile.get("eval_summary", {}) or {}
    lines.extend(
        [
            "",
            "## Eval Snapshot",
            "",
            f"- total_runs: `{eval_summary.get('total_runs')}`",
            f"- executed_runs: `{eval_summary.get('executed_runs')}`",
            f"- skipped_runs: `{eval_summary.get('skipped_runs')}`",
            f"- successful_runs: `{eval_summary.get('successful_runs')}`",
            f"- success_rate: `{eval_summary.get('success_rate')}`",
            f"- avg_duration_sec: `{eval_summary.get('avg_duration_sec')}`",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CI profile for minimal coding agent")
    parser.add_argument("--repeats", type=int, default=1, help="Deterministic eval repeats")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip minimal agent regression tests step",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip deterministic eval harness step",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(LATEST_PROFILE_JSON),
        help="JSON output path",
    )
    parser.add_argument(
        "--summary-output",
        type=str,
        default=str(LATEST_PROFILE_MD),
        help="Markdown summary output path",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if args.repeats < 1:
        print("--repeats must be >= 1")
        return 2

    steps: List[Dict[str, Any]] = []
    if not args.skip_tests:
        steps.append(
            run_step(
                "minimal_tests",
                [sys.executable, "-m", "pytest", "examples/minimal_coding_agent/tests", "-q"],
                REPO_ROOT,
            )
        )
    if not args.skip_eval:
        steps.append(
            run_step(
                "deterministic_eval",
                [
                    sys.executable,
                    "examples/minimal_coding_agent/eval_harness.py",
                    "--deterministic",
                    "--scenario",
                    "solve_baseline",
                    "--repeats",
                    str(args.repeats),
                ],
                REPO_ROOT,
            )
        )

    created_at = datetime.now().isoformat()
    latest_eval = load_latest_eval()
    profile = build_profile(
        created_at=created_at,
        python_version=sys.version.split()[0],
        platform=sys.platform,
        steps=steps,
        latest_eval=latest_eval,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(render_markdown(profile), encoding="utf-8")

    print(
        "CI profile:",
        f"success={profile['success']}",
        f"steps={profile['steps_passed']}/{profile['steps_total']}",
        f"json={output_path}",
        f"md={summary_path}",
    )
    return 0 if profile["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
