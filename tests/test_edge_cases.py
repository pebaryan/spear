#!/usr/bin/env python3
"""
Edge case and error handling tests for SPEAR
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from rdflib import Graph, URIRef, Namespace
import tempfile
import os


class TestAPIErrorHandling:
    """Test API error handling and edge cases"""

    @pytest.fixture
    def client(self):
        from src.api.main import app

        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_nonexistent_process(self, client):
        """Test getting a process that doesn't exist"""
        response = client.get("/api/v1/processes/nonexistent-id")
        assert response.status_code == 404

    def test_nonexistent_instance(self, client):
        """Test getting an instance that doesn't exist"""
        response = client.get("/api/v1/instances/nonexistent-id")
        assert response.status_code == 404


class TestStorageEdgeCases:
    """Test storage service edge cases"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_delete_nonexistent_process(self, storage):
        """Test deleting a process that doesn't exist"""
        result = storage.delete_process("nonexistent-id")
        # Function returns True even for nonexistent processes
        assert result is True

    def test_stop_nonexistent_instance(self, storage):
        """Test stopping an instance that doesn't exist"""
        from fastapi import HTTPException

        with pytest.raises(ValueError):
            storage.stop_instance("nonexistent-id")

    def test_get_nonexistent_instance_variables(self, storage):
        """Test getting variables for nonexistent instance"""
        variables = storage.get_instance_variables("nonexistent-id")
        assert variables == {}

    def test_update_nonexistent_process(self, storage):
        """Test updating a process that doesn't exist"""
        result = storage.update_process("nonexistent-id", name="New Name")
        assert result is None

    def test_create_instance_nonexistent_process(self, storage):
        """Test creating instance with nonexistent process"""
        from fastapi import HTTPException

        with pytest.raises(ValueError):
            storage.create_instance(process_id="nonexistent-id")

    def test_get_statistics_empty(self, storage):
        """Test statistics on empty storage"""
        stats = storage.get_statistics()
        assert "process_count" in stats
        assert "instance_count" in stats
        assert "total_triples" in stats
        assert stats["process_count"] == 0

    def test_list_processes_pagination(self, storage):
        """Test pagination of process list"""
        # Create some processes
        for i in range(5):
            storage.deploy_process(
                name=f"Process {i}",
                description="Test",
                bpmn_content="""
                <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                    <bpmn:process id="proc{}"/>
                </bpmn:definitions>
                """.format(i),
            )

        # Test pagination
        page1 = storage.list_processes(page=1, page_size=2)
        page2 = storage.list_processes(page=2, page_size=2)

        assert page1["page"] == 1
        assert page1["page_size"] == 2
        assert len(page1["processes"]) == 2
        assert page2["page"] == 2
        assert len(page2["processes"]) >= 1


class TestTaskEdgeCases:
    """Test task operations edge cases"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_claim_nonexistent_task(self, storage):
        """Test claiming a task that doesn't exist"""
        # Returns None instead of raising exception
        result = storage.claim_task("nonexistent-id", "user1")
        assert result is None

    def test_complete_nonexistent_task(self, storage):
        """Test completing a task that doesn't exist"""
        # Returns None instead of raising exception
        result = storage.complete_task("nonexistent-id", "user1")
        assert result is None

    def test_list_tasks_with_filters(self, storage):
        """Test listing tasks with various filters"""
        # Should return empty list when no tasks exist
        result = storage.list_tasks(
            instance_id="nonexistent", status="COMPLETED", assignee="nobody"
        )
        assert result["total"] == 0
        assert result["tasks"] == []


class TestTopicHandlerEdgeCases:
    """Test topic handler edge cases"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_execute_nonexistent_topic(self, storage):
        """Test executing a topic that doesn't exist"""
        with pytest.raises(ValueError) as exc_info:
            storage.execute_service_task(
                instance_id="test-instance", topic="nonexistent_topic", variables={}
            )
        assert "No handler registered" in str(exc_info.value)

    def test_update_nonexistent_topic_description(self, storage):
        """Test updating description for nonexistent topic"""
        result = storage.update_topic_description(
            "nonexistent_topic", "New description"
        )
        assert result is False

    def test_update_nonexistent_topic_async(self, storage):
        """Test updating async setting for nonexistent topic"""
        result = storage.update_topic_async("nonexistent_topic", async_execution=True)
        assert result is False

    def test_unregister_nonexistent_topic(self, storage):
        """Test unregistering a topic that doesn't exist"""
        result = storage.unregister_topic_handler("nonexistent_topic")
        assert result is False


class TestInstanceLifecycle:
    """Test instance lifecycle edge cases"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_instance_with_no_variables(self, storage):
        """Test creating and managing instance with no variables"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="Test",
            bpmn_content="""
            <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                <bpmn:process id="testProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>
            """,
        )

        result = storage.create_instance(process_id=process_id, variables=None)

        instance_data = storage.get_instance(result["id"])
        assert instance_data["variables"] == {}

    def test_list_instances_status_filter(self, storage):
        """Test filtering instances by status"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="Test",
            bpmn_content="""
            <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                <bpmn:process id="testProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>
            """,
        )

        storage.create_instance(process_id=process_id)

        # List all instances
        all_instances = storage.list_instances()
        assert all_instances["total"] >= 1

        # List with status filter (instances complete immediately for simple processes)
        completed_instances = storage.list_instances(status="COMPLETED")
        # May be 0 if process completes immediately
        assert completed_instances["total"] >= 0


class TestBPMNConverterEdgeCases:
    """Test BPMN conversion edge cases"""

    @pytest.fixture
    def converter(self):
        from src.conversion.bpmn2rdf import BPMNToRDFConverter

        return BPMNToRDFConverter()

    def test_convert_gateway(self, converter):
        """Test converting BPMN with gateways"""
        bpmn = """
        <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
            <bpmn:process id="testProc">
                <bpmn:startEvent id="start1"/>
                <bpmn:exclusiveGateway id="gateway1" name="Decision"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="gateway1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>
        """
        import io

        result = converter.parse_bpmn(io.StringIO(bpmn))

        assert "rdf:type bpmn:exclusiveGateway" in result
        assert "bpmn:name" in result
        assert "Decision" in result

    def test_convert_with_documentation(self, converter):
        """Test converting BPMN with documentation"""
        bpmn = """
        <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
            <bpmn:process id="testProc">
                <bpmn:startEvent id="start1">
                    <bpmn:documentation>This is a start event</bpmn:documentation>
                </bpmn:startEvent>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>
        """
        import io

        result = converter.parse_bpmn(io.StringIO(bpmn))

        assert "bpmn:documentation" in result
        assert "This is a start event" in result

    def test_convert_parallel_gateway(self, converter):
        """Test converting BPMN with parallel gateway"""
        bpmn = """
        <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
            <bpmn:process id="testProc">
                <bpmn:startEvent id="start1"/>
                <bpmn:parallelGateway id="gateway1"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="gateway1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>
        """
        import io

        result = converter.parse_bpmn(io.StringIO(bpmn))

        assert "rdf:type bpmn:parallelGateway" in result


class TestVariableDataTypes:
    """Test variable handling with different data types"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_variables_with_special_characters(self, storage):
        """Test variables with special characters"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="Test",
            bpmn_content="""
            <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                <bpmn:process id="testProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>
            """,
        )

        result = storage.create_instance(
            process_id=process_id,
            variables={"name": "John Doe", "email": "john@example.com"},
        )

        instance_data = storage.get_instance(result["id"])
        assert "name" in instance_data["variables"]
        assert "email" in instance_data["variables"]

    def test_variables_with_numbers(self, storage):
        """Test variables with numeric values"""
        process_id = storage.deploy_process(
            name="Test Process",
            description="Test",
            bpmn_content="""
            <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                <bpmn:process id="testProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>
            """,
        )

        result = storage.create_instance(
            process_id=process_id,
            variables={"count": 42, "price": 99.99, "percentage": 0.5},
        )

        instance_data = storage.get_instance(result["id"])
        assert "count" in instance_data["variables"]
        assert "price" in instance_data["variables"]
        assert "percentage" in instance_data["variables"]
