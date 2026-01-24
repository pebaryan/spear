# Audit Repository for SPEAR Engine
# Handles audit log persistence and retrieval

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from rdflib import URIRef, Literal, RDF

from .base import BaseStorageService, LOG, INST

if TYPE_CHECKING:
    from rdflib import Graph

logger = logging.getLogger(__name__)


class AuditRepository:
    """
    Repository for managing audit log entries.

    Audit logs track significant events in process instance lifecycle:
    - Instance creation, completion, termination
    - Task creation, claims, completions
    - Variable changes
    - Error events

    All audit entries are stored in the audit_graph and persisted
    to audit.ttl.
    """

    def __init__(self, base_storage: BaseStorageService):
        """
        Initialize the audit repository.

        Args:
            base_storage: The base storage service providing graph access
        """
        self._storage = base_storage

    @property
    def _graph(self) -> "Graph":
        """Get the audit graph."""
        return self._storage.audit_graph

    def log_event(
        self,
        instance_uri: URIRef,
        event_type: str,
        user: str = "System",
        details: str = "",
        node_uri: Optional[URIRef] = None,
        save: bool = True,
    ) -> URIRef:
        """
        Log an event for an instance.

        Args:
            instance_uri: URI of the process instance
            event_type: Type of event (e.g., "created", "completed", "error")
            user: User who triggered the event
            details: Additional details about the event
            node_uri: Optional URI of the node where the event occurred
            save: Whether to save the graph immediately (default True)

        Returns:
            URI of the created event
        """
        event_id = str(uuid.uuid4())
        event_uri = LOG[f"event_{event_id}"]

        self._graph.add((event_uri, RDF.type, LOG.Event))
        self._graph.add((event_uri, LOG.instance, instance_uri))
        self._graph.add((event_uri, LOG.eventType, Literal(event_type)))
        self._graph.add((event_uri, LOG.user, Literal(user)))
        self._graph.add((event_uri, LOG.timestamp, Literal(datetime.now().isoformat())))

        if details:
            self._graph.add((event_uri, LOG.details, Literal(details)))

        if node_uri:
            self._graph.add((event_uri, LOG.node, node_uri))

        if save:
            self._storage.save_audit()

        logger.debug(f"Logged {event_type} event for instance {instance_uri}")
        return event_uri

    def get_instance_audit_log(
        self,
        instance_id: str,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get the audit log for an instance.

        Args:
            instance_id: ID of the process instance
            event_type: Optional filter by event type
            limit: Optional maximum number of events to return

        Returns:
            List of audit events sorted by timestamp (oldest first)
        """
        instance_uri = INST[instance_id]
        events = []

        for event_uri in self._graph.subjects(LOG.instance, instance_uri):
            evt_type = self._graph.value(event_uri, LOG.eventType)

            # Filter by event type if specified
            if event_type and str(evt_type) != event_type:
                continue

            user = self._graph.value(event_uri, LOG.user)
            timestamp = self._graph.value(event_uri, LOG.timestamp)
            details = self._graph.value(event_uri, LOG.details)
            node = self._graph.value(event_uri, LOG.node)

            events.append(
                {
                    "id": str(event_uri).split("event_")[-1],
                    "type": str(evt_type) if evt_type else "",
                    "user": str(user) if user else "",
                    "timestamp": str(timestamp) if timestamp else "",
                    "details": str(details) if details else "",
                    "node_uri": str(node) if node else None,
                }
            )

        # Sort by timestamp
        sorted_events = sorted(events, key=lambda x: x["timestamp"])

        # Apply limit if specified
        if limit:
            sorted_events = sorted_events[:limit]

        return sorted_events

    def get_events_by_type(
        self,
        event_type: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all audit events of a specific type across all instances.

        Args:
            event_type: Type of events to retrieve
            limit: Optional maximum number of events to return

        Returns:
            List of audit events sorted by timestamp (newest first)
        """
        events = []

        for event_uri in self._graph.subjects(RDF.type, LOG.Event):
            evt_type = self._graph.value(event_uri, LOG.eventType)

            if str(evt_type) != event_type:
                continue

            instance = self._graph.value(event_uri, LOG.instance)
            user = self._graph.value(event_uri, LOG.user)
            timestamp = self._graph.value(event_uri, LOG.timestamp)
            details = self._graph.value(event_uri, LOG.details)

            events.append(
                {
                    "id": str(event_uri).split("event_")[-1],
                    "instance_uri": str(instance) if instance else None,
                    "type": str(evt_type) if evt_type else "",
                    "user": str(user) if user else "",
                    "timestamp": str(timestamp) if timestamp else "",
                    "details": str(details) if details else "",
                }
            )

        # Sort by timestamp (newest first)
        sorted_events = sorted(events, key=lambda x: x["timestamp"], reverse=True)

        if limit:
            sorted_events = sorted_events[:limit]

        return sorted_events

    def delete_instance_events(self, instance_id: str) -> int:
        """
        Delete all audit events for an instance.

        Args:
            instance_id: ID of the process instance

        Returns:
            Number of events deleted
        """
        instance_uri = INST[instance_id]
        deleted_count = 0

        # Find all events for this instance
        event_uris = list(self._graph.subjects(LOG.instance, instance_uri))

        for event_uri in event_uris:
            # Remove all triples with this event as subject
            self._graph.remove((event_uri, None, None))
            deleted_count += 1

        if deleted_count > 0:
            self._storage.save_audit()
            logger.info(
                f"Deleted {deleted_count} audit events for instance {instance_id}"
            )

        return deleted_count

    def get_event_count(self, instance_id: Optional[str] = None) -> int:
        """
        Get the count of audit events.

        Args:
            instance_id: Optional instance ID to count events for

        Returns:
            Number of audit events
        """
        if instance_id:
            instance_uri = INST[instance_id]
            return len(list(self._graph.subjects(LOG.instance, instance_uri)))
        else:
            return len(list(self._graph.subjects(RDF.type, LOG.Event)))
