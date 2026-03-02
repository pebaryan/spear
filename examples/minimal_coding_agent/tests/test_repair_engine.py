"""Tests for deterministic repair engine helpers."""

import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers import repair  # noqa: E402
from handlers.repair import (  # noqa: E402
    Mutation,
    _extract_suspect_locations,
    _iter_mutations_for_source,
    _mutation_priority,
)


def test_extract_suspect_locations_from_pytest_output(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    output = """
================================== FAILURES ===================================
test_app.py:7: in test_running_average_basic
    assert running_average(10, 2) == 5
app.py:4: in running_average
    return total / (count + 1)
"""
    suspects = _extract_suspect_locations(output, project)
    assert ("test_app.py", 7) in suspects
    assert ("app.py", 4) in suspects


def test_iter_mutations_include_line_numbers():
    source = (
        "def running_average(total, count):\n"
        "    if count < 0:\n"
        "        raise ValueError('bad')\n"
        "    return total / (count + 1)\n"
    )
    mutations = list(_iter_mutations_for_source(Path("app.py"), source))
    assert mutations
    assert all(m.line_no >= 1 for m in mutations)
    assert all(0.0 < float(m.confidence) <= 1.0 for m in mutations)
    assert all(m.template for m in mutations)


def test_iter_mutations_yields_high_confidence_templates():
    source = (
        "def running_average(total, count):\n"
        "    if count < 0:\n"
        "        raise ValueError('bad')\n"
        "    return total / (count + 1)\n"
    )
    mutations = list(_iter_mutations_for_source(Path("app.py"), source))
    templates = {m.template for m in mutations}
    assert "off_by_one_fix" in templates
    assert "boundary_guard" in templates
    assert any(m.template == "off_by_one_fix" and m.confidence >= 0.85 for m in mutations)


def test_mutation_priority_prefers_matching_file_and_line():
    suspects = [("app.py", 10)]
    high = Mutation(
        file_path=Path("app.py"),
        start=0,
        end=1,
        replacement="x",
        description="candidate",
        line_no=10,
    )
    low = Mutation(
        file_path=Path("service.py"),
        start=0,
        end=1,
        replacement="x",
        description="candidate",
        line_no=2,
    )
    assert _mutation_priority(high, suspects) > _mutation_priority(low, suspects)


def test_auto_repair_project_accepts_pair_candidate(monkeypatch, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    file_a = project / "a.py"
    file_b = project / "b.py"
    file_a.write_text("x0", encoding="utf-8")
    file_b.write_text("y0", encoding="utf-8")

    monkeypatch.setattr(repair, "discover_source_files", lambda _dir: [file_a, file_b])
    monkeypatch.setattr(repair, "build_project_context", None)

    def fake_iter(path, _source, template_weights=None):
        if path.name == "a.py":
            return [
                Mutation(
                    file_path=path,
                    start=0,
                    end=2,
                    replacement="x1",
                    description="fix a",
                    line_no=1,
                    confidence=0.8,
                    template="single_a",
                )
            ]
        return [
            Mutation(
                file_path=path,
                start=0,
                end=2,
                replacement="y1",
                description="fix b",
                line_no=1,
                confidence=0.8,
                template="single_b",
            )
        ]

    monkeypatch.setattr(repair, "_iter_mutations_for_source", fake_iter)

    def fake_run(_project_dir):
        a = file_a.read_text(encoding="utf-8")
        b = file_b.read_text(encoding="utf-8")
        if a == "x1" and b == "y1":
            return ("0", "all passed", 0)
        return ("1", "still failing", 10)

    monkeypatch.setattr(repair, "_run_tests", fake_run)

    result = repair.auto_repair_project(project, max_steps=1)
    assert result.success is True
    assert result.applied is True
    assert file_a.read_text(encoding="utf-8") == "x1"
    assert file_b.read_text(encoding="utf-8") == "y1"
    assert any(
        isinstance(step, dict)
        and step.get("event") == "pair_candidate"
        for step in result.steps
    )


def test_load_template_weights_prefers_kg_and_merges_json(monkeypatch, tmp_path):
    json_path = tmp_path / "template_weights.json"
    json_path.write_text(
        json.dumps(
            {
                "weights": {
                    "off_by_one_fix": 0.75,
                    "json_only_template": 1.11,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        repair,
        "get_template_weights_from_kg",
        lambda: {"off_by_one_fix": 1.3, "kg_only_template": 0.9},
    )

    weights = repair.load_template_weights(json_path)
    assert float(weights["off_by_one_fix"]) == 1.3
    assert float(weights["json_only_template"]) == 1.11
    assert float(weights["kg_only_template"]) == 0.9
