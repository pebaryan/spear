# Tests for InstanceRepository
# Tests process instance lifecycle management

import pytest
from rdflib import Graph, URIRef, Literal, RDF

from src.api.storage.instance_repository import InstanceRepository
from src.api.storage.base import BPMN, PROC, INST, VAR


class TestInstanceRepositoryInit:
    """Tests for InstanceRepository initialization."""

    def test_init_with_graphs(self, tmp_path):
        """Test initializing repository with graphs."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        assert repo._definitions is defs
        assert repo._instances is insts
        assert repo._audit is audit


class TestCreateInstance:
    """Tests for create_instance method."""

    def test_create_instance_basic(self, tmp_path):
        """Test creating a basic instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        # Add process definition
        process_uri = PROC["test_process"]
        defs.add((process_uri, RDF.type, PROC.ProcessDefinition))

        # Add start event
        start_uri = BPMN.StartEvent1
        defs.add((process_uri, PROC.hasElement, start_uri))
        defs.add((start_uri, RDF.type, BPMN.StartEvent))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.create_instance("test_process")

        assert result["process_id"] == "test_process"
        assert result["status"] == "RUNNING"
        assert "id" in result

    def test_create_instance_with_variables(self, tmp_path):
        """Test creating instance with initial variables."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        process_uri = PROC["test_process"]
        defs.add((process_uri, RDF.type, PROC.ProcessDefinition))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        variables = {"orderId": "123", "amount": "99.99"}
        result = repo.create_instance("test_process", variables=variables)

        assert result["variables"] == variables

    def test_create_instance_not_found(self, tmp_path):
        """Test creating instance for non-existent process."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        with pytest.raises(ValueError, match="Process.*not found"):
            repo.create_instance("nonexistent")

    def test_create_instance_with_execute_callback(self, tmp_path):
        """Test that execute callback is called."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        process_uri = PROC["test_process"]
        defs.add((process_uri, RDF.type, PROC.ProcessDefinition))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        callback_calls = []

        def execute_callback(instance_uri, instance_id):
            callback_calls.append((instance_uri, instance_id))

        result = repo.create_instance("test_process", execute_callback=execute_callback)

        assert len(callback_calls) == 1
        assert callback_calls[0][1] == result["id"]

    def test_create_instance_with_log_callback(self, tmp_path):
        """Test that log callback is called."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        process_uri = PROC["test_process"]
        defs.add((process_uri, RDF.type, PROC.ProcessDefinition))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        log_calls = []

        def log_callback(instance_uri, event, user, details):
            log_calls.append((event, user))

        repo.create_instance("test_process", log_callback=log_callback)

        assert len(log_calls) == 1
        assert log_calls[0][0] == "CREATED"

    def test_create_instance_with_specific_start_event(self, tmp_path):
        """Test creating instance with specific start event."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        process_uri = PROC["test_process"]
        defs.add((process_uri, RDF.type, PROC.ProcessDefinition))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.create_instance("test_process", start_event_id="CustomStartEvent")

        # Get the token and check its start node
        instance_uri = INST[result["id"]]
        for token_uri in insts.objects(instance_uri, INST.hasToken):
            node = insts.value(token_uri, INST.currentNode)
            assert "CustomStartEvent" in str(node)


class TestGetInstance:
    """Tests for get_instance method."""

    def test_get_instance_exists(self, tmp_path):
        """Test getting an existing instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        # Create instance directly in graph
        instance_uri = INST["inst_123"]
        process_uri = PROC["test_process"]

        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.processDefinition, process_uri))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))
        insts.add((instance_uri, INST.createdAt, Literal("2024-01-01T00:00:00")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.get_instance("inst_123")

        assert result is not None
        assert result["id"] == "inst_123"
        assert result["process_id"] == "test_process"
        assert result["status"] == "RUNNING"

    def test_get_instance_not_found(self, tmp_path):
        """Test getting non-existent instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.get_instance("nonexistent")

        assert result is None

    def test_get_instance_with_variables(self, tmp_path):
        """Test getting instance with variables."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        # Add variable
        var_uri = VAR["inst_123_orderId"]
        insts.add((instance_uri, INST.hasVariable, var_uri))
        insts.add((var_uri, VAR.name, Literal("orderId")))
        insts.add((var_uri, VAR.value, Literal("123")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.get_instance("inst_123")

        assert result["variables"]["orderId"] == "123"

    def test_get_instance_with_tokens(self, tmp_path):
        """Test getting instance with current nodes from tokens."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        # Add token
        token_uri = INST["token_123"]
        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, BPMN.Task1))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.get_instance("inst_123")

        assert len(result["current_nodes"]) == 1
        assert "Task1" in result["current_nodes"][0]


class TestInstanceExists:
    """Tests for instance_exists method."""

    def test_instance_exists_true(self, tmp_path):
        """Test instance exists returns true."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        assert repo.instance_exists("inst_123") is True

    def test_instance_exists_false(self, tmp_path):
        """Test instance exists returns false."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        assert repo.instance_exists("nonexistent") is False


class TestListInstances:
    """Tests for list_instances method."""

    def test_list_instances_empty(self, tmp_path):
        """Test listing instances when none exist."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.list_instances()

        assert result["instances"] == []
        assert result["total"] == 0

    def test_list_instances_basic(self, tmp_path):
        """Test listing all instances."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        # Add two instances
        inst1 = INST["inst_1"]
        inst2 = INST["inst_2"]

        insts.add((inst1, RDF.type, INST.ProcessInstance))
        insts.add((inst1, INST.status, Literal("RUNNING")))
        insts.add((inst1, INST.processDefinition, PROC.Process1))

        insts.add((inst2, RDF.type, INST.ProcessInstance))
        insts.add((inst2, INST.status, Literal("COMPLETED")))
        insts.add((inst2, INST.processDefinition, PROC.Process2))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.list_instances()

        assert result["total"] == 2
        assert len(result["instances"]) == 2

    def test_list_instances_filter_by_process(self, tmp_path):
        """Test filtering instances by process ID."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        inst1 = INST["inst_1"]
        inst2 = INST["inst_2"]

        insts.add((inst1, RDF.type, INST.ProcessInstance))
        insts.add((inst1, INST.status, Literal("RUNNING")))
        insts.add((inst1, INST.processDefinition, PROC.Process1))

        insts.add((inst2, RDF.type, INST.ProcessInstance))
        insts.add((inst2, INST.status, Literal("RUNNING")))
        insts.add((inst2, INST.processDefinition, PROC.Process2))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.list_instances(process_id="Process1")

        assert result["total"] == 1
        assert result["instances"][0]["process_id"] == "Process1"

    def test_list_instances_filter_by_status(self, tmp_path):
        """Test filtering instances by status."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        inst1 = INST["inst_1"]
        inst2 = INST["inst_2"]

        insts.add((inst1, RDF.type, INST.ProcessInstance))
        insts.add((inst1, INST.status, Literal("RUNNING")))

        insts.add((inst2, RDF.type, INST.ProcessInstance))
        insts.add((inst2, INST.status, Literal("COMPLETED")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.list_instances(status="RUNNING")

        assert result["total"] == 1
        assert result["instances"][0]["status"] == "RUNNING"

    def test_list_instances_pagination(self, tmp_path):
        """Test pagination of instances."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        # Add 5 instances
        for i in range(5):
            inst = INST[f"inst_{i}"]
            insts.add((inst, RDF.type, INST.ProcessInstance))
            insts.add((inst, INST.status, Literal("RUNNING")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.list_instances(page=1, page_size=2)

        assert result["total"] == 5
        assert len(result["instances"]) == 2
        assert result["page"] == 1
        assert result["page_size"] == 2


class TestStopInstance:
    """Tests for stop_instance method."""

    def test_stop_instance_success(self, tmp_path):
        """Test stopping an instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.stop_instance("inst_123", "Test reason")

        assert result["status"] == "TERMINATED"

    def test_stop_instance_not_found(self, tmp_path):
        """Test stopping non-existent instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        with pytest.raises(ValueError, match="Instance.*not found"):
            repo.stop_instance("nonexistent")

    def test_stop_instance_with_log_callback(self, tmp_path):
        """Test that log callback is called when stopping."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        log_calls = []

        def log_callback(instance_uri, event, user, details):
            log_calls.append((event, details))

        repo.stop_instance("inst_123", "Custom reason", log_callback=log_callback)

        assert len(log_calls) == 1
        assert log_calls[0][0] == "TERMINATED"
        assert log_calls[0][1] == "Custom reason"


class TestCancelInstance:
    """Tests for cancel_instance method."""

    def test_cancel_instance_success(self, tmp_path):
        """Test cancelling an instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        # Add active token
        token_uri = INST["token_123"]
        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.cancel_instance("inst_123", "User cancelled")

        assert result["status"] == "CANCELLED"
        # Token should be consumed
        assert str(insts.value(token_uri, INST.status)) == "CONSUMED"

    def test_cancel_instance_not_found(self, tmp_path):
        """Test cancelling non-existent instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        with pytest.raises(ValueError, match="Instance.*not found"):
            repo.cancel_instance("nonexistent")

    def test_cancel_instance_already_completed(self, tmp_path):
        """Test cancelling already completed instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("COMPLETED")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        with pytest.raises(ValueError, match="already COMPLETED"):
            repo.cancel_instance("inst_123")

    def test_cancel_instance_consumes_waiting_tokens(self, tmp_path):
        """Test that waiting tokens are also consumed."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        # Add waiting token
        token_uri = INST["token_123"]
        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.status, Literal("WAITING")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        repo.cancel_instance("inst_123")

        assert str(insts.value(token_uri, INST.status)) == "CONSUMED"


class TestInstanceStatus:
    """Tests for instance status methods."""

    def test_set_instance_status(self, tmp_path):
        """Test setting instance status."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        repo.set_instance_status("inst_123", "COMPLETED")

        assert str(insts.value(instance_uri, INST.status)) == "COMPLETED"
        assert insts.value(instance_uri, INST.updatedAt) is not None

    def test_get_instance_status(self, tmp_path):
        """Test getting instance status."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        assert repo.get_instance_status("inst_123") == "RUNNING"

    def test_get_instance_status_none(self, tmp_path):
        """Test getting status for non-existent instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        assert repo.get_instance_status("nonexistent") is None


class TestInstanceTokens:
    """Tests for instance token methods."""

    def test_get_instance_tokens(self, tmp_path):
        """Test getting all tokens for instance."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))

        token1 = INST["token_1"]
        token2 = INST["token_2"]
        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((instance_uri, INST.hasToken, token2))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        tokens = repo.get_instance_tokens("inst_123")

        assert len(tokens) == 2
        assert token1 in tokens
        assert token2 in tokens

    def test_get_active_tokens(self, tmp_path):
        """Test getting only active tokens."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))

        token1 = INST["token_1"]
        token2 = INST["token_2"]
        token3 = INST["token_3"]

        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((token1, INST.status, Literal("ACTIVE")))

        insts.add((instance_uri, INST.hasToken, token2))
        insts.add((token2, INST.status, Literal("CONSUMED")))

        insts.add((instance_uri, INST.hasToken, token3))
        insts.add((token3, INST.status, Literal("ACTIVE")))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        active_tokens = repo.get_active_tokens("inst_123")

        assert len(active_tokens) == 2
        assert token1 in active_tokens
        assert token3 in active_tokens
        assert token2 not in active_tokens


class TestProcessDefinitionAccess:
    """Tests for process definition access."""

    def test_get_process_definition_uri(self, tmp_path):
        """Test getting process definition URI."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        process_uri = PROC["test_process"]
        instance_uri = INST["inst_123"]
        insts.add((instance_uri, RDF.type, INST.ProcessInstance))
        insts.add((instance_uri, INST.processDefinition, process_uri))

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.get_process_definition_uri("inst_123")

        assert result == process_uri

    def test_get_process_definition_uri_none(self, tmp_path):
        """Test getting process definition URI when not set."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        result = repo.get_process_definition_uri("nonexistent")

        assert result is None


class TestInstanceUri:
    """Tests for get_instance_uri method."""

    def test_get_instance_uri(self, tmp_path):
        """Test getting instance URI."""
        defs = Graph()
        insts = Graph()
        audit = Graph()

        repo = InstanceRepository(defs, insts, audit, str(tmp_path))

        uri = repo.get_instance_uri("inst_123")

        assert uri == INST["inst_123"]
