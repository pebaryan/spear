#!/usr/bin/env python3
"""
Run the conference demo through SPEAR REST API endpoints (/api/v1/*).
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROCESS_FILE = BASE_DIR / "processes" / "risk_routing_demo.bpmn"
DEFAULT_OUTPUT_DIR = BASE_DIR / "expected_outputs"
DEFAULT_DATA_DIR = BASE_DIR / "run_data_api"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run API-mode conference demo")
    parser.add_argument(
        "--mode",
        choices=("inprocess", "http"),
        default="inprocess",
        help="inprocess: uses FastAPI TestClient; http: uses a live base URL",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL when running in --mode http",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Optional API key (X-API-Key) for protected APIs",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for output artifacts (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Storage path for inprocess mode (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset inprocess data dir before execution",
    )
    return parser.parse_args()


class HttpApiClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.headers = {}
        if api_key:
            self.headers["X-API-Key"] = api_key

    def request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}))
        return self.session.request(method, url, headers=headers, timeout=30, **kwargs)


class InprocessApiClient:
    def __init__(self, data_dir: Path, api_key: str, reset: bool):
        if reset and data_dir.exists():
            shutil.rmtree(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        os.environ["SPEAR_USE_FACADE"] = "true"
        os.environ["SPEAR_STORAGE_PATH"] = str(data_dir)
        os.environ.setdefault("AUTH_ENABLED", "false")
        os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

        from src.api.storage import reset_storage

        reset_storage()

        from fastapi.testclient import TestClient
        from src.api.main import app

        self.client = TestClient(app)
        self.headers = {}
        if api_key:
            self.headers["X-API-Key"] = api_key

    def request(self, method: str, path: str, **kwargs):
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}))
        return self.client.request(method, path, headers=headers, **kwargs)


def json_request(client, method: str, path: str, expected_status: int, **kwargs) -> Any:
    response = client.request(method, path, **kwargs)
    if response.status_code != expected_status:
        raise RuntimeError(
            f"{method} {path} -> {response.status_code}, expected {expected_status}. "
            f"Body: {response.text}"
        )
    if response.text:
        return response.json()
    return None


def run_api_demo(client) -> Dict[str, Any]:
    bpmn_content = PROCESS_FILE.read_text(encoding="utf-8")

    # Register built-in function handler used by low-risk auto path.
    json_request(client, "POST", "/api/v1/topics/builtin/calculate_tax", 200)

    process_payload = {
        "name": "Risk Routing Demo API",
        "description": "Conference API-driven demo scenario",
        "version": "1.0.0",
        "bpmn_file": bpmn_content,
    }

    process = json_request(client, "POST", "/api/v1/processes", 201, json=process_payload)
    process_id = process["id"]

    high_payload = {
        "process_id": process_id,
        "variables": {"risk": "high", "customerId": "C-200", "orderTotal": 250.0},
    }
    low_payload = {
        "process_id": process_id,
        "variables": {"risk": "low", "customerId": "C-201", "orderTotal": 100.0},
    }

    high_instance = json_request(client, "POST", "/api/v1/instances", 201, json=high_payload)
    low_instance = json_request(client, "POST", "/api/v1/instances", 201, json=low_payload)

    high_id = high_instance["id"]
    low_id = low_instance["id"]

    high_detail = json_request(client, "GET", f"/api/v1/instances/{high_id}", 200)
    low_detail = json_request(client, "GET", f"/api/v1/instances/{low_id}", 200)
    tasks = json_request(client, "GET", "/api/v1/tasks", 200)
    process_rdf = json_request(client, "GET", f"/api/v1/processes/{process_id}/rdf", 200)

    high_audit = json_request(client, "GET", f"/api/v1/instances/{high_id}/audit-log", 200)
    low_audit = json_request(client, "GET", f"/api/v1/instances/{low_id}/audit-log", 200)

    high_nodes = high_detail.get("current_nodes", [])
    high_node_hit = any("Task_ManualReview" in node for node in high_nodes)
    rdf_text = process_rdf.get("rdf", "")
    has_high_condition = "${risk eq high}" in rdf_text
    has_low_condition = "${risk eq low}" in rdf_text

    checks = {
        "high_instance_running": high_detail.get("status") == "RUNNING",
        "low_instance_completed": low_detail.get("status") == "COMPLETED",
        "manual_review_node_present": high_node_hit,
        "task_created": tasks.get("total", 0) >= 1,
        "flow_high_condition_present": has_high_condition,
        "flow_low_condition_present": has_low_condition,
        "audit_events_present": (
            high_audit.get("total_events", 0) + low_audit.get("total_events", 0)
        )
        >= 2,
    }

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"API demo checks failed: {failed}")

    return {
        "process_id": process_id,
        "high_instance_id": high_id,
        "low_instance_id": low_id,
        "high_status": high_detail.get("status"),
        "low_status": low_detail.get("status"),
        "tasks_total": tasks.get("total", 0),
        "checks": checks,
    }


def write_artifacts(output_dir: Path, summary: Dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "api_latest_run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved artifact:", summary_path)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if args.mode == "inprocess":
        data_dir = Path(args.data_dir).expanduser().resolve()
        client = InprocessApiClient(data_dir=data_dir, api_key=args.api_key, reset=args.reset)
    else:
        client = HttpApiClient(base_url=args.base_url, api_key=args.api_key)

    try:
        summary = run_api_demo(client)
    except Exception as exc:
        print(f"API demo failed: {exc}", file=sys.stderr)
        return 1

    print("\n== API Demo Summary")
    print("process_id:", summary["process_id"])
    print("high_instance:", summary["high_instance_id"], "status=", summary["high_status"])
    print("low_instance :", summary["low_instance_id"], "status=", summary["low_status"])
    print("tasks_total  :", summary["tasks_total"])

    write_artifacts(output_dir, summary)
    print("API conference demo run completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
