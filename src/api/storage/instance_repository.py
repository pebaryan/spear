# Instance Repository for SPEAR Engine
# Handles process instance lifecycle (create, read, update, stop, cancel)

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from rdflib import Graph, URIRef, Literal, RDF

from src.api.storage.base import BaseStorageService, BPMN, PROC, INST, VAR, LOG

logger = logging.getLogger(__name__)


class InstanceRepository(BaseStorageService):
    """
    Repository for managing process instances.

    Handles:
    - Creating new process instances
    - Retrieving instance data
    - Listing instances with pagination/filtering
    - Stopping/cancelling instances
    - Instance lifecycle management
    """

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
        audit_graph: Graph,
        data_dir: str = "data",
    ):
        """
        Initialize the instance repository.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
            audit_graph: Graph containing audit log entries
            data_dir: Directory for persisting data
        """
        super().__init__(data_dir)
        self._definitions = definitions_graph
        self._instances = instances_graph
        self._audit = audit_graph

    # ==================== Instance Creation ====================

    def create_instance(
        self,
        process_id: str,
        variables: Optional[Dict[str, Any]] = None,
        start_event_id: Optional[str] = None,
        execute_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Create and optionally start a new process instance.

        Args:
            process_id: ID of the process definition to instantiate
            variables: Optional initial variables
            start_event_id: Optional specific start event ID
            execute_callback: Optional callback to execute the instance
            log_callback: Optional callback to log events

        Returns:
            Dictionary with instance data including id, process_id, status, variables

        Raises:
            ValueError: If process definition not found
        """
        process_uri = PROC[process_id]

        # Verify process exists
        if (process_uri, RDF.type, PROC.ProcessDefinition) not in self._definitions:
            raise ValueError(f"Process {process_id} not found")

        instance_id = str(uuid.uuid4())
        instance_uri = INST[instance_id]

        # Create instance metadata
        self._instances.add((instance_uri, RDF.type, INST.ProcessInstance))
        self._instances.add((instance_uri, INST.processDefinition, process_uri))
        self._instances.add((instance_uri, INST.status, Literal("RUNNING")))
        self._instances.add(
            (instance_uri, INST.createdAt, Literal(datetime.now().isoformat()))
        )

        # Add variables
        if variables:
            for name, value in variables.items():
                var_uri = VAR[f"{instance_id}_{name}"]
                self._instances.add((instance_uri, INST.hasVariable, var_uri))
                self._instances.add((var_uri, VAR.name, Literal(name)))
                self._instances.add((var_uri, VAR.value, Literal(str(value))))

        # Create initial token
        token_uri = INST[f"token_{instance_id}"]
        self._instances.add((token_uri, RDF.type, INST.Token))
        self._instances.add((token_uri, INST.belongsTo, instance_uri))
        self._instances.add((token_uri, INST.status, Literal("ACTIVE")))
        self._instances.add((instance_uri, INST.hasToken, token_uri))

        # Find start event
        start_event_uri = self._find_start_event(process_uri, start_event_id)
        if start_event_uri:
            self._instances.add((token_uri, INST.currentNode, start_event_uri))
            logger.debug(f"Setting token currentNode to: {start_event_uri}")

        # Log instance creation
        if log_callback:
            log_callback(instance_uri, "CREATED", "System", "")

        # Save instances graph
        self._save_graph(self._instances, "instances.ttl")

        logger.info(f"Created instance {instance_id} for process {process_id}")

        # Execute the instance if callback provided
        if execute_callback:
            execute_callback(instance_uri, instance_id)

        return {
            "id": instance_id,
            "process_id": process_id,
            "status": "RUNNING",
            "variables": variables or {},
        }

    def _find_start_event(
        self, process_uri: URIRef, start_event_id: Optional[str] = None
    ) -> Optional[URIRef]:
        """
        Find the start event for a process.

        Args:
            process_uri: URI of the process definition
            start_event_id: Optional specific start event ID

        Returns:
            URI of the start event or None
        """
        if start_event_id:
            return URIRef(f"http://example.org/bpmn/{start_event_id}")

        # Find first start event linked to this process definition
        for _, _, elem in self._definitions.triples(
            (process_uri, PROC.hasElement, None)
        ):
            for _, _, oo in self._definitions.triples((elem, RDF.type, None)):
                if "startevent" in str(oo).lower():
                    logger.debug(f"Found start event: {elem}")
                    return elem

        return None

    # ==================== Instance Retrieval ====================

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a process instance by ID.

        Args:
            instance_id: The instance ID

        Returns:
            Dictionary with instance data or None if not found
        """
        instance_uri = INST[instance_id]

        if (instance_uri, RDF.type, INST.ProcessInstance) not in self._instances:
            return None

        # Get instance data
        status = self._instances.value(instance_uri, INST.status)
        created_at = self._instances.value(instance_uri, INST.createdAt)
        updated_at = self._instances.value(instance_uri, INST.updatedAt)

        process_def = self._instances.value(instance_uri, INST.processDefinition)
        process_id = str(process_def).split("/")[-1] if process_def else None

        # Get variables
        variables = {}
        for var_uri in self._instances.objects(instance_uri, INST.hasVariable):
            name = self._instances.value(var_uri, VAR.name)
            value = self._instances.value(var_uri, VAR.value)
            if name and value:
                variables[str(name)] = str(value)

        # Get current nodes from tokens
        current_nodes = []
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            node = self._instances.value(token_uri, INST.currentNode)
            if node:
                current_nodes.append(str(node))

        return {
            "id": instance_id,
            "process_id": process_id,
            "status": str(status) if status else "UNKNOWN",
            "current_nodes": current_nodes,
            "variables": variables,
            "created_at": str(created_at) if created_at else None,
            "updated_at": str(updated_at) if updated_at else None,
        }

    def instance_exists(self, instance_id: str) -> bool:
        """
        Check if an instance exists.

        Args:
            instance_id: The instance ID

        Returns:
            True if instance exists
        """
        instance_uri = INST[instance_id]
        return (instance_uri, RDF.type, INST.ProcessInstance) in self._instances

    def get_instance_uri(self, instance_id: str) -> URIRef:
        """
        Get the URI for an instance.

        Args:
            instance_id: The instance ID

        Returns:
            URIRef for the instance
        """
        return INST[instance_id]

    # ==================== Instance Listing ====================

    def list_instances(
        self,
        process_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        List process instances with optional filtering and pagination.

        Args:
            process_id: Filter by process ID
            status: Filter by status
            page: Page number (1-indexed)
            page_size: Number of items per page

        Returns:
            Dictionary with instances list, total count, page, page_size
        """
        instances = []

        for instance_uri in self._instances.subjects(RDF.type, INST.ProcessInstance):
            instance_id = str(instance_uri).split("/")[-1]
            instance_data = self.get_instance(instance_id)

            if instance_data:
                # Filter by process ID
                if process_id and instance_data["process_id"] != process_id:
                    continue
                # Filter by status
                if status and instance_data["status"] != status:
                    continue
                instances.append(instance_data)

        # Pagination
        total = len(instances)
        start = (page - 1) * page_size
        end = start + page_size
        instances = instances[start:end]

        return {
            "instances": instances,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ==================== Instance Status Management ====================

    def stop_instance(
        self,
        instance_id: str,
        reason: str = "User request",
        log_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Stop a running process instance.

        Args:
            instance_id: The instance ID
            reason: Reason for stopping
            log_callback: Optional callback to log events

        Returns:
            Updated instance data

        Raises:
            ValueError: If instance not found
        """
        instance_uri = INST[instance_id]

        if (instance_uri, RDF.type, INST.ProcessInstance) not in self._instances:
            raise ValueError(f"Instance {instance_id} not found")

        # Update status
        self._instances.set((instance_uri, INST.status, Literal("TERMINATED")))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        # Log termination
        if log_callback:
            log_callback(instance_uri, "TERMINATED", "System", reason)

        self._save_graph(self._instances, "instances.ttl")

        logger.info(f"Stopped instance {instance_id}: {reason}")

        return self.get_instance(instance_id)

    def cancel_instance(
        self,
        instance_id: str,
        reason: Optional[str] = None,
        log_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Cancel a process instance (external cancellation).

        Args:
            instance_id: The process instance ID
            reason: Optional cancellation reason
            log_callback: Optional callback to log events

        Returns:
            Dictionary with updated instance state

        Raises:
            ValueError: If instance not found or already completed
        """
        instance_uri = INST[instance_id]

        if (instance_uri, RDF.type, INST.ProcessInstance) not in self._instances:
            raise ValueError(f"Instance {instance_id} not found")

        current_status = self._instances.value(instance_uri, INST.status)
        if current_status and str(current_status) in [
            "COMPLETED",
            "TERMINATED",
            "CANCELLED",
        ]:
            raise ValueError(f"Instance {instance_id} is already {current_status}")

        logger.info(f"Cancelling instance {instance_id}: {reason}")

        # Log cancellation
        if log_callback:
            log_callback(
                instance_uri,
                "INSTANCE_CANCELLED",
                "System",
                f"Instance cancelled externally: {reason}",
            )

        # Consume all active/waiting tokens
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            status = self._instances.value(token_uri, INST.status)
            if status and str(status) in ["ACTIVE", "WAITING"]:
                self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        # Update instance status
        self._instances.set((instance_uri, INST.status, Literal("CANCELLED")))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        self._save_graph(self._instances, "instances.ttl")

        return self.get_instance(instance_id)

    def set_instance_status(
        self,
        instance_id: str,
        status: str,
    ) -> None:
        """
        Set the status of an instance.

        Args:
            instance_id: The instance ID
            status: New status value
        """
        instance_uri = INST[instance_id]
        self._instances.set((instance_uri, INST.status, Literal(status)))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

    def get_instance_status(self, instance_id: str) -> Optional[str]:
        """
        Get the status of an instance.

        Args:
            instance_id: The instance ID

        Returns:
            Status string or None
        """
        instance_uri = INST[instance_id]
        status = self._instances.value(instance_uri, INST.status)
        return str(status) if status else None

    # ==================== Instance Tokens ====================

    def get_instance_tokens(self, instance_id: str) -> List[URIRef]:
        """
        Get all tokens for an instance.

        Args:
            instance_id: The instance ID

        Returns:
            List of token URIs
        """
        instance_uri = INST[instance_id]
        return list(self._instances.objects(instance_uri, INST.hasToken))

    def get_active_tokens(self, instance_id: str) -> List[URIRef]:
        """
        Get all active tokens for an instance.

        Args:
            instance_id: The instance ID

        Returns:
            List of active token URIs
        """
        instance_uri = INST[instance_id]
        active_tokens = []

        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            status = self._instances.value(token_uri, INST.status)
            if status and str(status) == "ACTIVE":
                active_tokens.append(token_uri)

        return active_tokens

    # ==================== Process Definition Access ====================

    def get_process_definition_uri(self, instance_id: str) -> Optional[URIRef]:
        """
        Get the process definition URI for an instance.

        Args:
            instance_id: The instance ID

        Returns:
            Process definition URI or None
        """
        instance_uri = INST[instance_id]
        return self._instances.value(instance_uri, INST.processDefinition)

    # ==================== Persistence ====================

    def save(self) -> None:
        """Save the instances graph to disk."""
        self._save_graph(self._instances, "instances.ttl")
