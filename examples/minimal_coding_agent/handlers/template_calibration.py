"""Template calibration helpers for deterministic repair."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple


def parse_templates(value: Any) -> List[str]:
    """Parse template or templates field from report step payload."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = ast.literal_eval(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        return [text]
    return [str(value).strip()]


def collect_template_records(
    report: Dict[str, Any], success: bool
) -> List[Tuple[str, bool]]:
    """Collect (template, success) records from accepted repair steps."""
    steps = report.get("repair_steps", [])
    if not isinstance(steps, list):
        return []

    records: List[Tuple[str, bool]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("event", "")).strip() != "accepted_best_candidate":
            continue

        templates = []
        if "templates" in step:
            templates.extend(parse_templates(step.get("templates")))
        if "template" in step:
            templates.extend(parse_templates(step.get("template")))

        deduped = []
        seen = set()
        for item in templates:
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(key)

        for template in deduped:
            records.append((template, bool(success)))

    return records


def compute_template_weights(
    records: Iterable[Tuple[str, bool]],
    min_support: int = 2,
    floor: float = 0.6,
    ceiling: float = 1.4,
) -> Dict[str, Any]:
    """Compute template weights from historical outcomes."""
    stats = defaultdict(lambda: {"support": 0, "success": 0, "fail": 0})
    for template, succeeded in records:
        row = stats[template]
        row["support"] += 1
        if succeeded:
            row["success"] += 1
        else:
            row["fail"] += 1

    weights: Dict[str, float] = {}
    summary: Dict[str, Dict[str, Any]] = {}

    for template, row in sorted(stats.items()):
        support = int(row["support"])
        success = int(row["success"])
        fail = int(row["fail"])
        success_rate = (success / support) if support else 0.0

        if support < max(1, min_support):
            weight = 1.0
        else:
            # Map [0, 1] success_rate -> [0.75, 1.25]
            weight = 0.75 + (0.5 * success_rate)
            weight = max(float(floor), min(float(ceiling), weight))

        weights[template] = round(weight, 4)
        summary[template] = {
            "support": support,
            "success": success,
            "fail": fail,
            "success_rate": round(success_rate, 4),
            "weight": round(weight, 4),
        }

    return {"weights": weights, "stats": summary}
