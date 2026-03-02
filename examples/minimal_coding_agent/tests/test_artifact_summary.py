"""Tests for artifact diff summary and report integration."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers import artifact_tracker as at  # noqa: E402
from handlers import run_report as rr  # noqa: E402


def test_artifact_tracker_records_line_delta(monkeypatch, tmp_path):
    monkeypatch.setattr(at, "ARTIFACT_LOG_PATH", tmp_path / "artifact_changes.ttl")

    at.log_file_modified(
        "app.py",
        "a\nb\nc\n",
        previous_content="a\nx\n",
        run_id="run-delta-1",
    )

    artifacts = at.get_artifacts_for_run("run-delta-1")
    assert artifacts
    item = artifacts[0]
    assert item.get("operation") == "modified"
    assert item.get("lines_added", 0) >= 1
    assert item.get("lines_removed", 0) >= 1


def test_run_report_roundtrips_artifact_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "REPORT_GRAPH_PATH", tmp_path / "run_reports.ttl")
    rr.save_report(
        {
            "task": "t",
            "command": "solve",
            "run_id": "run-art-1",
            "success": True,
            "artifact_summary": [
                {
                    "file_path": "app.py",
                    "operation": "modified",
                    "lines_added": 3,
                    "lines_removed": 1,
                }
            ],
        }
    )

    report = rr.load_report_by_run_id("run-art-1")
    assert "artifact_summary" in report
    first = report["artifact_summary"][0]
    assert first["file_path"] == "app.py"
    assert first["operation"] == "modified"
    assert int(first["lines_added"]) == 3
    assert int(first["lines_removed"]) == 1
