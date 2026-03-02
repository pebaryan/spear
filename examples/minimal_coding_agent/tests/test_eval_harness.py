"""Tests for evaluation harness helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import eval_harness  # noqa: E402


def test_aggregate_results_computes_summary():
    results = [
        {"scenario": "solve_baseline", "success": True, "duration_sec": 1.2},
        {"scenario": "solve_baseline", "success": False, "duration_sec": 2.4},
        {"scenario": "solve_baseline", "success": True, "duration_sec": 0.9},
    ]

    summary = eval_harness.aggregate_results(results)

    assert summary["total_runs"] == 3
    assert summary["executed_runs"] == 3
    assert summary["skipped_runs"] == 0
    assert summary["successful_runs"] == 2
    assert summary["success_rate"] == 66.67
    assert summary["avg_duration_sec"] == 1.5
    assert summary["by_scenario"]["solve_baseline"]["success_rate"] == 66.67
    assert summary["by_scenario"]["solve_baseline"]["executed"] == 3


def test_aggregate_results_counts_skipped():
    results = [
        {"scenario": "build_baseline", "success": None, "skipped": True, "duration_sec": 0.0},
        {"scenario": "solve_baseline", "success": True, "duration_sec": 1.0},
    ]
    summary = eval_harness.aggregate_results(results)
    assert summary["total_runs"] == 2
    assert summary["executed_runs"] == 1
    assert summary["skipped_runs"] == 1
    assert summary["success_rate"] == 100.0
    assert summary["by_scenario"]["build_baseline"]["skipped"] == 1


def test_load_report_handles_missing_or_invalid_json(tmp_path):
    missing = tmp_path / "missing.json"
    assert eval_harness.load_report(missing) == {}

    broken = tmp_path / "broken.json"
    broken.write_text("{broken", encoding="utf-8")
    assert eval_harness.load_report(broken) == {}


def test_parse_args_defaults():
    args = eval_harness.parse_args([])
    assert args.repeats == 1
    assert args.scenario is None
    assert args.deterministic is False
    assert args.policy_profile == "standard"


def test_parse_args_accepts_policy_profile():
    args = eval_harness.parse_args(["--policy-profile", "aggressive"])
    assert args.policy_profile == "aggressive"


def test_build_markdown_summary_contains_sections():
    payload = {
        "created_at": "2026-02-14T00:00:00",
        "deterministic": True,
        "scenarios": ["solve_baseline"],
        "repeats": 1,
        "policy_profile": "standard",
        "summary": {
            "total_runs": 1,
            "executed_runs": 1,
            "skipped_runs": 0,
            "successful_runs": 1,
            "success_rate": 100.0,
            "avg_duration_sec": 1.0,
            "by_scenario": {
                "solve_baseline": {
                    "executed": 1,
                    "skipped": 0,
                    "success": 1,
                    "success_rate": 100.0,
                }
            },
        },
        "results": [],
    }

    md = eval_harness.build_markdown_summary(
        payload,
        recent_rows=[
            {
                "scenario": "solve_baseline",
                "policy_profile": "standard",
                "skipped": "false",
                "success": "true",
                "iteration": "1",
                "mode": "solve",
                "duration_sec": "1.0",
                "run_id": "solve-1",
                "created_at": "2026-02-14T00:00:00",
            }
        ],
    )
    assert "# Evaluation Summary" in md
    assert "## Aggregate" in md
    assert "## By Scenario" in md
    assert "## Recent Trend Rows" in md
    assert "## Policy Trend" in md
