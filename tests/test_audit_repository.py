# Tests for Audit Repository
# Verifies audit log persistence and retrieval

import os
import tempfile
import pytest
from rdflib import URIRef

from src.api.storage.base import BaseStorageService, INST
from src.api.storage.audit_repository import AuditRepository


class TestAuditRepository:
    """Tests for the AuditRepository class."""

    def test_log_event(self):
        """Test logging a basic event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            instance_uri = INST["test-instance"]

            event_uri = audit.log_event(
                instance_uri=instance_uri,
                event_type="created",
                user="test-user",
                details="Process instance created",
            )

            # Verify event was created
            assert event_uri is not None
            assert "event_" in str(event_uri)

    def test_log_event_with_node(self):
        """Test logging an event with a node URI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            instance_uri = INST["test-instance"]
            node_uri = URIRef("http://example.org/node/task1")

            audit.log_event(
                instance_uri=instance_uri,
                event_type="task_completed",
                user="test-user",
                node_uri=node_uri,
            )

            events = audit.get_instance_audit_log("test-instance")

            assert len(events) == 1
            assert events[0]["node_uri"] == str(node_uri)

    def test_get_instance_audit_log(self):
        """Test retrieving audit log for an instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            instance_uri = INST["test-instance"]

            # Log multiple events
            audit.log_event(instance_uri, "created", "user1")
            audit.log_event(instance_uri, "task_claimed", "user2", "Task claimed")
            audit.log_event(instance_uri, "task_completed", "user2", "Task done")

            events = audit.get_instance_audit_log("test-instance")

            assert len(events) == 3
            assert events[0]["type"] == "created"
            assert events[1]["type"] == "task_claimed"
            assert events[2]["type"] == "task_completed"

    def test_get_instance_audit_log_filter_by_type(self):
        """Test filtering audit log by event type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            instance_uri = INST["test-instance"]

            audit.log_event(instance_uri, "created", "user1")
            audit.log_event(instance_uri, "task_completed", "user2")
            audit.log_event(instance_uri, "task_completed", "user3")

            events = audit.get_instance_audit_log(
                "test-instance", event_type="task_completed"
            )

            assert len(events) == 2
            assert all(e["type"] == "task_completed" for e in events)

    def test_get_instance_audit_log_with_limit(self):
        """Test limiting the number of returned events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            instance_uri = INST["test-instance"]

            # Log many events
            for i in range(10):
                audit.log_event(instance_uri, f"event_{i}", "user")

            events = audit.get_instance_audit_log("test-instance", limit=3)

            assert len(events) == 3

    def test_get_events_by_type(self):
        """Test getting all events of a specific type across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            # Log events for multiple instances
            audit.log_event(INST["instance-1"], "created", "user1")
            audit.log_event(INST["instance-1"], "completed", "user1")
            audit.log_event(INST["instance-2"], "created", "user2")
            audit.log_event(INST["instance-2"], "error", "system")
            audit.log_event(INST["instance-3"], "created", "user3")

            created_events = audit.get_events_by_type("created")

            assert len(created_events) == 3
            assert all(e["type"] == "created" for e in created_events)

    def test_delete_instance_events(self):
        """Test deleting all events for an instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            # Log events for two instances
            audit.log_event(INST["instance-1"], "created", "user1")
            audit.log_event(INST["instance-1"], "completed", "user1")
            audit.log_event(INST["instance-2"], "created", "user2")

            # Delete events for instance-1
            deleted_count = audit.delete_instance_events("instance-1")

            assert deleted_count == 2

            # Instance-1 should have no events
            events1 = audit.get_instance_audit_log("instance-1")
            assert len(events1) == 0

            # Instance-2 should still have its events
            events2 = audit.get_instance_audit_log("instance-2")
            assert len(events2) == 1

    def test_get_event_count(self):
        """Test getting event counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            audit.log_event(INST["instance-1"], "created", "user1")
            audit.log_event(INST["instance-1"], "completed", "user1")
            audit.log_event(INST["instance-2"], "created", "user2")

            # Total count
            assert audit.get_event_count() == 3

            # Count for specific instance
            assert audit.get_event_count("instance-1") == 2
            assert audit.get_event_count("instance-2") == 1
            assert audit.get_event_count("nonexistent") == 0

    def test_events_sorted_by_timestamp(self):
        """Test that events are returned sorted by timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            instance_uri = INST["test-instance"]

            # Log events (they should be in order due to sequential timestamps)
            audit.log_event(instance_uri, "first", "user")
            audit.log_event(instance_uri, "second", "user")
            audit.log_event(instance_uri, "third", "user")

            events = audit.get_instance_audit_log("test-instance")

            assert events[0]["type"] == "first"
            assert events[1]["type"] == "second"
            assert events[2]["type"] == "third"

    def test_persistence(self):
        """Test that audit events are persisted to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and log events
            base1 = BaseStorageService(tmpdir)
            audit1 = AuditRepository(base1)

            audit1.log_event(INST["test-instance"], "created", "user1")
            audit1.log_event(INST["test-instance"], "completed", "user1")

            # Create new instances from same storage
            base2 = BaseStorageService(tmpdir)
            audit2 = AuditRepository(base2)

            events = audit2.get_instance_audit_log("test-instance")

            assert len(events) == 2

    def test_log_event_no_save(self):
        """Test logging events without immediate save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            instance_uri = INST["test-instance"]

            # Log without saving
            audit.log_event(instance_uri, "event1", "user", save=False)
            audit.log_event(instance_uri, "event2", "user", save=False)

            # Events should be in memory
            events = audit.get_instance_audit_log("test-instance")
            assert len(events) == 2

            # But not persisted yet - check by creating new base storage
            base2 = BaseStorageService(tmpdir)
            audit2 = AuditRepository(base2)
            events2 = audit2.get_instance_audit_log("test-instance")
            assert len(events2) == 0

            # Now save explicitly
            base.save_audit()

            # Now it should be persisted
            base3 = BaseStorageService(tmpdir)
            audit3 = AuditRepository(base3)
            events3 = audit3.get_instance_audit_log("test-instance")
            assert len(events3) == 2

    def test_empty_audit_log(self):
        """Test getting audit log for instance with no events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            events = audit.get_instance_audit_log("nonexistent-instance")

            assert events == []

    def test_default_user_is_system(self):
        """Test that default user is 'System'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            audit = AuditRepository(base)

            # Log without specifying user
            audit.log_event(INST["test-instance"], "auto_event")

            events = audit.get_instance_audit_log("test-instance")

            assert events[0]["user"] == "System"
