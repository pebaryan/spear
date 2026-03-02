"""Tests for RDF-backed repair template knowledge."""

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handlers import template_kg  # noqa: E402


def test_get_template_weights_creates_defaults(tmp_path):
    graph_path = tmp_path / "template_knowledge.ttl"
    weights = template_kg.get_template_weights(graph_path)

    assert graph_path.exists()
    assert "off_by_one_fix" in weights
    assert "boundary_guard" in weights
    assert "arithmetic_swap" in weights
    assert "operator_swap" in weights
    assert "generic" in weights
    assert all(float(v) > 0.0 for v in weights.values())


def test_update_template_weights_persists_values(tmp_path):
    graph_path = tmp_path / "template_knowledge.ttl"
    template_kg.update_template_weights(
        weights={"off_by_one_fix": 1.31, "custom_template": 0.92},
        stats={"off_by_one_fix": {"support": 7, "success_rate": 0.8571}},
        source="unit_test",
        eval_file="eval.json",
        min_support=2,
        path=graph_path,
    )

    weights = template_kg.get_template_weights(graph_path)
    assert float(weights["off_by_one_fix"]) == 1.31
    assert float(weights["custom_template"]) == 0.92
