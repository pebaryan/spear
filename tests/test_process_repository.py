# Tests for Process Repository
# Verifies process definition CRUD operations

import os
import tempfile
import pytest
from rdflib import Graph

from src.api.storage.base import BaseStorageService
from src.api.storage.process_repository import ProcessRepository


# Sample BPMN for testing
SIMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             id="definitions">
  <process id="TestProcess" name="Test Process" isExecutable="true">
    <startEvent id="start" name="Start"/>
    <endEvent id="end" name="End"/>
    <sequenceFlow id="flow1" sourceRef="start" targetRef="end"/>
  </process>
</definitions>"""


class TestProcessRepository:
    """Tests for the ProcessRepository class."""

    def test_deploy_process(self):
        """Test deploying a new process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            process_id = repo.deploy(
                name="Test Process",
                bpmn_content=SIMPLE_BPMN,
                description="A test process",
                version="1.0.0",
            )

            assert process_id is not None
            assert len(process_id) == 36  # UUID length

    def test_get_process(self):
        """Test retrieving a deployed process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            process_id = repo.deploy(
                name="My Process",
                bpmn_content=SIMPLE_BPMN,
                description="Description here",
                version="2.0.0",
            )

            process = repo.get(process_id)

            assert process is not None
            assert process["id"] == process_id
            assert process["name"] == "My Process"
            assert process["description"] == "Description here"
            assert process["version"] == "2.0.0"
            assert process["status"] == "active"

    def test_get_nonexistent_process(self):
        """Test retrieving a process that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            process = repo.get("nonexistent-id")

            assert process is None

    def test_list_processes(self):
        """Test listing all processes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            # Deploy multiple processes
            repo.deploy(name="Process 1", bpmn_content=SIMPLE_BPMN)
            repo.deploy(name="Process 2", bpmn_content=SIMPLE_BPMN)
            repo.deploy(name="Process 3", bpmn_content=SIMPLE_BPMN)

            result = repo.list()

            assert result["total"] == 3
            assert len(result["processes"]) == 3
            assert result["page"] == 1
            assert result["page_size"] == 20

    def test_list_processes_with_pagination(self):
        """Test listing processes with pagination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            # Deploy 5 processes
            for i in range(5):
                repo.deploy(name=f"Process {i}", bpmn_content=SIMPLE_BPMN)

            # Get page 1 with page_size 2
            result = repo.list(page=1, page_size=2)
            assert len(result["processes"]) == 2
            assert result["total"] == 5

            # Get page 2
            result = repo.list(page=2, page_size=2)
            assert len(result["processes"]) == 2

            # Get page 3
            result = repo.list(page=3, page_size=2)
            assert len(result["processes"]) == 1

    def test_list_processes_filter_by_status(self):
        """Test filtering processes by status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            # Deploy processes with different statuses
            id1 = repo.deploy(name="Active 1", bpmn_content=SIMPLE_BPMN)
            id2 = repo.deploy(name="Active 2", bpmn_content=SIMPLE_BPMN)
            id3 = repo.deploy(name="Inactive", bpmn_content=SIMPLE_BPMN)

            # Make one inactive
            repo.update(id3, status="inactive")

            # Filter by active
            result = repo.list(status="active")
            assert result["total"] == 2

            # Filter by inactive
            result = repo.list(status="inactive")
            assert result["total"] == 1

    def test_update_process(self):
        """Test updating a process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            process_id = repo.deploy(
                name="Original Name",
                bpmn_content=SIMPLE_BPMN,
                description="Original description",
            )

            # Update
            updated = repo.update(
                process_id,
                name="New Name",
                description="New description",
                status="inactive",
            )

            assert updated is not None
            assert updated["name"] == "New Name"
            assert updated["description"] == "New description"
            assert updated["status"] == "inactive"
            assert updated["updated_at"] is not None

    def test_update_nonexistent_process(self):
        """Test updating a process that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            result = repo.update("nonexistent", name="New Name")

            assert result is None

    def test_delete_process(self):
        """Test deleting a process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            process_id = repo.deploy(name="To Delete", bpmn_content=SIMPLE_BPMN)

            # Verify it exists
            assert repo.exists(process_id)

            # Delete it
            result = repo.delete(process_id)
            assert result is True

            # Verify it's gone
            assert not repo.exists(process_id)
            assert repo.get(process_id) is None

    def test_get_graph(self):
        """Test extracting process-specific graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            process_id = repo.deploy(name="Test", bpmn_content=SIMPLE_BPMN)

            graph = repo.get_graph(process_id)

            assert graph is not None
            assert isinstance(graph, Graph)
            assert len(graph) > 0

    def test_get_graph_nonexistent(self):
        """Test extracting graph for nonexistent process."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            graph = repo.get_graph("nonexistent")

            assert graph is None

    def test_exists(self):
        """Test checking if process exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            assert not repo.exists("nonexistent")

            process_id = repo.deploy(name="Test", bpmn_content=SIMPLE_BPMN)

            assert repo.exists(process_id)

    def test_count(self):
        """Test counting processes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            assert repo.count() == 0

            repo.deploy(name="Process 1", bpmn_content=SIMPLE_BPMN)
            repo.deploy(name="Process 2", bpmn_content=SIMPLE_BPMN)

            assert repo.count() == 2

    def test_count_by_status(self):
        """Test counting processes by status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            id1 = repo.deploy(name="Active", bpmn_content=SIMPLE_BPMN)
            id2 = repo.deploy(name="Inactive", bpmn_content=SIMPLE_BPMN)
            repo.update(id2, status="inactive")

            assert repo.count(status="active") == 1
            assert repo.count(status="inactive") == 1
            assert repo.count() == 2

    def test_get_all_ids(self):
        """Test getting all process IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            repo = ProcessRepository(base)

            id1 = repo.deploy(name="Process 1", bpmn_content=SIMPLE_BPMN)
            id2 = repo.deploy(name="Process 2", bpmn_content=SIMPLE_BPMN)

            ids = repo.get_all_ids()

            assert len(ids) == 2
            assert id1 in ids
            assert id2 in ids


class TestProcessRepositoryPersistence:
    """Tests for process repository persistence."""

    def test_processes_persist_to_disk(self):
        """Test that processes are persisted to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Deploy with first instance
            base1 = BaseStorageService(tmpdir)
            repo1 = ProcessRepository(base1)

            process_id = repo1.deploy(
                name="Persistent Process",
                bpmn_content=SIMPLE_BPMN,
                description="Should persist",
            )

            # Load with new instance
            base2 = BaseStorageService(tmpdir)
            repo2 = ProcessRepository(base2)

            process = repo2.get(process_id)

            assert process is not None
            assert process["name"] == "Persistent Process"

    def test_updates_persist(self):
        """Test that updates are persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base1 = BaseStorageService(tmpdir)
            repo1 = ProcessRepository(base1)

            process_id = repo1.deploy(name="Original", bpmn_content=SIMPLE_BPMN)
            repo1.update(process_id, name="Updated")

            # Load with new instance
            base2 = BaseStorageService(tmpdir)
            repo2 = ProcessRepository(base2)

            process = repo2.get(process_id)

            assert process["name"] == "Updated"

    def test_deletes_persist(self):
        """Test that deletes are persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base1 = BaseStorageService(tmpdir)
            repo1 = ProcessRepository(base1)

            process_id = repo1.deploy(name="To Delete", bpmn_content=SIMPLE_BPMN)
            repo1.delete(process_id)

            # Load with new instance
            base2 = BaseStorageService(tmpdir)
            repo2 = ProcessRepository(base2)

            assert not repo2.exists(process_id)
