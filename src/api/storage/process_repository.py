# Process Repository for SPEAR Engine
# Handles CRUD operations for process definitions

import os
import uuid
import logging
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from rdflib import Graph, Literal, RDF, RDFS

from .base import BaseStorageService, PROC, META, BPMN
from src.conversion import BPMNToRDFConverter

if TYPE_CHECKING:
    from rdflib import URIRef

logger = logging.getLogger(__name__)


class ProcessRepository:
    """
    Repository for managing BPMN process definitions.

    Handles:
    - Deploying new processes from BPMN XML
    - Retrieving process definitions
    - Updating process metadata
    - Deleting processes
    - Extracting process-specific RDF graphs

    Process definitions are stored in the definitions_graph with:
    - Process metadata (name, version, status, timestamps)
    - Linked BPMN elements converted to RDF triples
    """

    def __init__(self, base_storage: BaseStorageService):
        """
        Initialize the process repository.

        Args:
            base_storage: The base storage service providing graph access
        """
        self._storage = base_storage
        self._converter = BPMNToRDFConverter()

    @property
    def _graph(self) -> Graph:
        """Get the definitions graph."""
        return self._storage.definitions_graph

    def deploy(
        self,
        name: str,
        bpmn_content: str,
        description: Optional[str] = None,
        version: str = "1.0.0",
    ) -> str:
        """
        Deploy a new process definition from BPMN XML.

        Args:
            name: Human-readable process name
            bpmn_content: BPMN XML content
            description: Optional process description
            version: Process version (default "1.0.0")

        Returns:
            The generated process definition ID

        Raises:
            Exception: If BPMN parsing fails
        """
        process_id = str(uuid.uuid4())
        process_uri = PROC[process_id]

        # Write BPMN to temp file for conversion
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bpmn", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(bpmn_content)
            temp_file = tmp.name

        try:
            # Convert BPMN to RDF Graph
            bpmn_graph = self._converter.parse_bpmn_to_graph(temp_file)

            # Add process metadata
            self._graph.add((process_uri, RDF.type, PROC.ProcessDefinition))
            self._graph.add((process_uri, META.name, Literal(name)))
            self._graph.add((process_uri, META.version, Literal(version)))
            self._graph.add((process_uri, META.status, Literal("active")))
            self._graph.add(
                (process_uri, META.deployedAt, Literal(datetime.now().isoformat()))
            )
            self._graph.add((process_uri, RDFS.comment, Literal(description or "")))

            # Add all BPMN triples to definitions graph
            for s, p, o in bpmn_graph:
                self._graph.add((s, p, o))

            # Link process to its BPMN start events and process elements
            for s, p, o in bpmn_graph.triples((None, RDF.type, None)):
                o_lower = str(o).lower()
                if "startevent" in o_lower or "process" in o_lower:
                    self._graph.add((process_uri, PROC.hasElement, s))

            # Persist to disk
            self._storage.save_definitions()

            logger.info(f"Deployed process: {name} ({process_id})")
            return process_id

        finally:
            # Clean up temp file
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def get(self, process_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a process definition by ID.

        Args:
            process_id: The process definition ID

        Returns:
            Process data dictionary, or None if not found
        """
        process_uri = PROC[process_id]

        # Check if process exists
        if (process_uri, RDF.type, PROC.ProcessDefinition) not in self._graph:
            return None

        # Get metadata
        name = self._graph.value(process_uri, META.name)
        version = self._graph.value(process_uri, META.version)
        status = self._graph.value(process_uri, META.status)
        description = self._graph.value(process_uri, RDFS.comment)
        deployed_at = self._graph.value(process_uri, META.deployedAt)
        updated_at = self._graph.value(process_uri, META.updatedAt)

        # Count all triples in the graph (for info)
        triples_count = len(list(self._graph.triples((None, None, None))))

        # Use deployed_at for created_at
        created_at = deployed_at or updated_at

        return {
            "id": process_id,
            "name": str(name) if name else "",
            "version": str(version) if version else "1.0.0",
            "status": str(status) if status else "active",
            "description": str(description) if description else None,
            "rdf_triples_count": triples_count,
            "deployed_at": deployed_at,
            "created_at": created_at,
            "updated_at": updated_at or created_at,
        }

    def list(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        List all process definitions with pagination.

        Args:
            status: Optional filter by status (e.g., "active", "inactive")
            page: Page number (1-based)
            page_size: Number of items per page

        Returns:
            Dictionary with processes list and pagination info
        """
        processes = []

        # Find all process definitions
        for process_uri in self._graph.subjects(RDF.type, PROC.ProcessDefinition):
            process_id = str(process_uri).split("/")[-1]
            process_data = self.get(process_id)

            if process_data:
                # Filter by status if specified
                if status and process_data["status"] != status:
                    continue
                processes.append(process_data)

        # Calculate pagination
        total = len(processes)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_processes = processes[start:end]

        return {
            "processes": paginated_processes,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update(
        self,
        process_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update a process definition's metadata.

        Args:
            process_id: The process definition ID
            name: New name (if provided)
            description: New description (if provided)
            status: New status (if provided)

        Returns:
            Updated process data, or None if not found
        """
        process_uri = PROC[process_id]

        # Check if process exists
        if (process_uri, RDF.type, PROC.ProcessDefinition) not in self._graph:
            return None

        # Update provided fields
        if name:
            self._graph.set((process_uri, META.name, Literal(name)))
        if description is not None:
            self._graph.set((process_uri, RDFS.comment, Literal(description)))
        if status:
            self._graph.set((process_uri, META.status, Literal(status)))

        # Update timestamp
        self._graph.set(
            (process_uri, META.updatedAt, Literal(datetime.now().isoformat()))
        )

        # Persist changes
        self._storage.save_definitions()

        logger.info(f"Updated process: {process_id}")
        return self.get(process_id)

    def delete(self, process_id: str) -> bool:
        """
        Delete a process definition.

        Note: This only removes the process definition metadata and links.
        It does not remove associated BPMN element triples to avoid
        breaking other processes that might share them.

        Args:
            process_id: The process definition ID

        Returns:
            True if deleted (always returns True for idempotency)
        """
        process_uri = PROC[process_id]

        # Collect triples to remove
        triples_to_remove = list(self._graph.triples((process_uri, None, None)))
        triples_to_remove += list(self._graph.triples((None, None, process_uri)))

        # Remove the triples
        for s, p, o in triples_to_remove:
            self._graph.remove((s, p, o))

        # Persist changes
        self._storage.save_definitions()

        logger.info(f"Deleted process: {process_id}")
        return True

    def get_graph(self, process_id: str) -> Optional[Graph]:
        """
        Get a separate RDF graph containing only this process's triples.

        Useful for exporting a single process definition.

        Args:
            process_id: The process definition ID

        Returns:
            A new Graph containing the process triples, or None if not found
        """
        process_uri = PROC[process_id]

        # Check if process exists
        if (process_uri, RDF.type, PROC.ProcessDefinition) not in self._graph:
            return None

        # Extract process-specific triples
        process_graph = Graph()

        for s, p, o in self._graph:
            # Include if subject is the process or a BPMN element
            if str(s).startswith(str(process_uri)) or str(s).startswith(
                "http://example.org/bpmn/"
            ):
                process_graph.add((s, p, o))
            # Include if object references the process or a BPMN element
            if str(o).startswith(str(process_uri)) or str(o).startswith(
                "http://example.org/bpmn/"
            ):
                process_graph.add((s, p, o))

        return process_graph

    def exists(self, process_id: str) -> bool:
        """
        Check if a process definition exists.

        Args:
            process_id: The process definition ID

        Returns:
            True if the process exists
        """
        process_uri = PROC[process_id]
        return (process_uri, RDF.type, PROC.ProcessDefinition) in self._graph

    def count(self, status: Optional[str] = None) -> int:
        """
        Count process definitions.

        Args:
            status: Optional filter by status

        Returns:
            Number of process definitions
        """
        if status is None:
            return len(list(self._graph.subjects(RDF.type, PROC.ProcessDefinition)))

        count = 0
        for process_uri in self._graph.subjects(RDF.type, PROC.ProcessDefinition):
            proc_status = self._graph.value(process_uri, META.status)
            if proc_status and str(proc_status) == status:
                count += 1
        return count

    def get_all_ids(self) -> List[str]:
        """
        Get all process definition IDs.

        Returns:
            List of process IDs
        """
        ids = []
        for process_uri in self._graph.subjects(RDF.type, PROC.ProcessDefinition):
            process_id = str(process_uri).split("/")[-1]
            ids.append(process_id)
        return ids
