"""Tests for CI profile helpers."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ci_profile  # noqa: E402


def test_parse_args_defaults():
    args = ci_profile.parse_args([])
    assert args.repeats == 1
    assert args.skip_tests is False
    assert args.skip_eval is False


def test_build_profile_aggregates_step_success():
    steps = [
        {"name": "tests", "success": True},
        {"name": "eval", "success": False},
    ]
    latest_eval = {
        "summary": {
            "total_runs": 2,
            "executed_runs": 2,
            "skipped_runs": 0,
            "successful_runs": 1,
            "success_rate": 50.0,
            "avg_duration_sec": 1.2,
        }
    }
    profile = ci_profile.build_profile(
        created_at="2026-02-14T00:00:00",
        python_version="3.11.0",
        platform="win32",
        steps=steps,
        latest_eval=latest_eval,
    )
    assert profile["success"] is False
    assert profile["steps_total"] == 2
    assert profile["steps_passed"] == 1
    assert profile["eval_summary"]["success_rate"] == 50.0


def test_render_markdown_contains_sections():
    profile = {
        "created_at": "2026-02-14T00:00:00",
        "python_version": "3.11.0",
        "platform": "linux",
        "success": True,
        "steps_total": 1,
        "steps_passed": 1,
        "steps": [{"name": "minimal_tests", "exit_code": 0, "duration_sec": 1.0, "success": True}],
        "eval_summary": {
            "total_runs": 1,
            "executed_runs": 1,
            "skipped_runs": 0,
            "successful_runs": 1,
            "success_rate": 100.0,
            "avg_duration_sec": 1.0,
        },
    }
    md = ci_profile.render_markdown(profile)
    assert "# CI Profile Summary" in md
    assert "## Steps" in md
    assert "## Eval Snapshot" in md
