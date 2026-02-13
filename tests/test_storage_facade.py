# Tests for StorageFacade
# Tests the unified facade that wires all modules together

import pytest
from rdflib import Graph, Literal, RDF

from src.api.storage.facade import StorageFacade, get_facade, reset_facade
from src.api.storage.base import PROC, BPMN, INST


class TestStorageFacadeInit:
    """Tests for StorageFacade initialization."""

    def test_init_creates_graphs(self, tmp_path):
        """Test that facade creates graphs on init."""
        facade = StorageFacade(str(tmp_path))

        assert facade.definitions_graph is not None
        assert facade.instances_graph is not None
        assert facade.audit_graph is not None

    def test_init_creates_components(self, tmp_path):
        """Test that facade creates all components."""
        facade = StorageFacade(str(tmp_path))

        assert facade.event_bus is not None
        assert facade.process_repository is not None
        assert facade.instance_repository is not None
        assert facade.task_repository is not None
        assert facade.audit_repository is not None
        assert facade.variables_service is not None
        assert facade.topic_registry is not None
        assert facade.message_handler is not None
        assert facade.execution_engine is not None
        assert facade.gateway_evaluator is not None
        assert facade.token_handler is not None
        assert facade.multi_instance_handler is not None
        assert facade.error_handler is not None
        assert facade.node_handlers is not None


class TestGetFacade:
    """Tests for get_facade function."""

    def test_get_facade_creates_singleton(self, tmp_path):
        """Test that get_facade returns the same instance."""
        reset_facade()

        facade1 = get_facade(str(tmp_path))
        facade2 = get_facade(str(tmp_path))

        assert facade1 is facade2

        reset_facade()

    def test_reset_facade_clears_singleton(self, tmp_path):
        """Test that reset_facade clears the singleton."""
        reset_facade()

        facade1 = get_facade(str(tmp_path))
        reset_facade()
        facade2 = get_facade(str(tmp_path))

        assert facade1 is not facade2

        reset_facade()


class TestProcessOperations:
    """Tests for process definition operations via facade."""

    def test_get_process_not_found(self, tmp_path):
        """Test getting non-existent process."""
        facade = StorageFacade(str(tmp_path))

        result = facade.get_process("nonexistent")

        assert result is None

    def test_list_processes_empty(self, tmp_path):
        """Test listing processes when none exist."""
        facade = StorageFacade(str(tmp_path))

        result = facade.list_processes()

        assert result["total"] == 0
        assert result["processes"] == []


class TestInstanceOperations:
    """Tests for instance operations via facade."""

    def test_create_instance_process_not_found(self, tmp_path):
        """Test creating instance for non-existent process."""
        facade = StorageFacade(str(tmp_path))

        with pytest.raises(ValueError, match="Process.*not found"):
            facade.create_instance("nonexistent")

    def test_get_instance_not_found(self, tmp_path):
        """Test getting non-existent instance."""
        facade = StorageFacade(str(tmp_path))

        result = facade.get_instance("nonexistent")

        assert result is None

    def test_list_instances_empty(self, tmp_path):
        """Test listing instances when none exist."""
        facade = StorageFacade(str(tmp_path))

        result = facade.list_instances()

        assert result["total"] == 0
        assert result["instances"] == []

    def test_create_instance_success(self, tmp_path):
        """Test creating an instance successfully."""
        facade = StorageFacade(str(tmp_path))

        # Add process definition directly to graph
        process_uri = PROC["test_process"]
        facade.definitions_graph.add((process_uri, RDF.type, PROC.ProcessDefinition))

        # Add start event
        start_uri = BPMN.StartEvent1
        facade.definitions_graph.add((process_uri, PROC.hasElement, start_uri))
        facade.definitions_graph.add((start_uri, RDF.type, BPMN.StartEvent))

        result = facade.create_instance("test_process", {"orderTotal": "100"})

        assert result["process_id"] == "test_process"
        assert result["status"] == "RUNNING"
        assert "id" in result
        assert result["variables"]["orderTotal"] == "100"


class TestVariableOperations:
    """Tests for variable operations via facade."""

    def test_get_variables_empty(self, tmp_path):
        """Test getting variables for instance with no variables."""
        facade = StorageFacade(str(tmp_path))

        # Create instance in graph
        instance_uri = INST["test_inst"]
        facade.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))

        result = facade.get_instance_variables("test_inst")

        assert result == {}

    def test_set_and_get_variable(self, tmp_path):
        """Test setting and getting a variable."""
        facade = StorageFacade(str(tmp_path))

        # Create instance in graph
        instance_uri = INST["test_inst"]
        facade.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))

        facade.set_instance_variable("test_inst", "amount", "99.99")

        variables = facade.get_instance_variables("test_inst")

        assert variables["amount"] == "99.99"


class TestTaskOperations:
    """Tests for task operations via facade."""

    def test_list_tasks_empty(self, tmp_path):
        """Test listing tasks when none exist."""
        facade = StorageFacade(str(tmp_path))

        result = facade.list_tasks()

        # list returns a dict with tasks, total, page, page_size
        assert result["tasks"] == []
        assert result["total"] == 0

    def test_get_task_not_found(self, tmp_path):
        """Test getting non-existent task."""
        facade = StorageFacade(str(tmp_path))

        result = facade.get_task("nonexistent")

        assert result is None


class TestAuditOperations:
    """Tests for audit operations via facade."""

    def test_get_audit_log_empty(self, tmp_path):
        """Test getting audit log for instance with no events."""
        facade = StorageFacade(str(tmp_path))

        result = facade.get_instance_audit_log("test_inst")

        assert result == []


class TestServiceTaskRegistration:
    """Tests for service task registration via facade."""

    def test_register_and_get_handler(self, tmp_path):
        """Test registering and retrieving a handler."""
        facade = StorageFacade(str(tmp_path))

        def my_handler(context):
            pass

        facade.register_service_task_handler("calculate_tax", my_handler)

        handler = facade.get_service_task_handler("calculate_tax")

        assert handler is my_handler

    def test_unregister_handler(self, tmp_path):
        """Test unregistering a handler."""
        facade = StorageFacade(str(tmp_path))

        def my_handler(context):
            pass

        facade.register_service_task_handler("my_topic", my_handler)
        result = facade.unregister_service_task_handler("my_topic")

        assert result is True
        assert facade.get_service_task_handler("my_topic") is None

    def test_topic_compatibility_methods(self, tmp_path):
        """Test backward-compatible topic API methods on facade."""
        facade = StorageFacade(str(tmp_path))

        def handler(instance_id, variables):
            updated = dict(variables)
            updated["processed"] = True
            return updated

        assert facade.register_topic_handler("compat_topic", handler) is True
        topics = facade.get_registered_topics()
        assert "compat_topic" in topics

        result = facade.execute_service_task(
            "test-instance", "compat_topic", {"input": "value"}
        )
        assert result["processed"] is True

        assert facade.update_topic_description("compat_topic", "Updated") is True
        assert facade.update_topic_async("compat_topic", True) is True
        assert facade.unregister_topic_handler("compat_topic") is True


class TestSaveOperation:
    """Tests for save operation."""

    def test_save_creates_files(self, tmp_path):
        """Test that save creates TTL files."""
        facade = StorageFacade(str(tmp_path))

        # Add some data
        facade.definitions_graph.add((PROC.Test, RDF.type, PROC.ProcessDefinition))

        facade.save()

        # Check files exist
        assert (tmp_path / "definitions.ttl").exists()
        assert (tmp_path / "instances.ttl").exists()
        assert (tmp_path / "audit.ttl").exists()
