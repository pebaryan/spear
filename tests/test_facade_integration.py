# Integration Tests for StorageFacade
# Tests complete process execution through the facade

import pytest
import threading
from rdflib import Graph, Literal, RDF, URIRef

from src.api.storage.facade import StorageFacade, reset_facade
from src.api.storage.base import PROC, BPMN, INST


# Sample BPMN XML for testing
SIMPLE_PROCESS_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  id="Definitions_1">
  <bpmn:process id="simple_process" isExecutable="true">
    <bpmn:startEvent id="start_1" name="Start">
      <bpmn:outgoing>flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:serviceTask id="task_1" name="Calculate Tax">
      <bpmn:incoming>flow_1</bpmn:incoming>
      <bpmn:outgoing>flow_2</bpmn:outgoing>
    </bpmn:serviceTask>
    <bpmn:endEvent id="end_1" name="End">
      <bpmn:incoming>flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="flow_1" sourceRef="start_1" targetRef="task_1"/>
    <bpmn:sequenceFlow id="flow_2" sourceRef="task_1" targetRef="end_1"/>
  </bpmn:process>
</bpmn:definitions>
"""

# Process with user task that will wait for completion
USER_TASK_PROCESS_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="Definitions_2">
  <bpmn:process id="user_task_process" isExecutable="true">
    <bpmn:startEvent id="start_1" name="Start">
      <bpmn:outgoing>flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:userTask id="user_task_1" name="Review Order">
      <bpmn:incoming>flow_1</bpmn:incoming>
      <bpmn:outgoing>flow_2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="end_1" name="End">
      <bpmn:incoming>flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="flow_1" sourceRef="start_1" targetRef="user_task_1"/>
    <bpmn:sequenceFlow id="flow_2" sourceRef="user_task_1" targetRef="end_1"/>
  </bpmn:process>
</bpmn:definitions>
"""


@pytest.fixture
def facade(tmp_path):
    """Create a fresh facade for each test."""
    reset_facade()
    return StorageFacade(str(tmp_path))


class TestProcessDeployment:
    """Tests for deploying processes via facade."""

    def test_deploy_simple_process(self, facade):
        """Test deploying a simple BPMN process."""
        # deploy_process returns the process ID string (generated UUID)
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        assert process_id is not None
        assert isinstance(process_id, str)
        assert len(process_id) > 0

    def test_get_deployed_process(self, facade):
        """Test retrieving a deployed process."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        process = facade.get_process(process_id)

        assert process is not None
        assert process["id"] == process_id

    def test_list_deployed_processes(self, facade):
        """Test listing deployed processes."""
        facade.deploy_process("Process 1", SIMPLE_PROCESS_BPMN, version="1.0")
        facade.deploy_process("Process 2", SIMPLE_PROCESS_BPMN, version="1.0")

        result = facade.list_processes()

        assert result["total"] >= 2

    def test_delete_process(self, facade):
        """Test deleting a process."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        result = facade.delete_process(process_id)

        assert result is True
        assert facade.get_process(process_id) is None


class TestInstanceCreation:
    """Tests for creating process instances via facade."""

    def test_create_instance_without_deploy(self, facade):
        """Test that creating instance fails without process."""
        with pytest.raises(ValueError, match="not found"):
            facade.create_instance("nonexistent_process")

    def test_create_instance_with_variables(self, facade):
        """Test creating instance with initial variables."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        result = facade.create_instance(
            process_id, variables={"orderId": "123", "amount": "99.99"}
        )

        assert result is not None
        assert result["status"] == "RUNNING"
        assert result["variables"]["orderId"] == "123"
        assert result["variables"]["amount"] == "99.99"

    def test_get_instance_after_creation(self, facade):
        """Test retrieving an instance after creation."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        result = facade.create_instance(process_id)

        instance = facade.get_instance(result["id"])

        assert instance is not None
        assert instance["id"] == result["id"]

    def test_list_instances_after_creation(self, facade):
        """Test listing instances after creating some."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        facade.create_instance(process_id)
        facade.create_instance(process_id)

        result = facade.list_instances()

        assert result["total"] >= 2


class TestVariableManagement:
    """Tests for variable management via facade."""

    def test_set_and_get_variable(self, facade):
        """Test setting and getting a variable."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        instance = facade.create_instance(process_id)

        facade.set_instance_variable(instance["id"], "customVar", "customValue")

        variables = facade.get_instance_variables(instance["id"])
        assert variables["customVar"] == "customValue"

    def test_update_existing_variable(self, facade):
        """Test updating an existing variable."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        instance = facade.create_instance(process_id, variables={"counter": "1"})

        facade.set_instance_variable(instance["id"], "counter", "2")

        variables = facade.get_instance_variables(instance["id"])
        assert variables["counter"] == "2"


class TestInstanceLifecycle:
    """Tests for instance lifecycle management via facade."""

    def test_stop_instance(self, facade):
        """Test stopping a running instance."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        instance = facade.create_instance(process_id)

        result = facade.stop_instance(instance["id"], "Test stop")

        assert result["status"] == "TERMINATED"

    def test_cancel_instance(self, facade):
        """Test cancelling an instance."""
        # Use user task process which will wait at the user task
        process_id = facade.deploy_process(
            name="User Task Process", bpmn_content=USER_TASK_PROCESS_BPMN, version="1.0"
        )
        instance = facade.create_instance(process_id)

        # Instance should be running (waiting at user task)
        instance_data = facade.get_instance(instance["id"])
        assert instance_data["status"] == "RUNNING"

        result = facade.cancel_instance(instance["id"], "Test cancel")

        assert result["status"] == "CANCELLED"

    def test_cannot_cancel_completed_instance(self, facade):
        """Test that completed instances cannot be cancelled."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        instance = facade.create_instance(process_id)

        # First stop it
        facade.stop_instance(instance["id"])

        # Try to cancel - should fail
        with pytest.raises(ValueError, match="already"):
            facade.cancel_instance(instance["id"])


class TestAuditLog:
    """Tests for audit log via facade."""

    def test_get_audit_log_after_creation(self, facade):
        """Test that audit log has CREATED event."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        instance = facade.create_instance(process_id)

        log = facade.get_instance_audit_log(instance["id"])

        # Should have at least a CREATED event
        assert len(log) >= 1
        # Audit repository returns "type" not "event_type"
        event_types = [e["type"] for e in log]
        assert "CREATED" in event_types

    def test_get_audit_log_after_stop(self, facade):
        """Test that audit log has TERMINATED event after stop."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        instance = facade.create_instance(process_id)
        facade.stop_instance(instance["id"], "Test stop")

        log = facade.get_instance_audit_log(instance["id"])

        # Audit repository returns "type" not "event_type"
        event_types = [e["type"] for e in log]
        assert "TERMINATED" in event_types


class TestAdvancedNodeHandlers:
    """Integration tests for advanced node categories wired via facade."""

    def test_execute_expanded_subprocess_handler(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="p1" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:subProcess id="sub1">
      <bpmn:startEvent id="subStart"/>
      <bpmn:serviceTask id="subTask" camunda:topic="sub_task"/>
      <bpmn:endEvent id="subEnd"/>
      <bpmn:sequenceFlow id="sf1" sourceRef="subStart" targetRef="subTask"/>
      <bpmn:sequenceFlow id="sf2" sourceRef="subTask" targetRef="subEnd"/>
    </bpmn:subProcess>
    <bpmn:endEvent id="end1"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="sub1"/>
    <bpmn:sequenceFlow id="f2" sourceRef="sub1" targetRef="end1"/>
  </bpmn:process>
</bpmn:definitions>"""

        called = []

        def sub_task_handler(instance_id, variables):
            called.append(instance_id)
            return {"ok": True}

        facade.register_topic_handler("sub_task", sub_task_handler)
        process_id = facade.deploy_process("Expanded", bpmn, version="1.0")
        instance = facade.create_instance(process_id)
        data = facade.get_instance(instance["id"])

        assert data["status"] == "COMPLETED"
        assert len(called) == 1

    def test_execute_call_activity_handler(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="mainProcess" isExecutable="true">
    <bpmn:startEvent id="mainStart"/>
    <bpmn:callActivity id="call1" calledElement="calledProc"/>
    <bpmn:endEvent id="mainEnd"/>
    <bpmn:sequenceFlow id="cf1" sourceRef="mainStart" targetRef="call1"/>
    <bpmn:sequenceFlow id="cf2" sourceRef="call1" targetRef="mainEnd"/>
  </bpmn:process>
  <bpmn:process id="calledProc" isExecutable="false">
    <bpmn:startEvent id="calledStart"/>
    <bpmn:serviceTask id="calledTask" camunda:topic="called_task"/>
    <bpmn:endEvent id="calledEnd"/>
    <bpmn:sequenceFlow id="cf3" sourceRef="calledStart" targetRef="calledTask"/>
    <bpmn:sequenceFlow id="cf4" sourceRef="calledTask" targetRef="calledEnd"/>
  </bpmn:process>
</bpmn:definitions>"""

        called = []

        def called_task_handler(instance_id, variables):
            called.append(instance_id)
            return {"ok": True}

        facade.register_topic_handler("called_task", called_task_handler)
        process_id = facade.deploy_process("Call Activity", bpmn, version="1.0")
        instance = facade.create_instance(process_id)
        data = facade.get_instance(instance["id"])

        assert data["status"] == "COMPLETED"
        assert len(called) == 1

    def test_call_activity_variable_mapping_and_lifecycle(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="mainProcess" isExecutable="true">
    <bpmn:startEvent id="mainStart"/>
    <bpmn:callActivity id="call1" calledElement="calledProc" bpmn:inVariables="orderId,amount" bpmn:outVariables="approvalCode"/>
    <bpmn:endEvent id="mainEnd"/>
    <bpmn:sequenceFlow id="cf1" sourceRef="mainStart" targetRef="call1"/>
    <bpmn:sequenceFlow id="cf2" sourceRef="call1" targetRef="mainEnd"/>
  </bpmn:process>
  <bpmn:process id="calledProc" isExecutable="false">
    <bpmn:startEvent id="calledStart"/>
    <bpmn:serviceTask id="calledTask" camunda:topic="called_task"/>
    <bpmn:endEvent id="calledEnd"/>
    <bpmn:sequenceFlow id="cf3" sourceRef="calledStart" targetRef="calledTask"/>
    <bpmn:sequenceFlow id="cf4" sourceRef="calledTask" targetRef="calledEnd"/>
  </bpmn:process>
</bpmn:definitions>"""

        seen = []

        def called_task_handler(instance_id, variables):
            seen.append(dict(variables))
            return {"approvalCode": f"OK-{variables.get('orderId', 'NA')}"}

        facade.register_topic_handler("called_task", called_task_handler)
        process_id = facade.deploy_process("Call Mapping", bpmn, version="1.0")
        instance = facade.create_instance(
            process_id,
            variables={"orderId": "O-1", "amount": "12.5", "ignored": "x"},
        )

        vars_after = facade.get_instance_variables(instance["id"])
        assert vars_after["approvalCode"] == "OK-O-1"
        assert len(seen) == 1
        assert seen[0]["orderId"] == "O-1"
        assert seen[0]["amount"] == "12.5"
        assert "ignored" not in seen[0]

        instance_uri = URIRef(f"http://example.org/instance/{instance['id']}")
        call_execs = list(
            facade.instances_graph.objects(
                instance_uri, URIRef("http://example.org/instance/hasCallExecution")
            )
        )
        assert len(call_execs) == 1
        call_exec = call_execs[0]
        status = facade.instances_graph.value(
            call_exec, URIRef("http://example.org/instance/status")
        )
        copied_in = facade.instances_graph.value(
            call_exec, URIRef("http://example.org/instance/copiedInCount")
        )
        copied_out = facade.instances_graph.value(
            call_exec, URIRef("http://example.org/instance/copiedOutCount")
        )
        assert str(status) == "COMPLETED"
        assert str(copied_in) == "2"
        assert str(copied_out) == "1"

    def test_event_subprocess_triggers_on_message(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="proc1" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSub" triggeredByEvent="true">
      <bpmn:startEvent id="eventStart">
        <bpmn:messageEventDefinition camunda:message="kickoff"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="eventStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        calls = []

        def event_task_handler(instance_id, variables):
            calls.append((instance_id, dict(variables)))
            return {"eventDone": "yes"}

        facade.register_topic_handler("event_task", event_task_handler)
        process_id = facade.deploy_process("Event Subprocess", bpmn, version="1.0")
        instance = facade.create_instance(process_id, variables={"seed": "A"})

        result = facade.send_message(
            "kickoff",
            correlation_key=instance["id"],
            variables={"msgVar": "B"},
        )

        assert len(calls) == 1
        assert calls[0][1]["seed"] == "A"
        assert calls[0][1]["msgVar"] == "B"
        assert instance["id"] in result.get("event_subprocess_triggers", [])

    def test_event_subprocess_triggers_on_timer(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procTimer" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSubTimer" triggeredByEvent="true">
      <bpmn:startEvent id="timerStart">
        <bpmn:timerEventDefinition/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTimerTask" camunda:topic="event_timer_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="timerStart" targetRef="eventTimerTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTimerTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        calls = []

        def event_timer_task_handler(instance_id, variables):
            calls.append((instance_id, dict(variables)))
            return {"timerDone": "yes"}

        facade.register_topic_handler("event_timer_task", event_timer_task_handler)
        process_id = facade.deploy_process("Event Subprocess Timer", bpmn, version="1.0")

        timer_start_uri = URIRef("http://example.org/bpmn/timerStart")
        facade.definitions_graph.add(
            (
                timer_start_uri,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#timerDelaySeconds"),
                Literal("0"),
            )
        )

        instance = facade.create_instance(process_id, variables={"seed": "T"})
        data = facade.get_instance(instance["id"])

        assert data["status"] == "RUNNING"
        assert len(calls) == 1
        assert calls[0][1]["seed"] == "T"

    def test_timer_intermediate_catch_and_run_due_timers(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="timerProc" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:intermediateCatchEvent id="waitTimer"/>
    <bpmn:serviceTask id="afterTimerTask" camunda:topic="after_timer"/>
    <bpmn:endEvent id="end1"/>
    <bpmn:sequenceFlow id="t1" sourceRef="start1" targetRef="waitTimer"/>
    <bpmn:sequenceFlow id="t2" sourceRef="waitTimer" targetRef="afterTimerTask"/>
    <bpmn:sequenceFlow id="t3" sourceRef="afterTimerTask" targetRef="end1"/>
  </bpmn:process>
</bpmn:definitions>"""

        called = []

        def after_timer_handler(instance_id, variables):
            called.append(instance_id)
            return {"ok": True}

        facade.register_topic_handler("after_timer", after_timer_handler)
        process_id = facade.deploy_process("Timer Process", bpmn, version="1.0")

        # Mark catch event as timer-backed and immediate due.
        wait_timer_uri = URIRef("http://example.org/bpmn/waitTimer")
        timer_def_uri = URIRef("http://example.org/bpmn/timer_def_test")
        facade.definitions_graph.add(
            (
                timer_def_uri,
                RDF.type,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#timerEventDefinition"),
            )
        )
        facade.definitions_graph.add(
            (
                timer_def_uri,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#hasParent"),
                wait_timer_uri,
            )
        )
        facade.definitions_graph.add(
            (
                wait_timer_uri,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#timerDelaySeconds"),
                Literal("0"),
            )
        )

        instance = facade.create_instance(process_id)
        before = facade.get_instance(instance["id"])
        assert before["status"] == "RUNNING"

        fired = facade.run_due_timers()
        after = facade.get_instance(instance["id"])

        assert fired["fired"] >= 1
        assert after["status"] == "COMPLETED"
        assert len(called) == 1

    def test_send_task_handler_completes_process(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="sendProc" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:sendTask id="send1" camunda:message="order.sent"/>
    <bpmn:endEvent id="end1"/>
    <bpmn:sequenceFlow id="s1" sourceRef="start1" targetRef="send1"/>
    <bpmn:sequenceFlow id="s2" sourceRef="send1" targetRef="end1"/>
  </bpmn:process>
</bpmn:definitions>"""
        process_id = facade.deploy_process("Send Task", bpmn, version="1.0")
        instance = facade.create_instance(process_id)
        data = facade.get_instance(instance["id"])
        assert data["status"] == "COMPLETED"

    def test_manual_task_handler_completes_process(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="manualProc" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:manualTask id="manual1"/>
    <bpmn:endEvent id="end1"/>
    <bpmn:sequenceFlow id="m1" sourceRef="start1" targetRef="manual1"/>
    <bpmn:sequenceFlow id="m2" sourceRef="manual1" targetRef="end1"/>
  </bpmn:process>
</bpmn:definitions>"""
        process_id = facade.deploy_process("Manual Task", bpmn, version="1.0")
        instance = facade.create_instance(process_id)
        data = facade.get_instance(instance["id"])
        assert data["status"] == "COMPLETED"

    def test_run_due_timers_multi_worker_claims_once(self, tmp_path):
        facade_a = StorageFacade(str(tmp_path))

        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="timerProcConcurrent" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:intermediateCatchEvent id="waitTimer"/>
    <bpmn:serviceTask id="afterTimerTask" camunda:topic="after_timer_concurrent"/>
    <bpmn:endEvent id="end1"/>
    <bpmn:sequenceFlow id="t1" sourceRef="start1" targetRef="waitTimer"/>
    <bpmn:sequenceFlow id="t2" sourceRef="waitTimer" targetRef="afterTimerTask"/>
    <bpmn:sequenceFlow id="t3" sourceRef="afterTimerTask" targetRef="end1"/>
  </bpmn:process>
</bpmn:definitions>"""

        call_count = {"count": 0}
        counter_lock = threading.Lock()

        def after_timer_handler(instance_id, variables):
            with counter_lock:
                call_count["count"] += 1
            return {"ok": True}

        facade_a.register_topic_handler("after_timer_concurrent", after_timer_handler)

        process_id = facade_a.deploy_process("Timer Concurrent", bpmn, version="1.0")
        wait_timer_uri = URIRef("http://example.org/bpmn/waitTimer")
        timer_def_uri = URIRef("http://example.org/bpmn/timer_def_concurrent")
        facade_a.definitions_graph.add(
            (
                timer_def_uri,
                RDF.type,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#timerEventDefinition"),
            )
        )
        facade_a.definitions_graph.add(
            (
                timer_def_uri,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#hasParent"),
                wait_timer_uri,
            )
        )
        facade_a.definitions_graph.add(
            (
                wait_timer_uri,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#timerDelaySeconds"),
                Literal("0"),
            )
        )
        facade_a.save_definitions()

        facade_b = StorageFacade(str(tmp_path))
        facade_b.register_topic_handler("after_timer_concurrent", after_timer_handler)

        instance = facade_a.create_instance(process_id)

        results = []
        start_barrier = threading.Barrier(2)

        def _run_worker(local_facade, worker_name):
            start_barrier.wait()
            results.append(local_facade.run_due_timers(worker_id=worker_name))

        t1 = threading.Thread(target=_run_worker, args=(facade_a, "worker-a"))
        t2 = threading.Thread(target=_run_worker, args=(facade_b, "worker-b"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert sum(r["fired"] for r in results) == 1
        assert call_count["count"] == 1

        verifier = StorageFacade(str(tmp_path))
        final_instance = verifier.get_instance(instance["id"])
        assert final_instance["status"] == "COMPLETED"

    def test_run_due_timers_reclaims_expired_lease(self, tmp_path):
        facade = StorageFacade(str(tmp_path))

        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="timerProcLease" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:intermediateCatchEvent id="waitTimer"/>
    <bpmn:serviceTask id="afterTimerTask" camunda:topic="after_timer_lease"/>
    <bpmn:endEvent id="end1"/>
    <bpmn:sequenceFlow id="t1" sourceRef="start1" targetRef="waitTimer"/>
    <bpmn:sequenceFlow id="t2" sourceRef="waitTimer" targetRef="afterTimerTask"/>
    <bpmn:sequenceFlow id="t3" sourceRef="afterTimerTask" targetRef="end1"/>
  </bpmn:process>
</bpmn:definitions>"""

        call_count = {"count": 0}

        def after_timer_handler(instance_id, variables):
            call_count["count"] += 1
            return {"ok": True}

        facade.register_topic_handler("after_timer_lease", after_timer_handler)
        process_id = facade.deploy_process("Timer Lease", bpmn, version="1.0")
        wait_timer_uri = URIRef("http://example.org/bpmn/waitTimer")
        timer_def_uri = URIRef("http://example.org/bpmn/timer_def_lease")
        facade.definitions_graph.add(
            (
                timer_def_uri,
                RDF.type,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#timerEventDefinition"),
            )
        )
        facade.definitions_graph.add(
            (
                timer_def_uri,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#hasParent"),
                wait_timer_uri,
            )
        )
        facade.definitions_graph.add(
            (
                wait_timer_uri,
                URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#timerDelaySeconds"),
                Literal("0"),
            )
        )
        facade.save_definitions()

        instance = facade.create_instance(process_id)
        instance_uri = URIRef(f"http://example.org/instance/{instance['id']}")
        job_uri = next(facade.instances_graph.objects(instance_uri, INST.hasTimerJob))

        facade.instances_graph.set((job_uri, INST.timerStatus, Literal("CLAIMED")))
        facade.instances_graph.set((job_uri, INST.claimedBy, Literal("stale-worker")))
        facade.instances_graph.set((job_uri, INST.claimedAt, Literal("2020-01-01T00:00:00")))
        facade.instances_graph.set((job_uri, INST.leaseUntil, Literal("2020-01-01T00:00:01")))
        facade.save_instances()

        result = facade.run_due_timers(worker_id="new-worker")

        assert result["fired"] == 1
        assert call_count["count"] == 1
        refreshed = StorageFacade(str(tmp_path))
        final_instance = refreshed.get_instance(instance["id"])
        assert final_instance["status"] == "COMPLETED"

    def test_event_subprocess_triggers_on_error_variant(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procErr" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSubErr" triggeredByEvent="true">
      <bpmn:startEvent id="errorStart">
        <bpmn:errorEventDefinition id="errDef"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_error_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="errorStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        calls = []

        def event_error_handler(instance_id, variables):
            calls.append((instance_id, dict(variables)))
            return {"eventDone": "yes"}

        facade.register_topic_handler("event_error_task", event_error_handler)
        process_id = facade.deploy_process("Event Subprocess Error", bpmn, version="1.0")
        instance = facade.create_instance(process_id, variables={"seed": "E"})

        start_uri = URIRef("http://example.org/bpmn/errorStart")
        for child in facade.definitions_graph.subjects(BPMN.hasParent, start_uri):
            for _, _, child_type in facade.definitions_graph.triples((child, RDF.type, None)):
                if "erroreventdefinition" in str(child_type).lower():
                    facade.definitions_graph.set((child, BPMN.errorRef, Literal("E-ORDER")))
                    break
        facade.save_definitions()

        result = facade.throw_error(
            instance["id"],
            "E-ORDER",
            error_message="bad order",
            variables={"errSource": "api"},
        )

        assert result["triggered"] is True
        assert result["count"] == 1
        assert len(calls) == 1
        assert calls[0][1]["seed"] == "E"
        assert calls[0][1]["errorCode"] == "E-ORDER"
        assert calls[0][1]["errSource"] == "api"

    def test_event_subprocess_triggers_on_signal_variant(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procSignal" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSubSignal" triggeredByEvent="true">
      <bpmn:startEvent id="signalStart">
        <bpmn:signalEventDefinition id="sigDef"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_signal_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="signalStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        calls = []

        def event_signal_handler(instance_id, variables):
            calls.append((instance_id, dict(variables)))
            return {"eventDone": "yes"}

        facade.register_topic_handler("event_signal_task", event_signal_handler)
        process_id = facade.deploy_process("Event Subprocess Signal", bpmn, version="1.0")
        instance = facade.create_instance(process_id, variables={"seed": "S"})

        start_uri = URIRef("http://example.org/bpmn/signalStart")
        for child in facade.definitions_graph.subjects(BPMN.hasParent, start_uri):
            for _, _, child_type in facade.definitions_graph.triples((child, RDF.type, None)):
                if "signaleventdefinition" in str(child_type).lower():
                    facade.definitions_graph.set((child, BPMN.signalRef, Literal("SIG-KICKOFF")))
                    break
        facade.save_definitions()

        result = facade.throw_signal(
            "SIG-KICKOFF",
            correlation_key=instance["id"],
            variables={"sigPayload": "x"},
        )

        assert instance["id"] in result["triggered_instances"]
        assert len(calls) == 1
        assert calls[0][1]["seed"] == "S"
        assert calls[0][1]["sigPayload"] == "x"

    def test_event_subprocess_triggers_on_escalation_variant(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procEsc" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSubEsc" triggeredByEvent="true">
      <bpmn:startEvent id="escStart">
        <bpmn:escalationEventDefinition id="escDef"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_escalation_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="escStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        calls = []

        def event_escalation_handler(instance_id, variables):
            calls.append((instance_id, dict(variables)))
            return {"eventDone": "yes"}

        facade.register_topic_handler("event_escalation_task", event_escalation_handler)
        process_id = facade.deploy_process("Event Subprocess Escalation", bpmn, version="1.0")
        instance = facade.create_instance(process_id, variables={"seed": "C"})

        start_uri = URIRef("http://example.org/bpmn/escStart")
        for child in facade.definitions_graph.subjects(BPMN.hasParent, start_uri):
            for _, _, child_type in facade.definitions_graph.triples((child, RDF.type, None)):
                if "escalationeventdefinition" in str(child_type).lower():
                    facade.definitions_graph.set((child, BPMN.escalationRef, Literal("ESC-1")))
                    break
        facade.save_definitions()

        result = facade.throw_escalation(
            instance["id"],
            "ESC-1",
            variables={"escalatedBy": "policy"},
        )

        assert result["triggered"] is True
        assert result["count"] == 1
        assert len(calls) == 1
        assert calls[0][1]["seed"] == "C"
        assert calls[0][1]["escalationCode"] == "ESC-1"
        assert calls[0][1]["escalatedBy"] == "policy"

    def test_event_subprocess_triggers_on_conditional_variant(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procCond" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSubCond" triggeredByEvent="true">
      <bpmn:startEvent id="condStart">
        <bpmn:conditionalEventDefinition id="condDef"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_conditional_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="condStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        calls = []

        def event_conditional_handler(instance_id, variables):
            calls.append((instance_id, dict(variables)))
            return {"eventDone": "yes"}

        facade.register_topic_handler("event_conditional_task", event_conditional_handler)
        process_id = facade.deploy_process("Event Subprocess Conditional", bpmn, version="1.0")
        instance = facade.create_instance(process_id, variables={"seed": "Q"})

        start_uri = URIRef("http://example.org/bpmn/condStart")
        for child in facade.definitions_graph.subjects(BPMN.hasParent, start_uri):
            for _, _, child_type in facade.definitions_graph.triples((child, RDF.type, None)):
                if "conditionaleventdefinition" in str(child_type).lower():
                    facade.definitions_graph.set(
                        (child, BPMN.conditionExpression, Literal("kickoff"))
                    )
                    break
        facade.save_definitions()

        result = facade.trigger_conditional_event_subprocesses(
            instance["id"],
            variables={"kickoff": True},
        )

        assert result["triggered"] is True
        assert result["count"] == 1
        assert len(calls) == 1
        assert calls[0][1]["seed"] == "Q"
        assert str(calls[0][1]["kickoff"]).lower() == "true"

    def test_event_subprocess_unsupported_variant_is_auditable(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procUnsup" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSubUnsup" triggeredByEvent="true">
      <bpmn:startEvent id="unsupStart">
        <bpmn:compensateEventDefinition id="compDef"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_unsup_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="unsupStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        facade.register_topic_handler("event_unsup_task", lambda i, v: {"ok": True})
        process_id = facade.deploy_process("Event Subprocess Unsupported", bpmn, version="1.0")
        instance = facade.create_instance(process_id)

        result = facade.throw_signal("SIG-NONE", correlation_key=instance["id"])
        assert instance["id"] not in result["triggered_instances"]

        audit = facade.get_instance_audit_log(instance["id"])
        event_types = [entry["type"] for entry in audit]
        assert "EVENT_SUBPROCESS_START_UNSUPPORTED" in event_types

    def test_event_subprocess_non_interrupting_keeps_parent_token_active(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procNonInterrupt" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSub" triggeredByEvent="true">
      <bpmn:startEvent id="msgStart">
        <bpmn:messageEventDefinition camunda:message="kickoff.nonint"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_nonint_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="msgStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        facade.register_topic_handler("event_nonint_task", lambda i, v: {"ok": True})
        process_id = facade.deploy_process("Event Non Interrupting", bpmn, version="1.0")
        instance = facade.create_instance(process_id)

        msg_start_uri = URIRef("http://example.org/bpmn/msgStart")
        facade.definitions_graph.set((msg_start_uri, BPMN.interrupting, Literal("false")))
        facade.save_definitions()

        facade.send_message("kickoff.nonint", correlation_key=instance["id"])

        instance_uri = URIRef(f"http://example.org/instance/{instance['id']}")
        wait_task_uri = URIRef("http://example.org/bpmn/waitTask")
        statuses = []
        for tok in facade.instances_graph.objects(instance_uri, INST.hasToken):
            node = facade.instances_graph.value(tok, INST.currentNode)
            if node == wait_task_uri:
                statuses.append(str(facade.instances_graph.value(tok, INST.status)))
        assert "WAITING" in statuses

    def test_event_subprocess_interrupting_consumes_parent_scope_tokens(self, facade):
        bpmn = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
  <bpmn:process id="procInterrupt" isExecutable="true">
    <bpmn:startEvent id="start1"/>
    <bpmn:userTask id="waitTask"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start1" targetRef="waitTask"/>
    <bpmn:subProcess id="eventSub" triggeredByEvent="true">
      <bpmn:startEvent id="msgStart">
        <bpmn:messageEventDefinition camunda:message="kickoff.int"/>
      </bpmn:startEvent>
      <bpmn:serviceTask id="eventTask" camunda:topic="event_int_task"/>
      <bpmn:endEvent id="eventEnd"/>
      <bpmn:sequenceFlow id="ef1" sourceRef="msgStart" targetRef="eventTask"/>
      <bpmn:sequenceFlow id="ef2" sourceRef="eventTask" targetRef="eventEnd"/>
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""

        facade.register_topic_handler("event_int_task", lambda i, v: {"ok": True})
        process_id = facade.deploy_process("Event Interrupting", bpmn, version="1.0")
        instance = facade.create_instance(process_id)

        msg_start_uri = URIRef("http://example.org/bpmn/msgStart")
        facade.definitions_graph.set((msg_start_uri, BPMN.interrupting, Literal("true")))
        facade.save_definitions()

        facade.send_message("kickoff.int", correlation_key=instance["id"])

        instance_uri = URIRef(f"http://example.org/instance/{instance['id']}")
        wait_task_uri = URIRef("http://example.org/bpmn/waitTask")
        statuses = []
        for tok in facade.instances_graph.objects(instance_uri, INST.hasToken):
            node = facade.instances_graph.value(tok, INST.currentNode)
            if node == wait_task_uri:
                statuses.append(str(facade.instances_graph.value(tok, INST.status)))
        assert statuses
        assert all(status == "CONSUMED" for status in statuses)

        audit = facade.get_instance_audit_log(instance["id"])
        event_types = [entry["type"] for entry in audit]
        assert "EVENT_SUBPROCESS_INTERRUPTED_SCOPE" in event_types


class TestServiceTaskRegistration:
    """Tests for service task handler registration via facade."""

    def test_register_handler(self, facade):
        """Test registering a service task handler."""

        def my_handler(context):
            return {"result": "done"}

        facade.register_service_task_handler("my_topic", my_handler)

        handler = facade.get_service_task_handler("my_topic")
        assert handler is my_handler

    def test_unregister_handler(self, facade):
        """Test unregistering a service task handler."""

        def my_handler(context):
            pass

        facade.register_service_task_handler("my_topic", my_handler)
        result = facade.unregister_service_task_handler("my_topic")

        assert result is True
        assert facade.get_service_task_handler("my_topic") is None

    def test_handler_not_found(self, facade):
        """Test getting non-existent handler."""
        handler = facade.get_service_task_handler("nonexistent")
        assert handler is None


class TestComponentAccess:
    """Tests for accessing facade components."""

    def test_access_definitions_graph(self, facade):
        """Test accessing definitions graph."""
        assert facade.definitions_graph is not None
        assert isinstance(facade.definitions_graph, Graph)

    def test_access_instances_graph(self, facade):
        """Test accessing instances graph."""
        assert facade.instances_graph is not None
        assert isinstance(facade.instances_graph, Graph)

    def test_access_audit_graph(self, facade):
        """Test accessing audit graph."""
        assert facade.audit_graph is not None
        assert isinstance(facade.audit_graph, Graph)

    def test_access_event_bus(self, facade):
        """Test accessing event bus."""
        assert facade.event_bus is not None

    def test_access_all_repositories(self, facade):
        """Test accessing all repository/service components."""
        assert facade.process_repository is not None
        assert facade.instance_repository is not None
        assert facade.task_repository is not None
        assert facade.audit_repository is not None
        assert facade.variables_service is not None

    def test_access_all_execution_components(self, facade):
        """Test accessing all execution components."""
        assert facade.execution_engine is not None
        assert facade.gateway_evaluator is not None
        assert facade.token_handler is not None
        assert facade.multi_instance_handler is not None
        assert facade.error_handler is not None
        assert facade.node_handlers is not None

    def test_access_messaging_components(self, facade):
        """Test accessing messaging components."""
        assert facade.topic_registry is not None
        assert facade.message_handler is not None


class TestPersistence:
    """Tests for persistence via facade."""

    def test_save_creates_files(self, facade, tmp_path):
        """Test that save creates TTL files."""
        # Deploy a process to have some data
        facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        facade.save()

        assert (tmp_path / "definitions.ttl").exists()
        assert (tmp_path / "instances.ttl").exists()
        assert (tmp_path / "audit.ttl").exists()

    def test_data_persists_across_instances(self, tmp_path):
        """Test that data persists when creating new facade."""
        # Create first facade and deploy process
        facade1 = StorageFacade(str(tmp_path))
        process_id = facade1.deploy_process(
            name="Persistent Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )
        facade1.save()

        # Create second facade pointing to same directory
        facade2 = StorageFacade(str(tmp_path))

        # Process should be available
        process = facade2.get_process(process_id)
        assert process is not None
        assert process["id"] == process_id


class TestProcessUpdate:
    """Tests for updating process definitions via facade."""

    def test_update_process_name(self, facade):
        """Test updating process name."""
        process_id = facade.deploy_process(
            name="Original Name", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        updated = facade.update_process(process_id, name="Updated Name")

        assert updated is not None
        assert updated["name"] == "Updated Name"

    def test_update_process_description(self, facade):
        """Test updating process description."""
        process_id = facade.deploy_process(
            name="Test Process",
            bpmn_content=SIMPLE_PROCESS_BPMN,
            description="Original description",
            version="1.0",
        )

        updated = facade.update_process(process_id, description="Updated description")

        assert updated is not None
        assert updated["description"] == "Updated description"

    def test_update_process_status(self, facade):
        """Test updating process status."""
        process_id = facade.deploy_process(
            name="Test Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        updated = facade.update_process(process_id, status="INACTIVE")

        assert updated is not None
        assert updated["status"] == "INACTIVE"

    def test_update_nonexistent_process(self, facade):
        """Test updating non-existent process."""
        result = facade.update_process("nonexistent", name="New Name")
        assert result is None


class TestProcessGraph:
    """Tests for getting process graph via facade."""

    def test_get_process_graph(self, facade):
        """Test getting process RDF graph."""
        process_id = facade.deploy_process(
            name="Test Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        graph = facade.get_process_graph(process_id)

        assert graph is not None
        assert isinstance(graph, Graph)
        assert len(graph) > 0

    def test_get_process_graph_not_found(self, facade):
        """Test getting graph for non-existent process."""
        graph = facade.get_process_graph("nonexistent")
        assert graph is None


class TestTaskAssignment:
    """Tests for task assignment via facade."""

    def test_assign_task(self, facade):
        """Test assigning a task to a user."""
        # Deploy user task process
        process_id = facade.deploy_process(
            name="User Task Process", bpmn_content=USER_TASK_PROCESS_BPMN, version="1.0"
        )

        # Create instance (will stop at user task)
        instance = facade.create_instance(process_id)

        # Get the created task
        tasks = facade.list_tasks(instance_id=instance["id"])

        if tasks["total"] > 0:
            task_id = tasks["tasks"][0]["id"]

            # Assign the task
            assigned = facade.assign_task(task_id, "john.doe", "admin")

            assert assigned is not None
            assert assigned["assignee"] == "john.doe"
            assert assigned["status"] == "ASSIGNED"

    def test_assign_nonexistent_task(self, facade):
        """Test assigning non-existent task."""
        result = facade.assign_task("nonexistent", "user1")
        assert result is None


class TestResumeFromTask:
    """Tests for resuming instance from task via facade."""

    def test_resume_instance_from_completed_task(self, facade):
        """Test resuming instance after task completion."""
        # Deploy user task process
        process_id = facade.deploy_process(
            name="User Task Process", bpmn_content=USER_TASK_PROCESS_BPMN, version="1.0"
        )

        # Create instance (will stop at user task)
        instance = facade.create_instance(process_id)

        # Get the created task
        tasks = facade.list_tasks(instance_id=instance["id"])

        if tasks["total"] > 0:
            task_id = tasks["tasks"][0]["id"]

            # Complete the task (which should trigger resume_instance_from_task internally)
            result = facade.complete_task(task_id, "user1", {"approved": True})

            assert result is True

            # Instance should be completed now
            updated_instance = facade.get_instance(instance["id"])
            assert updated_instance["status"] == "COMPLETED"


class TestFilteringAndPagination:
    """Tests for filtering and pagination via facade."""

    def test_list_instances_filter_by_status(self, facade):
        """Test filtering instances by status."""
        # Use user task process which stays RUNNING at user task
        process_id = facade.deploy_process(
            name="User Task Process", bpmn_content=USER_TASK_PROCESS_BPMN, version="1.0"
        )

        # Create instances with different statuses
        inst1 = facade.create_instance(process_id)
        inst2 = facade.create_instance(process_id)
        facade.stop_instance(inst2["id"])

        # Filter by RUNNING
        running = facade.list_instances(status="RUNNING")
        terminated = facade.list_instances(status="TERMINATED")

        running_ids = [i["id"] for i in running["instances"]]
        terminated_ids = [i["id"] for i in terminated["instances"]]

        assert inst1["id"] in running_ids
        assert inst2["id"] in terminated_ids

    def test_list_instances_pagination(self, facade):
        """Test instance pagination."""
        process_id = facade.deploy_process(
            name="Simple Process", bpmn_content=SIMPLE_PROCESS_BPMN, version="1.0"
        )

        # Create 5 instances
        for _ in range(5):
            facade.create_instance(process_id)

        # Get page 1 with size 2
        page1 = facade.list_instances(page=1, page_size=2)

        assert page1["total"] >= 5
        assert len(page1["instances"]) == 2
        assert page1["page"] == 1
        assert page1["page_size"] == 2

        # Get page 2
        page2 = facade.list_instances(page=2, page_size=2)
        assert len(page2["instances"]) == 2
