#!/usr/bin/env python3
"""Calibrate deterministic repair template weights from eval runs."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent
for path in (BASE_DIR, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from handlers.run_report import load_report_by_run_id  # noqa: E402
from handlers.template_calibration import (  # noqa: E402
    collect_template_records,
    compute_template_weights,
)
from handlers.template_kg import update_template_weights  # noqa: E402

DEFAULT_EVAL_FILE = BASE_DIR / "evals" / "latest_eval.json"
DEFAULT_OUTPUT_FILE = BASE_DIR / "template_weights.json"
DEFAULT_KG_OUTPUT_FILE = BASE_DIR / "template_knowledge.ttl"


def _load_eval_payload(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate template weights")
    parser.add_argument(
        "--eval-file",
        type=str,
        default=str(DEFAULT_EVAL_FILE),
        help="Path to eval JSON payload",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT_FILE),
        help="Output JSON path for template weights",
    )
    parser.add_argument(
        "--min-support",
        type=int,
        default=2,
        help="Minimum support before a template weight deviates from 1.0",
    )
    parser.add_argument(
        "--kg-output",
        type=str,
        default=str(DEFAULT_KG_OUTPUT_FILE),
        help="Output TTL path for template knowledge graph updates",
    )
    parser.add_argument(
        "--no-kg",
        action="store_true",
        help="Skip writing weights to template knowledge graph",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    eval_path = Path(args.eval_file)
    output_path = Path(args.output)
    kg_output_path = Path(args.kg_output)

    if not eval_path.exists():
        print(f"Eval file not found: {eval_path}")
        return 2

    try:
        payload = _load_eval_payload(eval_path)
    except Exception as exc:
        print(f"Failed to parse eval file: {exc}")
        return 2

    results = payload.get("results", [])
    if not isinstance(results, list):
        print("Invalid eval payload: 'results' is not a list")
        return 2

    records = []
    processed_runs = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        run_id = str(item.get("run_id", "")).strip()
        if not run_id:
            continue
        report = load_report_by_run_id(run_id)
        if not report:
            continue

        success_value = item.get("success")
        if success_value is None:
            success_value = report.get("success", False)
        success = bool(success_value)

        records.extend(collect_template_records(report, success=success))
        processed_runs += 1

    calibration = compute_template_weights(records, min_support=args.min_support)
    output = {
        "generated_at": datetime.now().isoformat(),
        "source_eval_file": str(eval_path),
        "processed_runs": processed_runs,
        "record_count": len(records),
        "min_support": int(args.min_support),
        **calibration,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    kg_updated = False
    if not args.no_kg:
        update_template_weights(
            weights=output["weights"],
            stats=output["stats"],
            source="eval_harness_calibration",
            eval_file=str(eval_path),
            min_support=int(args.min_support),
            path=kg_output_path,
        )
        kg_updated = True

    print(f"Processed runs: {processed_runs}")
    print(f"Template records: {len(records)}")
    print(f"Weights written: {output_path}")
    if kg_updated:
        print(f"Template KG updated: {kg_output_path}")
    for template, weight in sorted(output["weights"].items()):
        stat = output["stats"].get(template, {})
        print(
            f"- {template}: weight={weight} "
            f"support={stat.get('support', 0)} "
            f"success_rate={stat.get('success_rate', 0)}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
