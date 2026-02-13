#!/usr/bin/env python3
"""
Additional tests for HTTP handlers and extended functionality
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from rdflib import Graph, Namespace, URIRef, Literal, XSD
import json


class TestHTTPHandlers:
    """Tests for HTTP handlers functionality"""

    @pytest.fixture
    def handlers(self):
        from src.api.handlers.http_handlers import HTTPHandlers

        return HTTPHandlers(default_timeout=10, max_retries=2)

    def test_init(self, handlers):
        """Test HTTPHandlers initialization"""
        assert handlers.default_timeout == 10
        assert handlers.max_retries == 2

    def test_substitute_variables_no_vars(self, handlers):
        """Test variable substitution with no variables"""
        result = handlers._substitute_variables("No variables here", {})
        assert result == "No variables here"

    def test_substitute_variables_single(self, handlers):
        """Test single variable substitution"""
        result = handlers._substitute_variables("Hello ${name}", {"name": "World"})
        assert result == "Hello World"

    def test_substitute_variables_multiple(self, handlers):
        """Test multiple variable substitution"""
        result = handlers._substitute_variables(
            "${user} ordered ${quantity} items", {"user": "John", "quantity": 5}
        )
        assert result == "John ordered 5 items"

    def test_substitute_variables_none_text(self, handlers):
        """Test variable substitution with None"""
        result = handlers._substitute_variables(None, {"name": "World"})
        assert result is None

    def test_extract_response_data_simple(self, handlers):
        """Test simple response extraction"""
        response = {"id": 123, "status": "success"}
        extraction = {"transactionId": "$.id", "status": "$.status"}

        result = handlers._extract_response_data(response, extraction)
        assert result["transactionId"] == "123"
        assert result["status"] == "success"

    def test_extract_response_data_nested(self, handlers):
        """Test nested JSON extraction"""
        response = {"transaction": {"details": {"id": "txn_123"}}}
        extraction = {"txnId": "$.transaction.details.id"}

        result = handlers._extract_response_data(response, extraction)
        assert result["txnId"] == "txn_123"

    def test_extract_response_data_array(self, handlers):
        """Test array index extraction"""
        response = {"items": [{"name": "first"}, {"name": "second"}]}
        extraction = {"firstItem": "$.items.0.name"}

        result = handlers._extract_response_data(response, extraction)
        assert result["firstItem"] == "first"

    def test_extract_response_data_missing_path(self, handlers):
        """Test extraction with missing path"""
        response = {"status": "ok"}
        extraction = {"missing": "$.nonexistent.path"}

        result = handlers._extract_response_data(response, extraction)
        assert "missing" not in result

    @patch("src.api.handlers.http_handlers.requests.request")
    def test_make_request_get(self, mock_request, handlers):
        """Test GET request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_request.return_value = mock_response

        result = handlers._make_request("GET", "http://example.com/api")

        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["url"] == "http://example.com/api"

    @patch("src.api.handlers.http_handlers.requests.request")
    def test_make_request_post(self, mock_request, handlers):
        """Test POST request with JSON data"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 123}
        mock_request.return_value = mock_response

        result = handlers._make_request(
            "POST",
            "http://example.com/api",
            data={"name": "test"},
            headers={"Content-Type": "application/json"},
        )

        mock_request.assert_called_once()

    @patch("src.api.handlers.http_handlers.requests.request")
    def test_make_request_with_api_key_auth(self, mock_request, handlers):
        """Test request with API key authentication"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        auth = {"type": "api_key", "key": "test-api-key"}
        handlers._make_request("GET", "http://example.com", auth=auth)

        call_kwargs = mock_request.call_args[1]
        # Verify headers include the API key
        assert "headers" in call_kwargs
        assert call_kwargs["headers"].get("X-API-Key") == "test-api-key"

    @patch("src.api.handlers.http_handlers.requests.request")
    def test_make_request_with_bearer_auth(self, mock_request, handlers):
        """Test request with bearer authentication."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        auth = {"type": "bearer", "token": "test-token"}
        handlers._make_request("GET", "http://example.com", auth=auth)

        call_kwargs = mock_request.call_args[1]
        assert "headers" in call_kwargs
        assert call_kwargs["headers"].get("Authorization") == "Bearer test-token"

    def test_make_request_blocks_private_destinations_by_default(self, handlers):
        """SSRF guard should block localhost/private destinations by default."""
        with pytest.raises(ValueError, match="Blocked private"):
            handlers._make_request("GET", "http://127.0.0.1/internal")

    @patch("src.api.handlers.http_handlers.requests.request")
    def test_make_request_allows_private_when_configured(
        self, mock_request, handlers, monkeypatch
    ):
        """Private destinations can be explicitly enabled via env var."""
        monkeypatch.setenv("SPEAR_HTTP_ALLOW_PRIVATE_NETWORKS", "true")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_request.return_value = mock_response

        handlers._make_request("GET", "http://127.0.0.1/internal")
        mock_request.assert_called_once()

    def test_make_request_blocks_unlisted_hosts_when_allowlist_set(
        self, handlers, monkeypatch
    ):
        """Outbound host allowlist should reject hosts not explicitly permitted."""
        monkeypatch.setenv("SPEAR_HTTP_ALLOWED_HOSTS", "api.example.com,*.trusted.test")
        with pytest.raises(ValueError, match="Host not permitted"):
            handlers._make_request("GET", "https://not-allowed.example.net/path")

    @patch("src.api.handlers.http_handlers.requests.request")
    def test_make_request_allows_host_matching_allowlist(
        self, mock_request, handlers, monkeypatch
    ):
        """Outbound host allowlist should allow exact and wildcard hosts."""
        monkeypatch.setenv("SPEAR_HTTP_ALLOWED_HOSTS", "api.example.com,*.trusted.test")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_request.return_value = mock_response

        handlers._make_request("GET", "https://api.example.com/v1")
        handlers._make_request("GET", "https://svc.trusted.test/v1")
        assert mock_request.call_count == 2


class TestProcessContextExtended:
    """Extended tests for ProcessContext"""

    @pytest.fixture
    def graph(self):
        return Graph()

    @pytest.fixture
    def context(self, graph):
        from src.core.rdfengine import ProcessContext

        inst_uri = URIRef("http://example.org/instance1")
        return ProcessContext(graph, inst_uri)

    def test_set_and_get_multiple_variables(self, context):
        """Test setting and getting multiple variables"""
        context.set_variable("name", "TestProcess", datatype=XSD.string)
        context.set_variable("count", 42, datatype=XSD.integer)
        context.set_variable("active", True, datatype=XSD.boolean)

        assert str(context.get_variable("name")) == "TestProcess"
        assert str(context.get_variable("count")) == "42"
        assert str(context.get_variable("active")) == "true"

    def test_overwrite_variable(self, context):
        """Test overwriting an existing variable"""
        context.set_variable("counter", 10, datatype=XSD.integer)
        context.set_variable("counter", 20, datatype=XSD.integer)

        result = context.get_variable("counter")
        assert str(result) == "20"


class TestBPMNConverterExtended:
    """Extended tests for BPMN to RDF conversion"""

    @pytest.fixture
    def converter(self):
        from src.conversion.bpmn2rdf import BPMNToRDFConverter

        return BPMNToRDFConverter()

    def test_convert_empty_process(self, converter):
        """Test converting a minimal valid BPMN process"""
        bpmn = """
        <process id="emptyProcess">
            <startEvent id="start1" name="Start"/>
            <endEvent id="end1"/>
            <sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
        </process>
        """
        import io

        result = converter.parse_bpmn(io.StringIO(bpmn))

        assert "rdf:type bpmn:process" in result
        assert "rdf:type bpmn:startEvent" in result
        assert "rdf:type bpmn:endEvent" in result
        assert "rdf:type bpmn:sequenceFlow" in result

    def test_convert_with_service_task(self, converter):
        """Test converting a BPMN with service task"""
        bpmn = """
        <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
            <bpmn:process id="testProcess">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Process Payment" camunda:topic="process_payment"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>
        """
        import io

        result = converter.parse_bpmn(io.StringIO(bpmn))

        assert "rdf:type bpmn:serviceTask" in result
        assert "camunda:topic" in result
        assert "process_payment" in result

    def test_convert_with_user_task(self, converter):
        """Test converting a BPMN with user task"""
        bpmn = """
        <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
            <bpmn:process id="testProcess">
                <bpmn:startEvent id="start1"/>
                <bpmn:userTask id="task1" name="Review Request" camunda:assignee="admin"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>
        """
        import io

        result = converter.parse_bpmn(io.StringIO(bpmn))

        assert "rdf:type bpmn:userTask" in result
        assert "camunda:assignee" in result


class TestExportFunctions:
    """Tests for export functionality"""

    def test_export_module_imports(self):
        """Test that export module can be imported"""
        from src.export import export_to_xes_csv

        assert callable(export_to_xes_csv)


class TestInstanceOperations:
    """Tests for instance operations"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService
        import tempfile
        import os

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        # Cleanup
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_create_instance_with_variables(self, storage):
        """Test creating instance with initial variables"""
        # First deploy a process
        process_id = storage.deploy_process(
            name="Test Process",
            description="A test process",
            bpmn_content="""
            <process id="testProc">
                <startEvent id="start1"/>
                <endEvent id="end1"/>
                <sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
            </process>
            """,
        )

        # Create instance with variables
        result = storage.create_instance(
            process_id=process_id, variables={"orderId": "ORD-123", "amount": 150.50}
        )

        assert result["id"] is not None
        assert result["status"] == "RUNNING"

        # Verify variables were stored
        instance_data = storage.get_instance(result["id"])
        assert "orderId" in instance_data["variables"]
        assert instance_data["variables"]["orderId"] == "ORD-123"

    def test_set_and_get_instance_variable(self, storage):
        """Test setting and getting instance variables"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="A test process",
            bpmn_content="""
            <process id="testProc">
                <startEvent id="start1"/>
                <endEvent id="end1"/>
                <sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
            </process>
            """,
        )

        result = storage.create_instance(process_id=process_id)
        instance_id = result["id"]

        # Set a new variable
        storage.set_instance_variable(instance_id, "newVar", "newValue")

        # Get all variables
        variables = storage.get_instance_variables(instance_id)
        assert "newVar" in variables
        assert variables["newVar"] == "newValue"

    def test_list_instances_filtered(self, storage):
        """Test listing instances with filters"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="A test process",
            bpmn_content="""
            <process id="testProc">
                <startEvent id="start1"/>
                <endEvent id="end1"/>
                <sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
            </process>
            """,
        )

        # Create multiple instances
        storage.create_instance(process_id=process_id)
        storage.create_instance(process_id=process_id)

        # List instances
        instances = storage.list_instances(process_id=process_id)
        assert instances["total"] >= 2


class TestTaskOperations:
    """Tests for task operations"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService
        import tempfile

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_create_and_get_task(self, storage):
        """Test creating and retrieving a task"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="A test process",
            bpmn_content="""
            <process id="testProc">
                <startEvent id="start1"/>
                <userTask id="task1" name="Review"/>
                <endEvent id="end1"/>
                <sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
            </process>
            """,
        )

        instance_result = storage.create_instance(process_id=process_id)
        instance_id = instance_result["id"]

        # Create a task manually
        task = storage.create_task(
            instance_id=instance_id,
            node_uri="http://example.org/bpmn/task1",
            name="Review Request",
            assignee="admin",
        )

        assert task["id"] is not None
        assert task["name"] == "Review Request"
        assert task["assignee"] == "admin"

    def test_list_tasks(self, storage):
        """Test listing tasks"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="A test process",
            bpmn_content="""
            <process id="testProc">
                <startEvent id="start1"/>
                <userTask id="task1" name="Task 1"/>
                <endEvent id="end1"/>
                <sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
            </process>
            """,
        )

        instance_result = storage.create_instance(process_id=process_id)
        instance_id = instance_result["id"]

        storage.create_task(
            instance_id=instance_id,
            node_uri="http://example.org/bpmn/task1",
            name="Task 1",
        )

        tasks = storage.list_tasks(instance_id=instance_id)
        assert tasks["total"] >= 1


class TestTopicRegistration:
    """Tests for topic handler registration"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService
        import tempfile

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_register_topic_handler(self, storage):
        """Test registering a topic handler"""

        def dummy_handler(instance_id, variables):
            return variables

        result = storage.register_topic_handler(
            topic="test_topic",
            handler_function=dummy_handler,
            description="A test handler",
            handler_type="function",
        )

        assert result is True

        # Verify it's registered
        topics = storage.get_registered_topics()
        assert "test_topic" in topics
        assert topics["test_topic"]["description"] == "A test handler"

    def test_unregister_topic_handler(self, storage):
        """Test unregistering a topic handler"""

        def dummy_handler(instance_id, variables):
            return variables

        storage.register_topic_handler(
            topic="to_remove", handler_function=dummy_handler
        )

        result = storage.unregister_topic_handler("to_remove")
        assert result is True

        topics = storage.get_registered_topics()
        assert "to_remove" not in topics

    def test_execute_service_task(self, storage):
        """Test executing a service task"""

        def calculate_total(instance_id, variables):
            variables["total"] = variables.get("subtotal", 0) + 10
            return variables

        storage.register_topic_handler(
            topic="calculate_total", handler_function=calculate_total
        )

        result = storage.execute_service_task(
            instance_id="test-instance",
            topic="calculate_total",
            variables={"subtotal": 100},
        )

        assert result["total"] == 110


class TestAuditLogging:
    """Tests for audit logging functionality"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService
        import tempfile

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_get_instance_audit_log(self, storage):
        """Test retrieving audit log for an instance"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="A test process",
            bpmn_content="""
            <process id="testProc">
                <startEvent id="start1"/>
                <endEvent id="end1"/>
                <sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
            </process>
            """,
        )

        result = storage.create_instance(process_id=process_id)
        instance_id = result["id"]

        # Get audit log
        audit_log = storage.get_instance_audit_log(instance_id)

        # Should have at least the CREATED event
        assert len(audit_log) >= 1
        event_types = [e["type"] for e in audit_log]
        assert "CREATED" in event_types
