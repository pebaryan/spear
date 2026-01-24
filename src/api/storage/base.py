# Base Storage Service for SPEAR Engine
# Handles RDF graph management and persistence

import os
import logging
from typing import Optional
from rdflib import Graph, Namespace

logger = logging.getLogger(__name__)

# RDF Namespaces - shared across all storage modules
BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
PROC = Namespace("http://example.org/process/")
INST = Namespace("http://example.org/instance/")
VAR = Namespace("http://example.org/variables/")
LOG = Namespace("http://example.org/audit/")
META = Namespace("http://example.org/meta/")
TASK = Namespace("http://example.org/task/")


class BaseStorageService:
    """
    Base class for RDF graph management and persistence.

    Manages four separate RDF graphs:
    - definitions_graph: Process definitions (BPMN models)
    - instances_graph: Process instances (running processes)
    - audit_graph: Audit log entries
    - tasks_graph: User task data

    Each graph is persisted to its own Turtle file.
    """

    def __init__(self, storage_path: str = "data/spear_rdf"):
        """
        Initialize the base storage service.

        Args:
            storage_path: Directory path for storing RDF data files
        """
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

        # Initialize empty graphs
        self._definitions_graph = Graph()
        self._instances_graph = Graph()
        self._audit_graph = Graph()
        self._tasks_graph = Graph()

        # Load existing data from disk
        self._load_all_graphs()

        logger.info(f"Initialized base storage at {storage_path}")

    def _load_all_graphs(self) -> None:
        """Load all graphs from their respective files."""
        self._definitions_graph = self._load_graph("definitions.ttl")
        self._instances_graph = self._load_graph("instances.ttl")
        self._audit_graph = self._load_graph("audit.ttl")
        self._tasks_graph = self._load_graph("tasks.ttl")

    def _load_graph(self, filename: str) -> Graph:
        """
        Load a graph from file if it exists.

        BUG FIX: The original implementation always loaded into definitions_graph
        regardless of the filename. This version correctly returns a new Graph
        containing the loaded data.

        Args:
            filename: Name of the turtle file to load

        Returns:
            Graph containing the loaded data, or empty Graph if file doesn't exist
        """
        graph = Graph()
        filepath = os.path.join(self.storage_path, filename)

        if os.path.exists(filepath):
            try:
                graph.parse(filepath, format="turtle")
                logger.info(f"Loaded graph from {filepath} ({len(graph)} triples)")
            except Exception as e:
                logger.warning(f"Failed to load {filepath}: {e}")

        return graph

    def _save_graph(self, graph: Graph, filename: str) -> None:
        """
        Save a graph to file.

        Args:
            graph: RDF Graph to save
            filename: Name of the turtle file to save to
        """
        filepath = os.path.join(self.storage_path, filename)
        graph.serialize(filepath, format="turtle")
        logger.debug(f"Saved graph to {filepath} ({len(graph)} triples)")

    def save_definitions(self) -> None:
        """Save the definitions graph to disk."""
        self._save_graph(self._definitions_graph, "definitions.ttl")

    def save_instances(self) -> None:
        """Save the instances graph to disk."""
        self._save_graph(self._instances_graph, "instances.ttl")

    def save_audit(self) -> None:
        """Save the audit graph to disk."""
        self._save_graph(self._audit_graph, "audit.ttl")

    def save_tasks(self) -> None:
        """Save the tasks graph to disk."""
        self._save_graph(self._tasks_graph, "tasks.ttl")

    def save_all(self) -> None:
        """Save all graphs to disk."""
        self.save_definitions()
        self.save_instances()
        self.save_audit()
        self.save_tasks()

    # Graph properties for controlled access

    @property
    def definitions_graph(self) -> Graph:
        """Get the process definitions graph."""
        return self._definitions_graph

    @property
    def instances_graph(self) -> Graph:
        """Get the process instances graph."""
        return self._instances_graph

    @property
    def audit_graph(self) -> Graph:
        """Get the audit log graph."""
        return self._audit_graph

    @property
    def tasks_graph(self) -> Graph:
        """Get the tasks graph."""
        return self._tasks_graph

    def clear_all(self) -> None:
        """
        Clear all graphs and delete persisted files.

        USE WITH CAUTION - this deletes all data!
        """
        self._definitions_graph = Graph()
        self._instances_graph = Graph()
        self._audit_graph = Graph()
        self._tasks_graph = Graph()

        # Delete files if they exist
        for filename in ["definitions.ttl", "instances.ttl", "audit.ttl", "tasks.ttl"]:
            filepath = os.path.join(self.storage_path, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Deleted {filepath}")

        logger.warning("Cleared all storage data")

    def get_stats(self) -> dict:
        """
        Get statistics about the stored data.

        Returns:
            Dictionary with triple counts for each graph
        """
        return {
            "definitions_triples": len(self._definitions_graph),
            "instances_triples": len(self._instances_graph),
            "audit_triples": len(self._audit_graph),
            "tasks_triples": len(self._tasks_graph),
            "total_triples": (
                len(self._definitions_graph)
                + len(self._instances_graph)
                + len(self._audit_graph)
                + len(self._tasks_graph)
            ),
            "storage_path": self.storage_path,
        }
