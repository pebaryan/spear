#!/usr/bin/env python3
"""
Test script for SPEAR REST API
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from src.api import main as api_main
from src.api.main import app
from src.api.security import _reset_rate_limiter_state_for_tests


@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)


def test_timer_polling_enabled_env(monkeypatch):
    monkeypatch.setenv("SPEAR_TIMER_POLLING_ENABLED", "true")
    assert api_main._timer_polling_enabled() is True
    monkeypatch.setenv("SPEAR_TIMER_POLLING_ENABLED", "false")
    assert api_main._timer_polling_enabled() is False


def test_timer_poll_interval_parsing(monkeypatch):
    monkeypatch.setenv("SPEAR_TIMER_POLL_INTERVAL_SECONDS", "2.5")
    assert api_main._timer_poll_interval_seconds() == 2.5
    monkeypatch.setenv("SPEAR_TIMER_POLL_INTERVAL_SECONDS", "0")
    assert api_main._timer_poll_interval_seconds() == 1.0
    monkeypatch.setenv("SPEAR_TIMER_POLL_INTERVAL_SECONDS", "bad")
    assert api_main._timer_poll_interval_seconds() == 1.0


def test_timer_poller_executes_due_timers(monkeypatch):
    calls = {"count": 0}

    class FakeStorage:
        def run_due_timers(self):
            calls["count"] += 1

    monkeypatch.setattr(api_main, "storage", FakeStorage())

    async def _run():
        stop = asyncio.Event()
        task = asyncio.create_task(api_main._timer_poller(stop, 0.01))
        await asyncio.sleep(0.03)
        stop.set()
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())
    assert calls["count"] >= 1


def test_health_check(client):
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "triple_count" in data


def test_response_includes_observability_and_security_headers(client):
    """Responses should include tracing/perf and baseline security headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")
    assert response.headers.get("X-Process-Time-Ms")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "no-referrer"


def test_api_info(client):
    """Test API info endpoint"""
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "SPEAR BPMN Engine API"
    assert data["version"] == "1.0.0"


def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "endpoints" in data


def test_statistics_endpoint(client):
    """Test statistics endpoint"""
    response = client.get("/statistics")
    assert response.status_code == 200
    data = response.json()
    assert "processes" in data
    assert "instances" in data
    assert "rdf_storage" in data


def test_processes_list_empty(client):
    """Test listing processes when empty"""
    response = client.get("/api/v1/processes")
    assert response.status_code == 200
    data = response.json()
    assert "processes" in data
    assert "total" in data
    assert data["total"] >= 0


def test_instances_list_empty(client):
    """Test listing instances when empty"""
    response = client.get("/api/v1/instances")
    assert response.status_code == 200
    data = response.json()
    assert "instances" in data
    assert "total" in data
    assert data["total"] >= 0


def test_get_nonexistent_process(client):
    """Test getting a process that doesn't exist"""
    response = client.get("/api/v1/processes/nonexistent-id")
    assert response.status_code == 404


def test_get_nonexistent_instance(client):
    """Test getting an instance that doesn't exist"""
    response = client.get("/api/v1/instances/nonexistent-id")
    assert response.status_code == 404


def test_stop_nonexistent_instance(client):
    """Test stopping an instance that doesn't exist"""
    response = client.post(
        "/api/v1/instances/nonexistent-id/stop",
        json={"reason": "Test"}
    )
    assert response.status_code == 404


def test_deploy_and_manage_process(client, sample_bpmn):
    """Test complete process deployment and management lifecycle"""
    # 1. Deploy a process
    response = client.post(
        "/api/v1/processes",
        json={
            "name": "Test Process",
            "description": "A test process",
            "version": "1.0.0",
            "bpmn_file": sample_bpmn
        }
    )
    assert response.status_code == 201
    process_id = response.json()["id"]
    
    # 2. Get the process
    response = client.get(f"/api/v1/processes/{process_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Process"
    
    # 3. List processes
    response = client.get("/api/v1/processes")
    assert response.status_code == 200
    processes = response.json()["processes"]
    assert any(p["id"] == process_id for p in processes)
    
    # 4. Get process RDF
    response = client.get(f"/api/v1/processes/{process_id}/rdf")
    assert response.status_code == 200
    assert "rdf" in response.json()
    
    # 5. Start an instance
    response = client.post(
        "/api/v1/instances",
        json={
            "process_id": process_id,
            "variables": {"test_var": "value"}
        }
    )
    assert response.status_code == 201
    instance_id = response.json()["id"]
    
    # 6. Get instance
    response = client.get(f"/api/v1/instances/{instance_id}")
    assert response.status_code == 200
    assert response.json()["process_id"] == process_id
    
    # 7. Stop instance
    response = client.post(f"/api/v1/instances/{instance_id}/stop")
    assert response.status_code == 200
    assert response.json()["status"] == "TERMINATED"
    
    # 8. Delete process (cleanup)
    response = client.delete(f"/api/v1/processes/{process_id}")
    assert response.status_code == 204


def test_builtin_calculate_tax_registration_and_execution(client):
    """Test built-in calculate_tax handler can be registered and executed."""
    response = client.post("/api/v1/topics/builtin/calculate_tax")
    assert response.status_code == 200

    response = client.post(
        "/api/v1/topics/calculate_tax/test",
        json={"variables": {"orderTotal": 100}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["output_variables"]["taxAmount"] == 10.0
    assert data["output_variables"]["taxRate"] == 0.10


def test_api_rate_limit_blocks_excess_requests(client, monkeypatch):
    """Rate limiter should return 429 when request budget is exceeded."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    _reset_rate_limiter_state_for_tests()

    try:
        assert client.get("/api/v1/processes").status_code == 200
        assert client.get("/api/v1/processes").status_code == 200

        response = client.get("/api/v1/processes")
        assert response.status_code == 429
        assert response.headers.get("Retry-After")
    finally:
        _reset_rate_limiter_state_for_tests()


# Sample BPMN for testing
@pytest.fixture
def sample_bpmn():
    """Provide a sample BPMN XML for testing"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             id="Definitions_1"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="StartEvent_1" name="Start">
      <outgoing>Flow_1</outgoing>
    </startEvent>
    <endEvent id="EndEvent_1" name="End">
      <incoming>Flow_1</incoming>
    </endEvent>
    <sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="EndEvent_1" />
  </process>
</definitions>"""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
