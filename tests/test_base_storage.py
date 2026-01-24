# Tests for Base Storage Service
# Verifies RDF graph management and persistence

import os
import tempfile
import pytest
from rdflib import Graph, Literal, URIRef, RDF

from src.api.storage.base import BaseStorageService, BPMN, PROC


class TestBaseStorageService:
    """Tests for the BaseStorageService class."""

    def test_initialization_creates_directory(self):
        """Test that initialization creates the storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "new_storage")

            # Directory doesn't exist yet
            assert not os.path.exists(storage_path)

            # Initialize storage
            storage = BaseStorageService(storage_path)

            # Directory should now exist
            assert os.path.exists(storage_path)

    def test_initialization_creates_empty_graphs(self):
        """Test that initialization creates four empty graphs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = BaseStorageService(tmpdir)

            assert isinstance(storage.definitions_graph, Graph)
            assert isinstance(storage.instances_graph, Graph)
            assert isinstance(storage.audit_graph, Graph)
            assert isinstance(storage.tasks_graph, Graph)

            # All graphs should be empty on fresh init
            assert len(storage.definitions_graph) == 0
            assert len(storage.instances_graph) == 0
            assert len(storage.audit_graph) == 0
            assert len(storage.tasks_graph) == 0

    def test_save_and_load_definitions(self):
        """Test saving and loading the definitions graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create storage and add some triples
            storage1 = BaseStorageService(tmpdir)

            process_uri = PROC["test-process"]
            storage1.definitions_graph.add((process_uri, RDF.type, BPMN.Process))
            storage1.definitions_graph.add(
                (process_uri, BPMN.name, Literal("Test Process"))
            )

            # Save to disk
            storage1.save_definitions()

            # Create new storage instance from same path
            storage2 = BaseStorageService(tmpdir)

            # Data should be loaded
            assert len(storage2.definitions_graph) == 2
            assert (process_uri, RDF.type, BPMN.Process) in storage2.definitions_graph

    def test_save_and_load_instances(self):
        """Test saving and loading the instances graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage1 = BaseStorageService(tmpdir)

            from src.api.storage.base import INST

            instance_uri = INST["test-instance"]
            storage1.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))

            storage1.save_instances()

            storage2 = BaseStorageService(tmpdir)
            assert len(storage2.instances_graph) == 1
            assert (
                instance_uri,
                RDF.type,
                BPMN.ProcessInstance,
            ) in storage2.instances_graph

    def test_save_and_load_audit(self):
        """Test saving and loading the audit graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage1 = BaseStorageService(tmpdir)

            from src.api.storage.base import LOG

            event_uri = LOG["test-event"]
            storage1.audit_graph.add((event_uri, RDF.type, LOG.AuditEvent))

            storage1.save_audit()

            storage2 = BaseStorageService(tmpdir)
            assert len(storage2.audit_graph) == 1

    def test_save_and_load_tasks(self):
        """Test saving and loading the tasks graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage1 = BaseStorageService(tmpdir)

            from src.api.storage.base import TASK

            task_uri = TASK["test-task"]
            storage1.tasks_graph.add((task_uri, RDF.type, TASK.UserTask))

            storage1.save_tasks()

            storage2 = BaseStorageService(tmpdir)
            assert len(storage2.tasks_graph) == 1

    def test_save_all(self):
        """Test saving all graphs at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage1 = BaseStorageService(tmpdir)

            # Add triples to each graph
            storage1.definitions_graph.add((PROC["p1"], RDF.type, BPMN.Process))
            from src.api.storage.base import INST, LOG, TASK

            storage1.instances_graph.add((INST["i1"], RDF.type, BPMN.ProcessInstance))
            storage1.audit_graph.add((LOG["e1"], RDF.type, LOG.AuditEvent))
            storage1.tasks_graph.add((TASK["t1"], RDF.type, TASK.UserTask))

            # Save all
            storage1.save_all()

            # Verify files exist
            assert os.path.exists(os.path.join(tmpdir, "definitions.ttl"))
            assert os.path.exists(os.path.join(tmpdir, "instances.ttl"))
            assert os.path.exists(os.path.join(tmpdir, "audit.ttl"))
            assert os.path.exists(os.path.join(tmpdir, "tasks.ttl"))

            # Verify data loads correctly
            storage2 = BaseStorageService(tmpdir)
            assert len(storage2.definitions_graph) == 1
            assert len(storage2.instances_graph) == 1
            assert len(storage2.audit_graph) == 1
            assert len(storage2.tasks_graph) == 1

    def test_load_graph_bug_fix(self):
        """
        Test that the _load_graph bug is fixed.

        The original bug: _load_graph always loaded into definitions_graph
        regardless of the filename parameter.

        This test verifies each graph is loaded into its own separate graph.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create initial storage with different data in each graph
            storage1 = BaseStorageService(tmpdir)

            # Add unique triples to each graph
            storage1.definitions_graph.add((PROC["def-only"], RDF.type, BPMN.Process))

            from src.api.storage.base import INST, LOG, TASK

            storage1.instances_graph.add(
                (INST["inst-only"], RDF.type, BPMN.ProcessInstance)
            )
            storage1.audit_graph.add((LOG["audit-only"], RDF.type, LOG.AuditEvent))
            storage1.tasks_graph.add((TASK["task-only"], RDF.type, TASK.UserTask))

            storage1.save_all()

            # Load into new storage
            storage2 = BaseStorageService(tmpdir)

            # BUG CHECK: Each graph should only contain its own data
            # Before fix: All data would be in definitions_graph

            # Definitions should NOT contain instance/audit/task data
            assert (
                PROC["def-only"],
                RDF.type,
                BPMN.Process,
            ) in storage2.definitions_graph
            assert (
                INST["inst-only"],
                RDF.type,
                BPMN.ProcessInstance,
            ) not in storage2.definitions_graph
            assert (
                LOG["audit-only"],
                RDF.type,
                LOG.AuditEvent,
            ) not in storage2.definitions_graph
            assert (
                TASK["task-only"],
                RDF.type,
                TASK.UserTask,
            ) not in storage2.definitions_graph

            # Instances should only contain instance data
            assert (
                INST["inst-only"],
                RDF.type,
                BPMN.ProcessInstance,
            ) in storage2.instances_graph
            assert (
                PROC["def-only"],
                RDF.type,
                BPMN.Process,
            ) not in storage2.instances_graph

            # Audit should only contain audit data
            assert (LOG["audit-only"], RDF.type, LOG.AuditEvent) in storage2.audit_graph
            assert (
                PROC["def-only"],
                RDF.type,
                BPMN.Process,
            ) not in storage2.audit_graph

            # Tasks should only contain task data
            assert (TASK["task-only"], RDF.type, TASK.UserTask) in storage2.tasks_graph
            assert (
                PROC["def-only"],
                RDF.type,
                BPMN.Process,
            ) not in storage2.tasks_graph

    def test_clear_all(self):
        """Test clearing all data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = BaseStorageService(tmpdir)

            # Add data and save
            storage.definitions_graph.add((PROC["p1"], RDF.type, BPMN.Process))
            storage.save_all()

            # Clear everything
            storage.clear_all()

            # All graphs should be empty
            assert len(storage.definitions_graph) == 0
            assert len(storage.instances_graph) == 0
            assert len(storage.audit_graph) == 0
            assert len(storage.tasks_graph) == 0

            # Files should be deleted
            assert not os.path.exists(os.path.join(tmpdir, "definitions.ttl"))

    def test_get_stats(self):
        """Test getting storage statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = BaseStorageService(tmpdir)

            # Add varying amounts of data
            storage.definitions_graph.add((PROC["p1"], RDF.type, BPMN.Process))
            storage.definitions_graph.add((PROC["p2"], RDF.type, BPMN.Process))

            from src.api.storage.base import INST

            storage.instances_graph.add((INST["i1"], RDF.type, BPMN.ProcessInstance))

            stats = storage.get_stats()

            assert stats["definitions_triples"] == 2
            assert stats["instances_triples"] == 1
            assert stats["audit_triples"] == 0
            assert stats["tasks_triples"] == 0
            assert stats["total_triples"] == 3
            assert stats["storage_path"] == tmpdir

    def test_load_nonexistent_file(self):
        """Test that loading a nonexistent file returns empty graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = BaseStorageService(tmpdir)

            # Should handle missing files gracefully
            assert len(storage.definitions_graph) == 0

    def test_load_corrupted_file_handled(self):
        """Test that loading a corrupted file is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a corrupted turtle file
            corrupted_path = os.path.join(tmpdir, "definitions.ttl")
            with open(corrupted_path, "w") as f:
                f.write("this is not valid turtle syntax @#$%^&*()")

            # Should not raise, just log warning and return empty graph
            storage = BaseStorageService(tmpdir)

            # Graph should be empty (failed to parse)
            assert len(storage.definitions_graph) == 0

    def test_graphs_are_independent(self):
        """Test that modifying one graph doesn't affect others."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = BaseStorageService(tmpdir)

            # Add to definitions
            storage.definitions_graph.add((PROC["p1"], RDF.type, BPMN.Process))

            # Other graphs should be unaffected
            assert len(storage.instances_graph) == 0
            assert len(storage.audit_graph) == 0
            assert len(storage.tasks_graph) == 0
