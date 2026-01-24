# Integration Tests for StorageFacade
# Tests complete process execution through the facade

import pytest
from rdflib import Graph, Literal, RDF

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
