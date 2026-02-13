# RDF Storage Service for SPEAR API
# Handles all process definitions and instances as RDF triples

import os
import uuid
import re
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, List
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef, BNode
from src.core import ProcessInstance, Token
from src.conversion import BPMNToRDFConverter
import logging

logger = logging.getLogger(__name__)

# RDF Namespaces
BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
PROC = Namespace("http://example.org/process/")
INST = Namespace("http://example.org/instance/")
VAR = Namespace("http://example.org/variables/")
LOG = Namespace("http://example.org/audit/")
META = Namespace("http://example.org/meta/")
TASK = Namespace("http://example.org/task/")


class RDFStorageService:
    """
    Service for managing all SPEAR data as RDF triples.

    Handles:
    - Process definitions storage and retrieval
    - Process instance lifecycle management
    - Variables and audit logging
    """

    def __init__(self, storage_path: str = "data/spear_rdf"):
        """
        Initialize RDF storage service.

        Args:
            storage_path: Path to store RDF data files
        """
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

        # Initialize all graphs first, then load persisted data.
        self.definitions_graph = Graph()
        self.instances_graph = Graph()
        self.audit_graph = Graph()
        self.tasks_graph = Graph()

        self._load_graph("definitions.ttl")
        self._load_graph("instances.ttl")
        self._load_graph("audit.ttl")
        self._load_graph("tasks.ttl")

        # Topic registry for service task handlers
        self.topic_handlers = {}

        # Message registry for receive tasks and event-based gateways
        self.message_handlers = {}

        # Pending messages waiting for correlation
        self.pending_messages = []

        # Script task execution - disabled by default for security
        self.script_tasks_enabled = False

        # BPMN converter for deployment
        self.converter = BPMNToRDFConverter()

        logger.info(f"Initialized RDF storage at {storage_path}")

    def _load_graph(self, filename: str):
        """Load a graph from file if it exists."""
        graph_map = {
            "definitions.ttl": self.definitions_graph,
            "instances.ttl": self.instances_graph,
            "audit.ttl": self.audit_graph,
            "tasks.ttl": self.tasks_graph,
        }
        target_graph = graph_map.get(filename)
        if target_graph is None:
            logger.warning(f"Unknown graph file: {filename}")
            return

        filepath = os.path.join(self.storage_path, filename)
        if os.path.exists(filepath):
            try:
                target_graph.parse(filepath, format="turtle")
                logger.info(f"Loaded graph from {filepath}")
            except Exception as e:
                logger.warning(f"Failed to load {filepath}: {e}")

    def _save_graph(self, graph: Graph, filename: str):
        """Save a graph to file"""
        filepath = os.path.join(self.storage_path, filename)
        graph.serialize(filepath, format="turtle")
        logger.debug(f"Saved graph to {filepath}")

    # ==================== Process Definition Operations ====================

    def deploy_process(
        self,
        name: str,
        description: Optional[str],
        bpmn_content: str,
        version: str = "1.0.0",
    ) -> str:
        """
        Deploy a new process definition from BPMN XML.

        Args:
            name: Human-readable process name
            description: Process description
            bpmn_content: BPMN XML content
            version: Process version

        Returns:
            Process definition ID
        """
        process_id = str(uuid.uuid4())
        process_uri = PROC[process_id]

        # Convert BPMN to RDF
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bpmn", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(bpmn_content)
            temp_file = tmp.name

        try:
            # Convert to RDF Graph
            bpmn_graph = self.converter.parse_bpmn_to_graph(temp_file)

            # Add metadata
            self.definitions_graph.add((process_uri, RDF.type, PROC.ProcessDefinition))
            self.definitions_graph.add((process_uri, META.name, Literal(name)))
            self.definitions_graph.add((process_uri, META.version, Literal(version)))
            self.definitions_graph.add((process_uri, META.status, Literal("active")))
            self.definitions_graph.add(
                (process_uri, META.deployedAt, Literal(datetime.now().isoformat()))
            )
            self.definitions_graph.add(
                (process_uri, RDFS.comment, Literal(description or ""))
            )

            # Add the BPMN triples to definitions graph
            for s, p, o in bpmn_graph:
                self.definitions_graph.add((s, p, o))

            # Link process to its BPMN elements
            for s, p, o in bpmn_graph.triples((None, RDF.type, None)):
                o_lower = str(o).lower()
                if "startevent" in o_lower or "process" in o_lower:
                    self.definitions_graph.add((process_uri, PROC.hasElement, s))

            # Save to disk
            self._save_graph(self.definitions_graph, "definitions.ttl")

            logger.info(f"Deployed process: {name} ({process_id})")
            return process_id

        finally:
            # Clean up temp file
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def get_process(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Get a process definition by ID"""
        process_uri = PROC[process_id]

        # Check if process exists
        if (
            not (process_uri, RDF.type, PROC.ProcessDefinition)
            in self.definitions_graph
        ):
            return None

        # Get metadata
        name = self.definitions_graph.value(process_uri, META.name)
        version = self.definitions_graph.value(process_uri, META.version)
        status = self.definitions_graph.value(process_uri, META.status)
        description = self.definitions_graph.value(process_uri, RDFS.comment)
        deployed_at = self.definitions_graph.value(process_uri, META.deployedAt)
        updated_at = self.definitions_graph.value(process_uri, META.updatedAt)

        # Count BPMN triples
        triples_count = len(list(self.definitions_graph.triples((None, None, None))))

        # Use deployed_at for both created_at and updated_at if updated_at is None
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

    def list_processes(
        self, status: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> Dict[str, Any]:
        """List all process definitions"""
        processes = []

        for process_uri in self.definitions_graph.subjects(
            RDF.type, PROC.ProcessDefinition
        ):
            process_id = str(process_uri).split("/")[-1]
            process_data = self.get_process(process_id)

            if process_data:
                # Filter by status if specified
                if status and process_data["status"] != status:
                    continue
                processes.append(process_data)

        # Pagination
        total = len(processes)
        start = (page - 1) * page_size
        end = start + page_size
        processes = processes[start:end]

        return {
            "processes": processes,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_process(
        self,
        process_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a process definition"""
        process_uri = PROC[process_id]

        if (
            not (process_uri, RDF.type, PROC.ProcessDefinition)
            in self.definitions_graph
        ):
            return None

        if name:
            self.definitions_graph.set((process_uri, META.name, Literal(name)))
        if description is not None:
            self.definitions_graph.set(
                (process_uri, RDFS.comment, Literal(description))
            )
        if status:
            self.definitions_graph.set((process_uri, META.status, Literal(status)))

        self.definitions_graph.set(
            (process_uri, META.updatedAt, Literal(datetime.now().isoformat()))
        )

        self._save_graph(self.definitions_graph, "definitions.ttl")

        return self.get_process(process_id)

    def delete_process(self, process_id: str) -> bool:
        """Delete a process definition"""
        process_uri = PROC[process_id]

        # Remove all triples about this process
        triples_to_remove = list(
            self.definitions_graph.triples((process_uri, None, None))
        )
        triples_to_remove += list(
            self.definitions_graph.triples((None, None, process_uri))
        )

        for s, p, o in triples_to_remove:
            self.definitions_graph.remove((s, p, o))

        self._save_graph(self.definitions_graph, "definitions.ttl")

        logger.info(f"Deleted process: {process_id}")
        return True

    def get_process_graph(self, process_id: str) -> Optional[Graph]:
        """Get the RDF graph for a specific process"""
        process_uri = PROC[process_id]

        if (
            not (process_uri, RDF.type, PROC.ProcessDefinition)
            in self.definitions_graph
        ):
            return None

        # Extract process-specific triples
        process_graph = Graph()
        for s, p, o in self.definitions_graph:
            # Include if subject or object is part of this process
            if str(s).startswith(str(process_uri)) or str(s).startswith(
                "http://example.org/bpmn/"
            ):
                process_graph.add((s, p, o))
            if str(o).startswith(str(process_uri)) or str(o).startswith(
                "http://example.org/bpmn/"
            ):
                process_graph.add((s, p, o))

        return process_graph

    # ==================== Process Instance Operations ====================

    def create_instance(
        self,
        process_id: str,
        variables: Optional[Dict[str, Any]] = None,
        start_event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and start a new process instance"""
        process_uri = PROC[process_id]

        if (
            not (process_uri, RDF.type, PROC.ProcessDefinition)
            in self.definitions_graph
        ):
            raise ValueError(f"Process {process_id} not found")

        instance_id = str(uuid.uuid4())
        instance_uri = INST[instance_id]

        # Create instance metadata
        self.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        self.instances_graph.add((instance_uri, INST.processDefinition, process_uri))
        self.instances_graph.add((instance_uri, INST.status, Literal("RUNNING")))
        self.instances_graph.add(
            (instance_uri, INST.createdAt, Literal(datetime.now().isoformat()))
        )

        # Add variables
        if variables:
            for name, value in variables.items():
                var_uri = VAR[f"{instance_id}_{name}"]
                self.instances_graph.add((instance_uri, INST.hasVariable, var_uri))
                self.instances_graph.add((var_uri, VAR.name, Literal(name)))
                self.instances_graph.add((var_uri, VAR.value, Literal(str(value))))

        # Create token at start event
        token_uri = INST[f"token_{instance_id}"]
        self.instances_graph.add((token_uri, RDF.type, INST.Token))
        self.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        self.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        self.instances_graph.add((instance_uri, INST.hasToken, token_uri))

        # Find start event URI
        start_event_uri = None
        if start_event_id:
            start_event_uri = URIRef(f"http://example.org/bpmn/{start_event_id}")
        else:
            # Find first start event linked to this process definition
            elements_found = []
            for s, p, o in self.definitions_graph.triples(
                (process_uri, PROC.hasElement, None)
            ):
                elements_found.append(o)

            logger.debug(f"Found {len(elements_found)} elements linked to process")
            for elem in elements_found:
                logger.debug(f"  Checking element: {elem}")
                # Check if this element is a start event (case-insensitive check)
                for ss, pp, oo in self.definitions_graph.triples(
                    (elem, RDF.type, None)
                ):
                    logger.debug(f"    Type: {oo}")
                    if "startevent" in str(oo).lower():
                        start_event_uri = elem
                        logger.debug(f"    -> Found start event: {start_event_uri}")
                        break
                if start_event_uri:
                    break

        logger.debug(f"Setting token currentNode to: {start_event_uri}")
        if start_event_uri:
            self.instances_graph.add((token_uri, INST.currentNode, start_event_uri))

        # Log instance creation
        self._log_instance_event(instance_uri, "CREATED", "System")

        self._save_graph(self.instances_graph, "instances.ttl")

        logger.info(f"Created instance {instance_id} for process {process_id}")

        # Execute the instance
        self._execute_instance(instance_uri, instance_id)

        return {
            "id": instance_id,
            "process_id": process_id,
            "status": "RUNNING",
            "variables": variables or {},
        }

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get a process instance by ID"""
        instance_uri = INST[instance_id]

        if not (instance_uri, RDF.type, INST.ProcessInstance) in self.instances_graph:
            return None

        # Get instance data
        status = self.instances_graph.value(instance_uri, INST.status)
        created_at = self.instances_graph.value(instance_uri, INST.createdAt)
        updated_at = self.instances_graph.value(instance_uri, INST.updatedAt)

        process_def = self.instances_graph.value(instance_uri, INST.processDefinition)
        process_id = str(process_def).split("/")[-1] if process_def else None

        # Get variables
        variables = {}
        for var_uri in self.instances_graph.objects(instance_uri, INST.hasVariable):
            name = self.instances_graph.value(var_uri, VAR.name)
            value = self.instances_graph.value(var_uri, VAR.value)
            if name and value:
                variables[str(name)] = str(value)

        # Get current nodes from tokens
        current_nodes = []
        for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
            node = self.instances_graph.value(token_uri, INST.currentNode)
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

    def list_instances(
        self,
        process_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List process instances"""
        instances = []

        for instance_uri in self.instances_graph.subjects(
            RDF.type, INST.ProcessInstance
        ):
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

    def stop_instance(
        self, instance_id: str, reason: str = "User request"
    ) -> Dict[str, Any]:
        """Stop a running process instance"""
        instance_uri = INST[instance_id]

        if not (instance_uri, RDF.type, INST.ProcessInstance) in self.instances_graph:
            raise ValueError(f"Instance {instance_id} not found")

        # Update status
        self.instances_graph.set((instance_uri, INST.status, Literal("TERMINATED")))
        self.instances_graph.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        # Log termination
        self._log_instance_event(instance_uri, "TERMINATED", "System", reason)

        self._save_graph(self.instances_graph, "instances.ttl")

        logger.info(f"Stopped instance {instance_id}: {reason}")

        return self.get_instance(instance_id)

    # ==================== Loop-Scoped Variable Methods ====================

    def _get_loop_scoped_name(self, base_name: str, loop_idx: int) -> str:
        """Convert 'orderId' to 'orderId_loop0' for loop-scoped variables"""
        return f"{base_name}_loop{loop_idx}"

    def _parse_loop_scoped_name(self, scoped_name: str) -> tuple:
        """Parse 'orderId_loop0' into ('orderId', 0)"""
        if "_loop" in scoped_name:
            parts = scoped_name.rsplit("_loop", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return parts[0], int(parts[1])
        return scoped_name, None

    def _get_loop_index(self, token_uri: URIRef) -> Optional[int]:
        """Extract loop index from a token URI"""
        loop_idx = self.instances_graph.value(token_uri, INST.loopInstance)
        if loop_idx:
            try:
                return int(str(loop_idx))
            except ValueError:
                pass
        return None

    def get_instance_variables(
        self, instance_id: str, loop_idx: int = None, mi_info: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Get variables for a process instance, optionally scoped to a loop instance"""
        instance_uri = INST[instance_id]

        variables = {}
        for var_uri in self.instances_graph.objects(instance_uri, INST.hasVariable):
            name = self.instances_graph.value(var_uri, VAR.name)
            value = self.instances_graph.value(var_uri, VAR.value)
            if name and value:
                name_str = str(name)
                value_str = str(value)

                if loop_idx is not None:
                    base_name, var_loop_idx = self._parse_loop_scoped_name(name_str)
                    if var_loop_idx == loop_idx:
                        variables[base_name] = value_str
                    elif var_loop_idx is None:
                        variables[name_str] = value_str
                else:
                    variables[name_str] = value_str

        if loop_idx is not None and mi_info and mi_info.get("data_input"):
            data_input = mi_info["data_input"]
            data_output = mi_info.get("data_output", "item")

            # First try loop-scoped variable
            input_var_name_scoped = f"{data_input}_loop{loop_idx}"
            input_value = None

            for var_uri in self.instances_graph.objects(instance_uri, INST.hasVariable):
                name = self.instances_graph.value(var_uri, VAR.name)
                if name and str(name) == input_var_name_scoped:
                    value = self.instances_graph.value(var_uri, VAR.value)
                    if value:
                        input_value = str(value)
                    break

            # If not found, try non-scoped variable
            if input_value is None:
                for var_uri in self.instances_graph.objects(
                    instance_uri, INST.hasVariable
                ):
                    name = self.instances_graph.value(var_uri, VAR.name)
                    if name and str(name) == data_input:
                        value = self.instances_graph.value(var_uri, VAR.value)
                        if value:
                            input_value = str(value)
                        break

            if input_value:
                items = input_value.split(",")
                if loop_idx < len(items):
                    variables[data_output] = items[loop_idx].strip()

        return variables

    def set_instance_variable(
        self, instance_id: str, name: str, value: Any, loop_idx: int = None
    ) -> bool:
        """Set a variable on a process instance, optionally scoped to a loop instance"""
        instance_uri = INST[instance_id]

        # Build the variable name (with loop scope if specified)
        if loop_idx is not None:
            var_name = self._get_loop_scoped_name(name, loop_idx)
        else:
            var_name = name

        # Find existing variable
        var_uri = None
        for v in self.instances_graph.objects(instance_uri, INST.hasVariable):
            if self.instances_graph.value(v, VAR.name) == Literal(var_name):
                var_uri = v
                break

        if var_uri:
            # Update existing variable
            self.instances_graph.set((var_uri, VAR.value, Literal(str(value))))
        else:
            # Create new variable
            var_uri = VAR[f"{instance_id}_{var_name}"]
            self.instances_graph.add((instance_uri, INST.hasVariable, var_uri))
            self.instances_graph.add((var_uri, VAR.name, Literal(var_name)))
            self.instances_graph.add((var_uri, VAR.value, Literal(str(value))))

        self._save_graph(self.instances_graph, "instances.ttl")

        return True

    # ==================== Audit Log Operations ====================

    def _log_instance_event(
        self, instance_uri: URIRef, event_type: str, user: str, details: str = ""
    ):
        """Log an event for an instance"""
        event_uri = LOG[f"event_{str(uuid.uuid4())}"]

        self.audit_graph.add((event_uri, RDF.type, LOG.Event))
        self.audit_graph.add((event_uri, LOG.instance, instance_uri))
        self.audit_graph.add((event_uri, LOG.eventType, Literal(event_type)))
        self.audit_graph.add((event_uri, LOG.user, Literal(user)))
        self.audit_graph.add(
            (event_uri, LOG.timestamp, Literal(datetime.now().isoformat()))
        )
        if details:
            self.audit_graph.add((event_uri, LOG.details, Literal(details)))

        self._save_graph(self.audit_graph, "audit.ttl")

    def get_instance_audit_log(self, instance_id: str) -> List[Dict[str, Any]]:
        """Get the audit log for an instance"""
        instance_uri = INST[instance_id]
        events = []

        for event_uri in self.audit_graph.subjects(LOG.instance, instance_uri):
            event_type = self.audit_graph.value(event_uri, LOG.eventType)
            user = self.audit_graph.value(event_uri, LOG.user)
            timestamp = self.audit_graph.value(event_uri, LOG.timestamp)
            details = self.audit_graph.value(event_uri, LOG.details)

            events.append(
                {
                    "type": str(event_type) if event_type else "",
                    "user": str(user) if user else "",
                    "timestamp": str(timestamp) if timestamp else "",
                    "details": str(details) if details else "",
                }
            )

        return sorted(events, key=lambda x: x["timestamp"])

    # ==================== Instance Execution ====================

    def _execute_instance(self, instance_uri: URIRef, instance_id: str):
        """Execute a process instance by processing all tokens"""
        while True:
            active_tokens = []
            for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
                token_status = self.instances_graph.value(token_uri, INST.status)
                if token_status and str(token_status) == "ACTIVE":
                    active_tokens.append(token_uri)

            if not active_tokens:
                break

            merged_gateways = set()
            for token_uri in active_tokens:
                self._execute_token(
                    instance_uri, token_uri, instance_id, merged_gateways
                )

            self._save_graph(self.instances_graph, "instances.ttl")

        if self._is_instance_completed(instance_uri):
            self.instances_graph.set((instance_uri, INST.status, Literal("COMPLETED")))
            self.instances_graph.set(
                (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
            )
            self._log_instance_event(instance_uri, "COMPLETED", "System")
            self._save_graph(self.instances_graph, "instances.ttl")

    def _execute_token(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        instance_id: str,
        merged_gateways: set = None,
    ):
        """Execute a single token through the process"""
        if merged_gateways is None:
            merged_gateways = set()

        current_node = self.instances_graph.value(token_uri, INST.currentNode)
        if not current_node:
            # Token has no current node - mark as error
            self.instances_graph.set((token_uri, INST.status, Literal("ERROR")))
            self._log_instance_event(
                instance_uri,
                "TOKEN_ERROR",
                "System",
                f"Token has no current node",
            )
            return

        # Skip tokens that are no longer active (may have been consumed by merge in same iteration)
        token_status = self.instances_graph.value(token_uri, INST.status)
        if token_status and str(token_status) in ["CONSUMED", "ERROR", "WAITING"]:
            return

        # Get node type - check all types to handle nodes with multiple types
        node_type = None
        node_types = []
        for s, p, o in self.definitions_graph.triples((current_node, RDF.type, None)):
            node_types.append(o)

        logger.debug(f"Executing token at {current_node}, types: {node_types}")

        if BPMN.StartEvent in node_types or BPMN.startEvent in node_types:
            self._log_instance_event(instance_uri, "START", "System", str(current_node))
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)

        elif BPMN.EndEvent in node_types or BPMN.endEvent in node_types:
            is_message_end_event = False
            message_name = None
            for s, p, o in self.definitions_graph.triples(
                (current_node, RDF.type, None)
            ):
                if "MessageEndEvent" in str(o):
                    is_message_end_event = True
                    message_name = self.definitions_graph.value(
                        current_node, BPMN.messageRef
                    )
                    if not message_name:
                        message_name = self.definitions_graph.value(
                            current_node,
                            URIRef("http://camunda.org/schema/1.0/bpmn#message"),
                        )
                    if message_name:
                        message_name = str(message_name)
                    break

            if is_message_end_event and message_name:
                self._log_instance_event(
                    instance_uri,
                    "MESSAGE_END_EVENT",
                    "System",
                    f"Message end event triggered: {message_name}",
                )
                logger.info(
                    f"Message end event at {current_node}, triggering message: {message_name}"
                )
                self._trigger_message_end_event(instance_uri, message_name)

            sub_status = self.instances_graph.value(token_uri, INST.subprocessStatus)
            if sub_status and str(sub_status) == "inside":
                # We're inside an expanded subprocess - delegate to subprocess handler
                # Find the parent subprocess of this end event
                for parent_uri in self.definitions_graph.objects(
                    current_node, BPMN.hasParent
                ):
                    # Check if parent is an expanded subprocess
                    for ss, pp, oo in self.definitions_graph.triples(
                        (parent_uri, RDF.type, None)
                    ):
                        if "expandedsubprocess" in str(oo).lower():
                            # Call the expanded subprocess handler to handle completion
                            self._execute_expanded_subprocess(
                                instance_uri, token_uri, parent_uri, instance_id
                            )
                            return
            # Not inside a subprocess or no parent subprocess - regular end event
            self._log_instance_event(instance_uri, "END", "System", str(current_node))
            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        elif BPMN.ServiceTask in node_types or BPMN.serviceTask in node_types:
            self._execute_service_task(
                instance_uri, token_uri, current_node, instance_id
            )

        elif BPMN.ScriptTask in node_types or "scripttask" in str(node_types).lower():
            self._execute_script_task(
                instance_uri, token_uri, current_node, instance_id
            )

        elif BPMN.UserTask in node_types or BPMN.userTask in node_types:
            mi_info = self._is_multi_instance(current_node)

            if mi_info["is_multi_instance"]:
                loop_instance = self.instances_graph.value(token_uri, INST.loopInstance)
                if loop_instance is None:
                    self._create_multi_instance_tokens(
                        instance_uri, token_uri, current_node, instance_id, mi_info
                    )
                    self._log_instance_event(
                        instance_uri,
                        "MULTI_INSTANCE_STARTED",
                        "System",
                        f"{str(current_node)} - {'parallel' if mi_info['is_parallel'] else 'sequential'}",
                    )
                    return
                else:
                    completed = self._complete_loop_instance(
                        instance_uri, token_uri, current_node, instance_id, mi_info
                    )
                    if completed:
                        return

            task_name = "User Task"
            name_elem = self.definitions_graph.value(current_node, RDFS.label)
            if name_elem:
                task_name = str(name_elem)

            assignee = None
            assignee_elem = self.definitions_graph.value(current_node, BPMN.assignee)
            if assignee_elem:
                assignee = str(assignee_elem)

            candidate_users = []
            for u in self.definitions_graph.objects(current_node, BPMN.candidateUsers):
                candidate_users.append(str(u))

            candidate_groups = []
            for g in self.definitions_graph.objects(current_node, BPMN.candidateGroups):
                candidate_groups.append(str(g))

            task = self.create_task(
                instance_id=instance_id,
                node_uri=str(current_node),
                name=task_name,
                assignee=assignee,
                candidate_users=candidate_users if candidate_users else None,
                candidate_groups=candidate_groups if candidate_groups else None,
            )

            # Execute "create" task listeners
            self._execute_task_listeners(
                instance_uri, token_uri, current_node, instance_id, "create"
            )

            self._log_instance_event(
                instance_uri,
                "USER_TASK",
                "System",
                f"{str(current_node)} (task: {task['id']})",
            )
            self.instances_graph.set((token_uri, INST.status, Literal("WAITING")))

        elif BPMN.ReceiveTask in node_types or BPMN.receiveTask in node_types:
            self._execute_receive_task(
                instance_uri, token_uri, current_node, instance_id
            )

        elif BPMN.EventBasedGateway in node_types:
            self._execute_event_based_gateway(
                instance_uri, token_uri, current_node, instance_id
            )

        elif (
            BPMN.ExclusiveGateway in node_types
            or "exclusivegateway" in str(node_types).lower()
        ):
            # Evaluate conditions to choose the correct outgoing flow
            next_node = self._evaluate_gateway_conditions(instance_uri, current_node)
            if next_node:
                # Move token to the selected next node
                self.instances_graph.set((token_uri, INST.currentNode, next_node))
            else:
                # No valid path found - consume token with error
                logger.error(f"No valid path found at exclusive gateway {current_node}")
                self.instances_graph.set((token_uri, INST.status, Literal("ERROR")))
                self._log_instance_event(
                    instance_uri,
                    "GATEWAY_ERROR",
                    "System",
                    f"No valid path at {str(current_node)}",
                )

        elif BPMN.ParallelGateway in node_types:
            next_nodes = []
            for s, p, o in self.definitions_graph.triples(
                (current_node, BPMN.outgoing, None)
            ):
                for ss, pp, target in self.definitions_graph.triples(
                    (o, BPMN.targetRef, None)
                ):
                    next_nodes.append(target)

            if len(next_nodes) > 1:
                self.instances_graph.set((token_uri, INST.currentNode, next_nodes[0]))
                for additional_target in next_nodes[1:]:
                    new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                    self.instances_graph.add((new_token_uri, RDF.type, INST.Token))
                    self.instances_graph.add(
                        (new_token_uri, INST.belongsTo, instance_uri)
                    )
                    self.instances_graph.add(
                        (new_token_uri, INST.status, Literal("ACTIVE"))
                    )
                    self.instances_graph.add(
                        (new_token_uri, INST.currentNode, additional_target)
                    )
                    self.instances_graph.add(
                        (instance_uri, INST.hasToken, new_token_uri)
                    )

                self._log_instance_event(
                    instance_uri,
                    "PARALLEL_GATEWAY_FORK",
                    "System",
                    f"Parallel gateway {str(current_node)} forked to {len(next_nodes)} paths",
                )

                logger.info(
                    f"Parallel gateway {current_node} created {len(next_nodes)} parallel paths"
                )
            elif len(next_nodes) == 1:
                self.instances_graph.set((token_uri, INST.currentNode, next_nodes[0]))

        elif (
            BPMN.InclusiveGateway in node_types
            or "inclusivegateway" in str(node_types).lower()
        ):
            inclusive_next_nodes = []
            for s, p, o in self.definitions_graph.triples(
                (current_node, BPMN.outgoing, None)
            ):
                for ss, pp, target in self.definitions_graph.triples(
                    (o, BPMN.targetRef, None)
                ):
                    inclusive_next_nodes.append((o, target))

            if len(inclusive_next_nodes) > 1:
                incoming_count = self._count_incoming_flows(current_node)
                if incoming_count > 1:
                    waiting_count = self._count_waiting_tokens_at_incoming(
                        instance_uri, current_node
                    )
                    if waiting_count >= incoming_count:
                        targets = [t for _, t in inclusive_next_nodes]
                        self._merge_inclusive_tokens(
                            instance_uri, current_node, instance_id, targets
                        )
                    else:
                        self.instances_graph.set(
                            (token_uri, INST.status, Literal("WAITING"))
                        )
                else:
                    true_targets = []
                    for flow_uri, target in inclusive_next_nodes:
                        condition_result = self._evaluate_condition_for_flow(
                            instance_uri, flow_uri
                        )
                        if condition_result:
                            true_targets.append(target)

                    if len(true_targets) > 1:
                        self.instances_graph.set(
                            (token_uri, INST.currentNode, true_targets[0])
                        )
                        for additional_target in true_targets[1:]:
                            new_token_uri = INST[
                                f"token_{instance_id}_{str(uuid.uuid4())[:8]}"
                            ]
                            self.instances_graph.add(
                                (new_token_uri, RDF.type, INST.Token)
                            )
                            self.instances_graph.add(
                                (new_token_uri, INST.belongsTo, instance_uri)
                            )
                            self.instances_graph.add(
                                (new_token_uri, INST.status, Literal("ACTIVE"))
                            )
                            self.instances_graph.add(
                                (new_token_uri, INST.currentNode, additional_target)
                            )
                            self.instances_graph.add(
                                (instance_uri, INST.hasToken, new_token_uri)
                            )

                        self._log_instance_event(
                            instance_uri,
                            "INCLUSIVE_GATEWAY_FORK",
                            "System",
                            f"Inclusive gateway {str(current_node)} forked to {len(true_targets)} paths",
                        )

                        logger.info(
                            f"Inclusive gateway {current_node} created {len(true_targets)} parallel paths"
                        )
                    elif len(true_targets) == 1:
                        self.instances_graph.set(
                            (token_uri, INST.currentNode, true_targets[0])
                        )
                    else:
                        logger.warning(
                            f"No outgoing paths taken from inclusive gateway {current_node}"
                        )
                        self.instances_graph.set(
                            (token_uri, INST.status, Literal("CONSUMED"))
                        )
            elif len(inclusive_next_nodes) == 1:
                incoming_count = self._count_incoming_flows(current_node)
                if incoming_count > 1:
                    # Skip if this gateway was already merged in this iteration
                    if current_node in merged_gateways:
                        self.instances_graph.set(
                            (token_uri, INST.status, Literal("CONSUMED"))
                        )
                        return

                    waiting_count = self._count_waiting_tokens_at_incoming(
                        instance_uri, current_node
                    )
                    if waiting_count >= incoming_count:
                        merged_gateways.add(current_node)
                        self._merge_inclusive_tokens(
                            instance_uri,
                            current_node,
                            instance_id,
                            [inclusive_next_nodes[0][1]],
                        )
                    else:
                        self.instances_graph.set(
                            (token_uri, INST.status, Literal("WAITING"))
                        )
                else:
                    self.instances_graph.set(
                        (token_uri, INST.currentNode, inclusive_next_nodes[0][1])
                    )
            else:
                self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        elif any("expandedsubprocess" in str(t).lower() for t in node_types):
            self._execute_expanded_subprocess(
                instance_uri, token_uri, current_node, instance_id
            )

        elif any("callactivity" in str(t).lower() for t in node_types):
            self._execute_call_activity(
                instance_uri, token_uri, current_node, instance_id
            )

        elif any("eventsubprocess" in str(t).lower() for t in node_types):
            self._execute_event_subprocess(
                instance_uri, token_uri, current_node, instance_id
            )

        elif any("intermediatecatchevent" in str(t).lower() for t in node_types):
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)

        elif (
            BPMN.cancelEndEvent in node_types
            or "cancelendevent" in str(node_types).lower()
        ):
            self._execute_cancel_end_event(
                instance_uri, token_uri, current_node, instance_id
            )

        elif (
            BPMN.compensationEndEvent in node_types
            or "compensationendevent" in str(node_types).lower()
        ):
            self._execute_compensation_end_event(
                instance_uri, token_uri, current_node, instance_id
            )

        elif (
            BPMN.errorEndEvent in node_types
            or "errorendevent" in str(node_types).lower()
        ):
            self._execute_error_end_event(
                instance_uri, token_uri, current_node, instance_id
            )

        elif (
            BPMN.terminateEndEvent in node_types
            or "terminateendevent" in str(node_types).lower()
        ):
            self._execute_terminate_end_event(
                instance_uri, token_uri, current_node, instance_id
            )

        elif any("boundaryevent" in str(t).lower() for t in node_types):
            self._execute_boundary_event(
                instance_uri, token_uri, current_node, instance_id
            )

        else:
            # For other node types, just move to next node
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)

        self._save_graph(self.instances_graph, "instances.ttl")

    def _execute_service_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ):
        """Execute a service task and move token to next node"""
        # Execute "start" execution listeners
        self._execute_execution_listeners(
            instance_uri, token_uri, node_uri, instance_id, "start"
        )

        mi_info = self._is_multi_instance(node_uri)

        if mi_info["is_multi_instance"]:
            loop_instance = self.instances_graph.value(token_uri, INST.loopInstance)

            if loop_instance is None:
                count = 3
                if mi_info["loop_cardinality"]:
                    try:
                        count = int(mi_info["loop_cardinality"])
                    except ValueError:
                        pass

                logger.info(
                    f"Creating {count} parallel tokens for multi-instance activity {node_uri}"
                )

                for i in range(count):
                    loop_token_uri = INST[
                        f"token_{instance_id}_{str(uuid.uuid4())[:8]}"
                    ]
                    self.instances_graph.add((loop_token_uri, RDF.type, INST.Token))
                    self.instances_graph.add(
                        (loop_token_uri, INST.belongsTo, instance_uri)
                    )
                    self.instances_graph.add(
                        (loop_token_uri, INST.status, Literal("ACTIVE"))
                    )
                    self.instances_graph.add(
                        (loop_token_uri, INST.currentNode, node_uri)
                    )
                    self.instances_graph.add(
                        (loop_token_uri, INST.loopInstance, Literal(str(i)))
                    )
                    self.instances_graph.add(
                        (instance_uri, INST.hasToken, loop_token_uri)
                    )

                    self._execute_service_task_handler(
                        instance_uri, loop_token_uri, node_uri, instance_id
                    )
                    self.instances_graph.set(
                        (loop_token_uri, INST.status, Literal("CONSUMED"))
                    )

                self._log_instance_event(
                    instance_uri,
                    "MULTI_INSTANCE_STARTED",
                    "System",
                    f"{str(node_uri)} - parallel ({count} instances)",
                )

                self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

                self._advance_multi_instance(instance_uri, node_uri, instance_id)
                return

            self._complete_loop_instance(
                instance_uri, token_uri, node_uri, instance_id, mi_info
            )
            return

        self._execute_service_task_handler(
            instance_uri, token_uri, node_uri, instance_id
        )

        # Execute "end" execution listeners
        self._execute_execution_listeners(
            instance_uri, token_uri, node_uri, instance_id, "end"
        )

        self._move_token_to_next_node(instance_uri, token_uri, instance_id)

    def _execute_script_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ):
        """Execute a script task if script execution is enabled, otherwise log and skip"""
        script_format = None
        script_code = None

        for s, p, o in self.definitions_graph.triples(
            (node_uri, BPMN.scriptFormat, None)
        ):
            script_format = str(o)
            break

        for s, p, o in self.definitions_graph.triples((node_uri, BPMN.script, None)):
            script_code = str(o)
            break

        node_id = str(node_uri).split("/")[-1]

        if not script_code:
            logger.warning(
                f"ScriptTask {node_id} has no script content - skipping execution"
            )
            self._log_instance_event(
                instance_uri,
                "SCRIPT_TASK_SKIPPED",
                "System",
                f"ScriptTask {node_id} - no script content",
            )
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)
            return

        if not self.script_tasks_enabled:
            logger.info(
                f"ScriptTask {node_id} execution disabled by configuration - skipping"
            )
            self._log_instance_event(
                instance_uri,
                "SCRIPT_TASK_DISABLED",
                "System",
                f"ScriptTask {node_id} - script execution disabled",
            )
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)
            return

        logger.info(
            f"Executing ScriptTask {node_id} (format: {script_format or 'python'})"
        )
        self._log_instance_event(
            instance_uri,
            "SCRIPT_TASK_STARTED",
            "System",
            f"ScriptTask {node_id} started",
        )

        try:
            self._run_script(
                instance_uri, node_uri, instance_id, script_code, script_format
            )

            logger.info(f"ScriptTask {node_id} completed successfully")
            self._log_instance_event(
                instance_uri,
                "SCRIPT_TASK_COMPLETED",
                "System",
                f"ScriptTask {node_id} completed",
            )
        except Exception as e:
            logger.error(f"ScriptTask {node_id} failed: {e}")
            self._log_instance_event(
                instance_uri,
                "SCRIPT_TASK_ERROR",
                "System",
                f"ScriptTask {node_id} failed: {str(e)}",
            )
            self.instances_graph.set((token_uri, INST.status, Literal("ERROR")))
            self._save_graph(self.instances_graph, "instances.ttl")
            return

        self._move_token_to_next_node(instance_uri, token_uri, instance_id)

    def _run_script(
        self,
        instance_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        script_code: str,
        script_format: str = None,
    ):
        """Execute a Python script with access to process variables"""
        variables = self.get_instance_variables(instance_id)

        local_vars = {"variables": dict(variables)}

        exec(script_code, {"print": print, "datetime": datetime}, local_vars)

        updated_vars = {
            k: v
            for k, v in local_vars.items()
            if k != "variables" and not k.startswith("_")
        }

        for name, value in updated_vars.items():
            self.set_instance_variable(instance_id, name, value)

    def _execute_execution_listeners(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        event: str,
    ):
        """Execute all execution listeners for a specific event"""
        for listener_uri in self.definitions_graph.subjects(
            BPMN.listenerElement, node_uri
        ):
            listener_type = self.definitions_graph.value(listener_uri, RDF.type)
            if listener_type and "ExecutionListener" not in str(listener_type):
                continue

            listener_event = self.definitions_graph.value(
                listener_uri, BPMN.listenerEvent
            )
            if listener_event and str(listener_event) != event:
                continue

            expression = self.definitions_graph.value(
                listener_uri, BPMN.listenerExpression
            )
            if expression and expression in self.topic_handlers:
                self._execute_listener(
                    instance_uri,
                    node_uri,
                    instance_id,
                    str(expression),
                    "execution",
                    event,
                )

    def _execute_task_listeners(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        event: str,
    ):
        """Execute all task listeners for a specific event"""
        for listener_uri in self.definitions_graph.subjects(
            BPMN.listenerElement, node_uri
        ):
            listener_type = self.definitions_graph.value(listener_uri, RDF.type)
            if listener_type and "TaskListener" not in str(listener_type):
                continue

            listener_event = self.definitions_graph.value(
                listener_uri, BPMN.listenerEvent
            )
            if listener_event and str(listener_event) != event:
                continue

            expression = self.definitions_graph.value(
                listener_uri, BPMN.listenerExpression
            )
            if expression and expression in self.topic_handlers:
                self._execute_listener(
                    instance_uri, node_uri, instance_id, str(expression), "task", event
                )

    def _execute_listener(
        self,
        instance_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        expression: str,
        listener_type: str,
        event: str,
    ):
        """Execute a single listener via its topic handler"""
        handler = self.topic_handlers.get(expression)
        if not handler:
            return

        node_id = str(node_uri).split("/")[-1]

        logger.info(
            f"Executing {listener_type} listener '{expression}' "
            f"(event: {event}) on node {node_id}"
        )

        try:
            from src.core.rdfengine import ProcessContext

            context = ProcessContext(self, instance_uri)

            if callable(handler):
                if hasattr(handler, "__self__"):
                    method = getattr(handler.__self__, handler.__name__)
                    method(context)
                else:
                    handler(context)
            elif isinstance(handler, dict):
                handler_type = handler.get("type", "function")
                if handler_type == "http":
                    self._execute_http_handler(handler, context)

            self._log_instance_event(
                instance_uri,
                "LISTENER_EXECUTED",
                "System",
                f"{listener_type.capitalize()} listener '{expression}' (event: {event})",
            )
        except Exception as e:
            logger.error(f"Listener '{expression}' failed: {e}")
            self._log_instance_event(
                instance_uri,
                "LISTENER_ERROR",
                "System",
                f"{listener_type.capitalize()} listener '{expression}' failed: {str(e)}",
            )

    def _execute_service_task_handler(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ):
        """Execute the actual service task handler"""
        topic = None
        for s, p, o in self.definitions_graph.triples((node_uri, BPMN.topic, None)):
            topic = str(o)
            break
        if not topic:
            for s, p, o in self.definitions_graph.triples(
                (node_uri, URIRef("http://camunda.org/schema/1.0/bpmn#topic"), None)
            ):
                topic = str(o)
                break

        if not topic:
            self._log_instance_event(
                instance_uri,
                "SERVICE_TASK",
                "System",
                f"{str(node_uri)} (no topic configured)",
            )
            return

        # Get loop index for multi-instance activities
        loop_idx = self._get_loop_index(token_uri)

        # Get multi-instance info for dataInput/dataOutput handling
        mi_info = self._is_multi_instance(node_uri)

        # Get loop-scoped variables
        variables = self.get_instance_variables(instance_id, loop_idx, mi_info)

        try:
            updated_variables = self.execute_service_task(
                instance_id, topic, variables, loop_idx
            )

            # Store loop-scoped results
            if updated_variables:
                for name, value in updated_variables.items():
                    self.set_instance_variable(instance_id, name, value, loop_idx)

            self._log_instance_event(
                instance_uri,
                "SERVICE_TASK",
                "System",
                f"{str(node_uri)} (topic: {topic})",
            )

        except ValueError as e:
            logger.warning(str(e))
            self._log_instance_event(
                instance_uri,
                "SERVICE_TASK_SKIPPED",
                "System",
                f"{str(node_uri)} (topic: {topic}) - no handler",
            )

        except Exception as e:
            logger.error(f"Service task failed: {e}")
            self.instances_graph.set((token_uri, INST.status, Literal("ERROR")))
            self._log_instance_event(
                instance_uri,
                "SERVICE_TASK_ERROR",
                "System",
                f"{str(node_uri)} (topic: {topic}): {str(e)}",
            )
            return

    def _execute_expanded_subprocess(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ):
        """Execute an expanded (embedded) subprocess"""
        mi_info = self._is_multi_instance(node_uri)

        if mi_info["is_multi_instance"]:
            loop_instance = self.instances_graph.value(token_uri, INST.loopInstance)

            if loop_instance is None:
                count = 3
                if mi_info["loop_cardinality"]:
                    try:
                        count = int(mi_info["loop_cardinality"])
                    except ValueError:
                        pass

                logger.info(
                    f"Creating {count} parallel tokens for multi-instance expanded subprocess {node_uri}"
                )

                for i in range(count):
                    loop_token_uri = INST[
                        f"token_{instance_id}_{str(uuid.uuid4())[:8]}"
                    ]
                    self.instances_graph.add((loop_token_uri, RDF.type, INST.Token))
                    self.instances_graph.add(
                        (loop_token_uri, INST.belongsTo, instance_uri)
                    )
                    self.instances_graph.add(
                        (loop_token_uri, INST.status, Literal("ACTIVE"))
                    )
                    self.instances_graph.add(
                        (loop_token_uri, INST.currentNode, node_uri)
                    )
                    self.instances_graph.add(
                        (loop_token_uri, INST.loopInstance, Literal(str(i)))
                    )
                    self.instances_graph.add(
                        (instance_uri, INST.hasToken, loop_token_uri)
                    )

                    self._execute_expanded_subprocess_handler(
                        instance_uri, loop_token_uri, node_uri, instance_id, i
                    )

                self._log_instance_event(
                    instance_uri,
                    "MULTI_INSTANCE_STARTED",
                    "System",
                    f"{str(node_uri)} - parallel ({count} instances)",
                )

                self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

                self._advance_multi_instance(instance_uri, node_uri, instance_id)
                return

            loop_idx = int(str(loop_instance)) if loop_instance else 0
            self._complete_subprocess_loop_instance(
                instance_uri, token_uri, node_uri, instance_id, mi_info, loop_idx
            )
            return

        self._execute_expanded_subprocess_handler(
            instance_uri, token_uri, node_uri, instance_id, None
        )

    def _execute_expanded_subprocess_handler(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        loop_idx: Optional[int] = None,
    ):
        """Handle the actual execution of an expanded subprocess (single instance)"""
        sub_status = self.instances_graph.value(token_uri, INST.subprocessStatus)

        if not sub_status:
            start_events = []
            for child_uri in self.definitions_graph.subjects(BPMN.hasParent, node_uri):
                for ss, pp, oo in self.definitions_graph.triples(
                    (child_uri, RDF.type, None)
                ):
                    if "startevent" in str(oo).lower():
                        start_events.append(child_uri)
                        break

            if not start_events:
                self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))
                return

            start_event = start_events[0]
            sub_instance_id = f"{instance_id}_sub_{str(uuid.uuid4())[:8]}"

            self.instances_graph.set((token_uri, INST.status, Literal("ACTIVE")))
            self.instances_graph.set((token_uri, INST.currentNode, start_event))
            self.instances_graph.set(
                (token_uri, INST.subprocessStatus, Literal("inside"))
            )
            self.instances_graph.set(
                (token_uri, INST.subprocessId, Literal(sub_instance_id))
            )

            loop_suffix = f"_loop{loop_idx}" if loop_idx is not None else ""
            self._log_instance_event(
                instance_uri,
                "SUBPROCESS_STARTED",
                "System",
                f"Entered expanded subprocess {str(node_uri)}{loop_suffix}",
            )

            logger.info(
                f"Entered expanded subprocess {node_uri}{loop_suffix}, starting at {start_event}"
            )

            self._execute_token(instance_uri, token_uri, instance_id)
        else:
            current_node = self.instances_graph.value(token_uri, INST.currentNode)

            node_type = None
            for s, p, o in self.definitions_graph.triples(
                (current_node, RDF.type, None)
            ):
                node_type = o
                break

            if str(node_type).endswith("EndEvent") or str(node_type).endswith(
                "endEvent"
            ):
                self.instances_graph.remove((token_uri, INST.subprocessStatus, None))
                self.instances_graph.remove((token_uri, INST.subprocessId, None))

                loop_suffix = f"_loop{loop_idx}" if loop_idx is not None else ""
                self._log_instance_event(
                    instance_uri,
                    "SUBPROCESS_COMPLETED",
                    "System",
                    f"Completed expanded subprocess {str(node_uri)}{loop_suffix}",
                )

                logger.info(f"Completed expanded subprocess {node_uri}{loop_suffix}")

                self.instances_graph.set((token_uri, INST.currentNode, node_uri))
                self._move_token_to_next_node(instance_uri, token_uri, instance_id)
                self._execute_token(instance_uri, token_uri, instance_id)
            else:
                self._execute_token(instance_uri, token_uri, instance_id)

    def _complete_subprocess_loop_instance(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        mi_info: Dict[str, Any],
        loop_idx: int,
    ):
        """Complete a single loop instance of a multi-instance subprocess"""
        loop_instance = self.instances_graph.value(token_uri, INST.loopInstance)
        current_loop = int(str(loop_instance)) if loop_instance else 0

        logger.info(
            f"Completed loop instance {current_loop} of expanded subprocess {node_uri}"
        )

        self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        self._advance_multi_instance(instance_uri, node_uri, instance_id)

    def _execute_call_activity(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ):
        """Execute a call activity (collapsed subprocess)"""
        # Get called element (subprocess definition)
        called_element = self.definitions_graph.value(node_uri, BPMN.calledElement)

        if not called_element:
            logger.warning(f"Call activity {node_uri} has no calledElement")
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)
            return

        called_element_str = str(called_element)
        logger.info(f"Call activity {node_uri} calling subprocess {called_element_str}")

        # Create a new instance of the called subprocess
        # For now, we execute inline (synchronous)
        # Find start events in called subprocess (elements with hasParent = called_element)
        start_events = []
        for child_uri in self.definitions_graph.subjects(
            BPMN.hasParent, called_element
        ):
            for ss, pp, oo in self.definitions_graph.triples(
                (child_uri, RDF.type, None)
            ):
                if str(oo).endswith("StartEvent") or str(oo).endswith("startEvent"):
                    start_events.append(child_uri)
                    break

        if not start_events:
            logger.warning(f"Called subprocess {called_element} has no start events")
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)
            return

        # Execute the called subprocess inline
        self._log_instance_event(
            instance_uri,
            "CALL_ACTIVITY_STARTED",
            "System",
            f"Started call to {called_element_str}",
        )

        # Create token for the called subprocess
        sub_instance_id = f"{instance_id}_call_{str(uuid.uuid4())[:8]}"
        sub_token_uri = INST[f"token_{sub_instance_id}"]

        self.instances_graph.add((sub_token_uri, RDF.type, INST.Token))
        self.instances_graph.add((sub_token_uri, INST.belongsTo, instance_uri))
        self.instances_graph.add((sub_token_uri, INST.status, Literal("ACTIVE")))
        self.instances_graph.add((sub_token_uri, INST.currentNode, start_events[0]))
        self.instances_graph.add(
            (sub_token_uri, INST.calledFrom, Literal(called_element_str))
        )
        self.instances_graph.add((instance_uri, INST.hasToken, sub_token_uri))

        # Execute tokens starting from start event
        # Continue execution until the call token is completed
        while True:
            token_status = self.instances_graph.value(sub_token_uri, INST.status)
            if not token_status or str(token_status) != "ACTIVE":
                break
            self._execute_token(instance_uri, sub_token_uri, sub_instance_id)

        # Clean up the call token
        self.instances_graph.set((sub_token_uri, INST.status, Literal("CONSUMED")))

        self._log_instance_event(
            instance_uri,
            "CALL_ACTIVITY_COMPLETED",
            "System",
            f"Completed call to {called_element_str}",
        )

        # Move to next node in parent process
        self._move_token_to_next_node(instance_uri, token_uri, instance_id)

    def _execute_event_subprocess(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ):
        """Execute an event subprocess (triggered by events)"""
        # Event subprocesses are started by events, not by regular token flow
        # This method handles when an event triggers the subprocess
        logger.info(f"Event subprocess {node_uri} triggered")

        # Find start events in event subprocess
        start_events = []
        for s, p, o in self.definitions_graph.triples(
            (node_uri, BPMN.hasFlowNode, None)
        ):
            for ss, pp, oo in self.definitions_graph.triples((o, RDF.type, None)):
                # Look for event-start events (message, timer, error, etc.)
                # Simplified: just find all start events
                if str(oo).endswith("StartEvent") or str(oo).endswith("startEvent"):
                    start_events.append(o)
                    break

        if not start_events:
            logger.warning(f"Event subprocess {node_uri} has no start events")
            return

        # Create token in event subprocess
        sub_instance_id = f"{instance_id}_event_{str(uuid.uuid4())[:8]}"
        sub_token_uri = INST[f"token_{sub_instance_id}"]

        self.instances_graph.add((sub_token_uri, RDF.type, INST.Token))
        self.instances_graph.add((sub_token_uri, INST.belongsTo, instance_uri))
        self.instances_graph.add((sub_token_uri, INST.status, Literal("ACTIVE")))
        self.instances_graph.add((sub_token_uri, INST.currentNode, start_events[0]))
        self.instances_graph.add(
            (sub_token_uri, INST.eventSubprocess, Literal(str(node_uri)))
        )
        self.instances_graph.add((instance_uri, INST.hasToken, sub_token_uri))

        self._log_instance_event(
            instance_uri,
            "EVENT_SUBPROCESS_STARTED",
            "System",
            f"Event subprocess {str(node_uri)} triggered",
        )

        # Execute the event subprocess
        self._execute_token(instance_uri, sub_token_uri, sub_instance_id)

    def _evaluate_gateway_conditions(
        self, instance_uri: URIRef, gateway_uri: URIRef
    ) -> Optional[URIRef]:
        """Evaluate conditions on outgoing flows from a gateway and return the target to proceed to

        For exclusive gateways:
        - Find all outgoing sequence flows (flows with sourceRef = gateway)
        - For each flow, check if it has a bpmn:conditionExpression
        - Evaluate the condition by checking instance variables
        - Return first target where condition evaluates to True
        - If no conditions, return first outgoing flow (default behavior)
        - If no conditions match and no default flow, return None

        Args:
            instance_uri: URI of the process instance
            gateway_uri: URI of the gateway node

        Returns:
            URIRef of the next node, or None if no valid path found
        """
        # Find all outgoing flows from gateway (flows where gateway is the source)
        outgoing_flows = []
        for flow_uri in self.definitions_graph.subjects(BPMN.sourceRef, gateway_uri):
            target_ref = self.definitions_graph.value(flow_uri, BPMN.targetRef)
            if target_ref:
                outgoing_flows.append((flow_uri, target_ref))

        if not outgoing_flows:
            logger.warning(f"Gateway {gateway_uri} has no outgoing flows")
            return None

        # Get default flow if exists (for exclusive gateway)
        default_flow = self.definitions_graph.value(gateway_uri, BPMN.default)
        if not default_flow:
            # Also check camunda:default
            default_flow = self.definitions_graph.value(
                gateway_uri, URIRef("http://camunda.org/schema/1.0/bpmn#default")
            )

        # Get instance variables for evaluation
        instance_vars = {}
        for var_uri in self.instances_graph.objects(instance_uri, INST.hasVariable):
            var_name = self.instances_graph.value(var_uri, VAR.name)
            var_value = self.instances_graph.value(var_uri, VAR.value)
            if var_name and var_value:
                instance_vars[str(var_name)] = str(var_value)

        # Check each flow for conditions
        for flow_uri, target_uri in outgoing_flows:
            # Skip default flow - it's only used if no other conditions match
            if default_flow and flow_uri == default_flow:
                continue

            # Get condition from conditionBody (original expression)
            condition_body = self.definitions_graph.value(flow_uri, BPMN.conditionBody)

            if condition_body:
                try:
                    # Parse the condition expression
                    condition_str = str(condition_body)

                    # Parse simple conditions: ${var op value} or just var op value
                    match = re.search(
                        r"\$\{(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|>=|<|!=|=)\s*(.+)\}",
                        condition_str,
                    )

                    if not match:
                        # Try without ${}
                        match = re.search(
                            r"(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|>=|<|!=|=)\s*(.+)",
                            condition_str,
                        )

                    if match:
                        var_name = match.group(1)
                        operator = match.group(2)
                        expected_value = match.group(3).strip()

                        # Strip quotes from expected value if present
                        if (
                            expected_value.startswith("'")
                            and expected_value.endswith("'")
                        ) or (
                            expected_value.startswith('"')
                            and expected_value.endswith('"')
                        ):
                            expected_value = expected_value[1:-1]

                        # Get actual value from instance
                        actual_value = instance_vars.get(var_name)

                        if actual_value is not None:
                            # Compare values
                            result = self._compare_values(
                                actual_value, expected_value, operator
                            )

                            if result:
                                logger.info(
                                    f"Condition matched on flow {flow_uri}, proceeding to {target_uri}"
                                )
                                return target_uri

                except Exception as e:
                    logger.warning(
                        f"Failed to evaluate condition on flow {flow_uri}: {e}"
                    )
                    continue

        # No conditions matched - check if there's a default flow
        if default_flow:
            for flow_uri, target_uri in outgoing_flows:
                if flow_uri == default_flow:
                    logger.info(f"Using default flow {flow_uri}")
                    return target_uri

        # If only one outgoing flow with no conditions, use it
        if len(outgoing_flows) == 1:
            logger.info(
                f"No conditions on single outgoing flow, proceeding to {outgoing_flows[0][1]}"
            )
            return outgoing_flows[0][1]

        # No valid path found
        logger.warning(f"No valid path found at exclusive gateway {gateway_uri}")
        return None

    def _evaluate_condition_for_flow(
        self, instance_uri: URIRef, flow_uri: URIRef
    ) -> bool:
        """Evaluate the condition on a single flow and return True/False.

        Args:
            instance_uri: URI of the process instance
            flow_uri: URI of the sequence flow to check

        Returns:
            True if condition passes or no condition, False otherwise
        """
        try:
            condition_body = self.definitions_graph.value(flow_uri, BPMN.conditionBody)

            if not condition_body:
                return True

            condition_str = str(condition_body)

            match = re.search(
                r"\$\{(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|>=|<|!=|=)\s*(.+)\}",
                condition_str,
            )

            if not match:
                match = re.search(
                    r"(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|>=|<|!=|=)\s*(.+)",
                    condition_str,
                )

            if not match:
                return True

            var_name = match.group(1)
            operator = match.group(2)
            expected_value = match.group(3).strip()

            if (expected_value.startswith("'") and expected_value.endswith("'")) or (
                expected_value.startswith('"') and expected_value.endswith('"')
            ):
                expected_value = expected_value[1:-1]

            instance_vars = {}
            for var_uri in self.instances_graph.objects(instance_uri, INST.hasVariable):
                var_name_from_uri = self.instances_graph.value(var_uri, VAR.name)
                var_value = self.instances_graph.value(var_uri, VAR.value)
                if var_name_from_uri and var_value:
                    instance_vars[str(var_name_from_uri)] = str(var_value)

            actual_value = instance_vars.get(var_name)

            if actual_value is None:
                return False

            result = self._compare_values(actual_value, expected_value, operator)
            return result

        except Exception as e:
            logger.warning(f"Failed to evaluate condition on flow {flow_uri}: {e}")
            return False

    def _compare_values(self, actual: str, expected: str, operator: str) -> bool:
        """Compare two values using the given operator"""
        # Map operators
        op_map = {
            "==": "=",
            "eq": "=",
            "!=": "!=",
            "neq": "!=",
            ">": ">",
            "gt": ">",
            ">=": ">=",
            "gte": ">=",
            "<": "<",
            "lt": "<",
            "<=": "<=",
            "lte": "<=",
        }
        op = op_map.get(operator, operator)

        # Try numeric comparison
        try:
            actual_num = float(actual)
            expected_num = float(expected)

            if op == "=":
                return actual_num == expected_num
            elif op == "!=":
                return actual_num != expected_num
            elif op == ">":
                return actual_num > expected_num
            elif op == ">=":
                return actual_num >= expected_num
            elif op == "<":
                return actual_num < expected_num
            elif op == "<=":
                return actual_num <= expected_num
        except ValueError:
            pass  # Not numeric, try string comparison

        # String comparison
        if op == "=":
            return actual == expected
        elif op == "!=":
            return actual != expected
        elif op in (">", ">=", "<", "<="):
            # String comparison for inequalities
            try:
                actual_num = float(actual)
                expected_num = float(expected)
                if op == ">":
                    return actual_num > expected_num
                elif op == ">=":
                    return actual_num >= expected_num
                elif op == "<":
                    return actual_num < expected_num
                elif op == "<=":
                    return actual_num <= expected_num
            except ValueError:
                # Fallback to lexicographic comparison
                if op == ">":
                    return actual > expected
                elif op == ">=":
                    return actual >= expected
                elif op == "<":
                    return actual < expected
                elif op == "<=":
                    return actual <= expected

        return False

        # Get default flow if exists (for exclusive gateway)
        default_flow = self.definitions_graph.value(gateway_uri, BPMN.default)

        # Check each flow for conditions
        for flow_uri, target_uri in outgoing_flows:
            # Skip default flow - it's only used if no other conditions match
            if default_flow and flow_uri == default_flow:
                continue

            # Check if flow has a condition query
            condition_query = self.definitions_graph.value(
                flow_uri, BPMN.conditionQuery
            )

            if condition_query:
                try:
                    # Execute SPARQL ASK query
                    query_str = str(condition_query)

                    # Bind the instance URI
                    result = self.definitions_graph.query(
                        query_str, initBindings={"instance": instance_uri}
                    )

                    if result.askAnswer:
                        logger.info(
                            f"Condition matched on flow {flow_uri}, proceeding to {target_uri}"
                        )
                        return target_uri

                except Exception as e:
                    logger.warning(
                        f"Failed to evaluate condition on flow {flow_uri}: {e}"
                    )
                    continue

        # No conditions matched - check if there's a default flow
        if default_flow:
            for flow_uri, target_uri in outgoing_flows:
                if flow_uri == default_flow:
                    logger.info(f"Using default flow {flow_uri}")
                    return target_uri

        # If only one outgoing flow with no conditions, use it
        if len(outgoing_flows) == 1:
            logger.info(
                f"No conditions on single outgoing flow, proceeding to {outgoing_flows[0][1]}"
            )
            return outgoing_flows[0][1]

        # No valid path found
        logger.warning(f"No valid path found at exclusive gateway {gateway_uri}")
        return None

    def _execute_event_based_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        current_node: URIRef,
        instance_id: str,
    ) -> None:
        """
        Execute an event-based gateway.

        Event-based gateways wait for one of several possible events:
        - Message events (receive tasks)
        - Timer events

        The first event to trigger determines the path taken.
        """
        outgoing_targets = []
        for s, p, flow_uri in self.definitions_graph.triples(
            (current_node, BPMN.outgoing, None)
        ):
            for ss, pp, target in self.definitions_graph.triples(
                (flow_uri, BPMN.targetRef, None)
            ):
                outgoing_targets.append((flow_uri, target))

        if not outgoing_targets:
            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))
            return

        waiting_tasks = []
        for flow_uri, target in outgoing_targets:
            target_type = None
            for s, p, o in self.definitions_graph.triples((target, RDF.type, None)):
                target_type = o
                break

            if target_type in [BPMN.ReceiveTask, BPMN.receiveTask]:
                message_name = None
                for s, p, o in self.definitions_graph.triples(
                    (target, BPMN.message, None)
                ):
                    message_name = str(o)
                    break
                if not message_name:
                    for s, p, o in self.definitions_graph.triples(
                        (
                            target,
                            URIRef("http://camunda.org/schema/1.0/bpmn#message"),
                            None,
                        )
                    ):
                        message_name = str(o)
                        break

                if message_name:
                    waiting_tasks.append(
                        {"type": "message", "target": target, "message": message_name}
                    )
                else:
                    waiting_tasks.append({"type": "receive", "target": target})

        if waiting_tasks:
            self.instances_graph.set((token_uri, INST.status, Literal("WAITING")))

            for task_info in waiting_tasks:
                target = task_info["target"]
                existing_tokens = []
                for tok in self.instances_graph.objects(instance_uri, INST.hasToken):
                    status = self.instances_graph.value(tok, INST.status)
                    current = self.instances_graph.value(tok, INST.currentNode)
                    if status and str(status) == "ACTIVE" and current == target:
                        existing_tokens.append(tok)

                if not existing_tokens:
                    new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                    self.instances_graph.add((new_token_uri, RDF.type, INST.Token))
                    self.instances_graph.add(
                        (new_token_uri, INST.belongsTo, instance_uri)
                    )
                    self.instances_graph.add(
                        (new_token_uri, INST.status, Literal("WAITING"))
                    )
                    self.instances_graph.add((new_token_uri, INST.currentNode, target))
                    self.instances_graph.add(
                        (instance_uri, INST.hasToken, new_token_uri)
                    )

            self._log_instance_event(
                instance_uri,
                "WAITING_FOR_EVENT",
                "System",
                f"Event-based gateway {current_node} waiting for {len(waiting_tasks)} events",
            )
            logger.info(
                f"Event-based gateway at {current_node}, created {len(waiting_tasks)} waiting tokens"
            )
        else:
            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))
            logger.warning(
                f"Event-based gateway {current_node} has no message/receive targets"
            )

    def _move_token_to_next_node(
        self, instance_uri: URIRef, token_uri: URIRef, instance_id: str
    ):
        """Move token to the next node via sequence flows"""
        current_node = self.instances_graph.value(token_uri, INST.currentNode)
        if not current_node:
            return

        # Find outgoing sequence flows and their targets
        next_nodes = []
        for s, p, o in self.definitions_graph.triples(
            (current_node, BPMN.outgoing, None)
        ):
            # o is the sequence flow URI, find its target
            for ss, pp, target in self.definitions_graph.triples(
                (o, BPMN.targetRef, None)
            ):
                next_nodes.append(target)
                break

        if next_nodes:
            # Move token to first target
            self.instances_graph.set((token_uri, INST.currentNode, next_nodes[0]))

            # If there are additional targets, create new tokens (for gateways/splits)
            for additional_target in next_nodes[1:]:
                new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                self.instances_graph.add((new_token_uri, RDF.type, INST.Token))
                self.instances_graph.add((new_token_uri, INST.belongsTo, instance_uri))
                self.instances_graph.add(
                    (new_token_uri, INST.status, Literal("ACTIVE"))
                )
                self.instances_graph.add(
                    (new_token_uri, INST.currentNode, additional_target)
                )
                self.instances_graph.add((instance_uri, INST.hasToken, new_token_uri))
        else:
            # No outgoing flows - consume token
            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

    def _is_instance_completed(self, instance_uri: URIRef) -> bool:
        """Check if all tokens in an instance are consumed"""
        for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
            status = self.instances_graph.value(token_uri, INST.status)
            if not status or str(status) != "CONSUMED":
                return False
        return True

    def _count_incoming_flows(self, gateway_uri: URIRef) -> int:
        """Count the number of incoming sequence flows to a gateway"""
        count = 0
        for _ in self.definitions_graph.triples((gateway_uri, BPMN.incoming, None)):
            count += 1
        return count

    def _count_waiting_tokens_at_incoming(
        self, instance_uri: URIRef, gateway_uri: URIRef
    ) -> int:
        """Count tokens that have arrived at the incoming targets of a gateway"""
        count = 0
        for s, p, incoming_flow in self.definitions_graph.triples(
            (gateway_uri, BPMN.incoming, None)
        ):
            for ss, pp, target in self.definitions_graph.triples(
                (incoming_flow, BPMN.targetRef, None)
            ):
                for token_uri in self.instances_graph.objects(
                    instance_uri, INST.hasToken
                ):
                    status = self.instances_graph.value(token_uri, INST.status)
                    current_node = self.instances_graph.value(
                        token_uri, INST.currentNode
                    )
                    # For join detection, count tokens at the gateway regardless of status
                    # (CONSUMED tokens may have arrived but not yet been merged)
                    if current_node == gateway_uri:
                        count += 1
        return count

    def _merge_parallel_tokens(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
        instance_id: str,
        next_node: URIRef,
    ):
        """Consume all tokens waiting at gateway and create one token for next node"""
        for s, p, incoming_flow in self.definitions_graph.triples(
            (gateway_uri, BPMN.incoming, None)
        ):
            for ss, pp, target in self.definitions_graph.triples(
                (incoming_flow, BPMN.targetRef, None)
            ):
                for token_uri in self.instances_graph.objects(
                    instance_uri, INST.hasToken
                ):
                    current_node = self.instances_graph.value(
                        token_uri, INST.currentNode
                    )
                    # For join, tokens are at the gateway, not at the incoming target
                    if current_node == gateway_uri:
                        self.instances_graph.set(
                            (token_uri, INST.status, Literal("CONSUMED"))
                        )

        merged_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
        self.instances_graph.add((merged_token_uri, RDF.type, INST.Token))
        self.instances_graph.add((merged_token_uri, INST.belongsTo, instance_uri))
        self.instances_graph.add((merged_token_uri, INST.status, Literal("ACTIVE")))
        self.instances_graph.add((merged_token_uri, INST.currentNode, next_node))
        self.instances_graph.add((instance_uri, INST.hasToken, merged_token_uri))

    def _merge_inclusive_tokens(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
        instance_id: str,
        next_nodes: List[URIRef],
    ):
        """Consume all tokens waiting at inclusive gateway and create token(s) for next nodes"""
        tokens_consumed = 0
        for s, p, incoming_flow in self.definitions_graph.triples(
            (gateway_uri, BPMN.incoming, None)
        ):
            for ss, pp, target in self.definitions_graph.triples(
                (incoming_flow, BPMN.targetRef, None)
            ):
                for token_uri in self.instances_graph.objects(
                    instance_uri, INST.hasToken
                ):
                    current_node = self.instances_graph.value(
                        token_uri, INST.currentNode
                    )
                    # For join, tokens are at the gateway, not at the incoming target
                    if current_node == gateway_uri:
                        self.instances_graph.set(
                            (token_uri, INST.status, Literal("CONSUMED"))
                        )
                        tokens_consumed += 1

        if len(next_nodes) > 1:
            logger.debug(
                f"Inclusive gateway {gateway_uri} forking to {len(next_nodes)} paths"
            )
            for i, next_node in enumerate(next_nodes):
                new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                self.instances_graph.add((new_token_uri, RDF.type, INST.Token))
                self.instances_graph.add((new_token_uri, INST.belongsTo, instance_uri))
                self.instances_graph.add(
                    (new_token_uri, INST.status, Literal("ACTIVE"))
                )
                self.instances_graph.add((new_token_uri, INST.currentNode, next_node))
                self.instances_graph.add((instance_uri, INST.hasToken, new_token_uri))
                logger.debug(f"  Created token {new_token_uri} for node {next_node}")

            self._log_instance_event(
                instance_uri,
                "INCLUSIVE_GATEWAY_MERGE",
                "System",
                f"Inclusive gateway {str(gateway_uri)} merged and forked to {len(next_nodes)} paths",
            )

            logger.info(
                f"Inclusive gateway {gateway_uri} created {len(next_nodes)} tokens after merge"
            )
        elif len(next_nodes) == 1:
            logger.debug(
                f"Inclusive gateway {gateway_uri} merging to single path: {next_nodes[0]}"
            )
            merged_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
            self.instances_graph.add((merged_token_uri, RDF.type, INST.Token))
            self.instances_graph.add((merged_token_uri, INST.belongsTo, instance_uri))
            self.instances_graph.add((merged_token_uri, INST.status, Literal("ACTIVE")))
            self.instances_graph.add(
                (merged_token_uri, INST.currentNode, next_nodes[0])
            )
            self.instances_graph.add((instance_uri, INST.hasToken, merged_token_uri))
            logger.debug(f"  Created merged token {merged_token_uri}")

            self._log_instance_event(
                instance_uri,
                "INCLUSIVE_GATEWAY_MERGE",
                "System",
                f"Inclusive gateway {str(gateway_uri)} merged to single path",
            )

    def _is_multi_instance(self, node_uri: URIRef) -> Dict[str, Any]:
        """Check if a node has multi-instance characteristics"""
        result = {
            "is_multi_instance": False,
            "is_parallel": False,
            "is_sequential": False,
            "loop_cardinality": None,
            "data_input": None,
            "data_output": None,
            "completion_condition": None,
        }

        for s, p, o in self.definitions_graph.triples(
            (node_uri, BPMN.loopCharacteristics, None)
        ):
            loop_char_uri = o
            result["is_multi_instance"] = True

            for ss, pp, oo in self.definitions_graph.triples(
                (loop_char_uri, RDF.type, None)
            ):
                if "Parallel" in str(oo):
                    result["is_parallel"] = True
                elif "Sequential" in str(oo):
                    result["is_sequential"] = True

            for ss, pp, oo in self.definitions_graph.triples(
                (loop_char_uri, BPMN.loopCardinality, None)
            ):
                result["loop_cardinality"] = str(oo)
            for ss, pp, oo in self.definitions_graph.triples(
                (loop_char_uri, BPMN.cardinality, None)
            ):
                result["loop_cardinality"] = str(oo)

            for ss, pp, oo in self.definitions_graph.triples(
                (loop_char_uri, BPMN.dataInput, None)
            ):
                result["data_input"] = str(oo)
            for ss, pp, oo in self.definitions_graph.triples(
                (loop_char_uri, BPMN.dataOutput, None)
            ):
                result["data_output"] = str(oo)

            for ss, pp, oo in self.definitions_graph.triples(
                (loop_char_uri, BPMN.completionCondition, None)
            ):
                result["completion_condition"] = str(oo)

            break

        return result

    def _create_multi_instance_tokens(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        mi_info: Dict[str, Any],
    ) -> List[URIRef]:
        """Create tokens for multi-instance activity execution"""
        created_tokens = []

        if mi_info["is_parallel"]:
            if mi_info["loop_cardinality"]:
                try:
                    count = int(mi_info["loop_cardinality"])
                except ValueError:
                    count = 3
            else:
                count = 3

            logger.info(
                f"Creating {count} parallel tokens for multi-instance activity {node_uri}"
            )

            for i in range(count):
                loop_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                self.instances_graph.add((loop_token_uri, RDF.type, INST.Token))
                self.instances_graph.add((loop_token_uri, INST.belongsTo, instance_uri))
                self.instances_graph.add(
                    (loop_token_uri, INST.status, Literal("ACTIVE"))
                )
                self.instances_graph.add((loop_token_uri, INST.currentNode, node_uri))
                self.instances_graph.add(
                    (loop_token_uri, INST.loopInstance, Literal(str(i)))
                )
                self.instances_graph.add((instance_uri, INST.hasToken, loop_token_uri))

                created_tokens.append(loop_token_uri)

            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        elif mi_info["is_sequential"]:
            loop_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
            self.instances_graph.add((loop_token_uri, RDF.type, INST.Token))
            self.instances_graph.add((loop_token_uri, INST.belongsTo, instance_uri))
            self.instances_graph.add((loop_token_uri, INST.status, Literal("ACTIVE")))
            self.instances_graph.add((loop_token_uri, INST.currentNode, node_uri))
            self.instances_graph.add((loop_token_uri, INST.loopInstance, Literal("0")))
            self.instances_graph.add(
                (
                    loop_token_uri,
                    INST.loopTotal,
                    Literal(mi_info["loop_cardinality"] or "3"),
                )
            )
            self.instances_graph.add((instance_uri, INST.hasToken, loop_token_uri))

            created_tokens.append(loop_token_uri)

            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        return created_tokens

    def _complete_loop_instance(
        self,
        instance_uri: URIRef,
        completed_token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        mi_info: Dict[str, Any],
    ) -> bool:
        """Handle completion of a single loop instance"""
        instance_num = None
        for o in self.instances_graph.objects(completed_token_uri, INST.loopInstance):
            instance_num = int(str(o)) if o else 0
            break

        total_count = 3
        for o in self.instances_graph.objects(completed_token_uri, INST.loopTotal):
            try:
                total_count = int(str(o))
            except (ValueError, TypeError):
                pass
            break

        if mi_info["is_parallel"]:
            consumed_count = 0
            for tok in self.instances_graph.objects(instance_uri, INST.hasToken):
                status = self.instances_graph.value(tok, INST.status)
                current = self.instances_graph.value(tok, INST.currentNode)
                if status and str(status) == "CONSUMED" and current == node_uri:
                    consumed_count += 1

            next_nodes = []
            for s, p, o in self.definitions_graph.triples(
                (node_uri, BPMN.outgoing, None)
            ):
                for ss, pp, target in self.definitions_graph.triples(
                    (o, BPMN.targetRef, None)
                ):
                    next_nodes.append(target)
                    break

            already_advanced = False
            for next_node in next_nodes:
                for tok in self.instances_graph.objects(instance_uri, INST.hasToken):
                    current = self.instances_graph.value(tok, INST.currentNode)
                    if current == next_node:
                        already_advanced = True
                        break
                if already_advanced:
                    break

            should_advance = not already_advanced and consumed_count >= total_count - 1

            self.instances_graph.set(
                (completed_token_uri, INST.status, Literal("CONSUMED"))
            )

            logger.info(
                f"Parallel loop {instance_num} completed. {consumed_count}/{total_count} instances done, advance={should_advance}"
            )

            if should_advance:
                self._advance_multi_instance(instance_uri, node_uri, instance_id)
                return True

        elif mi_info["is_sequential"]:
            next_instance = instance_num + 1
            self.instances_graph.set(
                (completed_token_uri, INST.status, Literal("CONSUMED"))
            )
            if next_instance < total_count:
                next_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                self.instances_graph.add((next_token_uri, RDF.type, INST.Token))
                self.instances_graph.add((next_token_uri, INST.belongsTo, instance_uri))
                self.instances_graph.add(
                    (next_token_uri, INST.status, Literal("ACTIVE"))
                )
                self.instances_graph.add((next_token_uri, INST.currentNode, node_uri))
                self.instances_graph.add(
                    (next_token_uri, INST.loopInstance, Literal(str(next_instance)))
                )
                self.instances_graph.add(
                    (next_token_uri, INST.loopTotal, Literal(str(total_count)))
                )
                self.instances_graph.add((instance_uri, INST.hasToken, next_token_uri))

                logger.info(
                    f"Sequential loop {instance_num} completed. Starting instance {next_instance}/{total_count}"
                )
            else:
                logger.info(
                    f"Sequential loop {instance_num} completed. All {total_count} instances done"
                )
                self._advance_multi_instance(instance_uri, node_uri, instance_id)
                return True

        return False

    def _advance_multi_instance(
        self, instance_uri: URIRef, node_uri: URIRef, instance_id: str
    ):
        """Advance past a completed multi-instance activity"""
        next_nodes = []
        for s, p, o in self.definitions_graph.triples((node_uri, BPMN.outgoing, None)):
            for ss, pp, target in self.definitions_graph.triples(
                (o, BPMN.targetRef, None)
            ):
                next_nodes.append(target)
                break

        if next_nodes:
            self.instances_graph.set((instance_uri, INST.currentNode, next_nodes[0]))
            new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
            self.instances_graph.add((new_token_uri, RDF.type, INST.Token))
            self.instances_graph.add((new_token_uri, INST.belongsTo, instance_uri))
            self.instances_graph.add((new_token_uri, INST.status, Literal("ACTIVE")))
            self.instances_graph.add((new_token_uri, INST.currentNode, next_nodes[0]))
            self.instances_graph.add((instance_uri, INST.hasToken, new_token_uri))

            logger.info(f"Advanced past multi-instance activity to {next_nodes[0]}")

    # ==================== Task Management ====================

    def create_task(
        self,
        instance_id: str,
        node_uri: str,
        name: str = "User Task",
        assignee: Optional[str] = None,
        candidate_users: Optional[List[str]] = None,
        candidate_groups: Optional[List[str]] = None,
        form_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new user task"""
        task_id = str(uuid.uuid4())
        task_uri = TASK[task_id]
        instance_uri = INST[instance_id]

        # Create task in RDF
        self.tasks_graph.add((task_uri, RDF.type, TASK.UserTask))
        self.tasks_graph.add((task_uri, TASK.instance, instance_uri))
        self.tasks_graph.add((task_uri, TASK.node, URIRef(node_uri)))
        self.tasks_graph.add((task_uri, TASK.name, Literal(name)))
        self.tasks_graph.add((task_uri, TASK.status, Literal("CREATED")))
        self.tasks_graph.add(
            (task_uri, TASK.createdAt, Literal(datetime.now().isoformat()))
        )

        if assignee:
            self.tasks_graph.add((task_uri, TASK.assignee, Literal(assignee)))

        if candidate_users:
            for user in candidate_users:
                self.tasks_graph.add((task_uri, TASK.candidateUser, Literal(user)))

        if candidate_groups:
            for group in candidate_groups:
                self.tasks_graph.add((task_uri, TASK.candidateGroup, Literal(group)))

        if form_data:
            form_uri = TASK[f"form_{task_id}"]
            self.tasks_graph.add((task_uri, TASK.hasForm, form_uri))
            for key, value in form_data.items():
                self.tasks_graph.add((form_uri, TASK.fieldName, Literal(key)))
                self.tasks_graph.add((form_uri, TASK.fieldValue, Literal(str(value))))

        # Link task to instance
        self.instances_graph.add((instance_uri, INST.hasTask, task_uri))

        self._save_graph(self.tasks_graph, "tasks.ttl")

        logger.info(f"Created task {task_id} for instance {instance_id}")

        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID"""
        task_uri = TASK[task_id]

        if not (task_uri, RDF.type, TASK.UserTask) in self.tasks_graph:
            return None

        instance_uri = self.tasks_graph.value(task_uri, TASK.instance)
        node_uri = self.tasks_graph.value(task_uri, TASK.node)
        name = self.tasks_graph.value(task_uri, TASK.name)
        status = self.tasks_graph.value(task_uri, TASK.status)
        assignee = self.tasks_graph.value(task_uri, TASK.assignee)
        created_at = self.tasks_graph.value(task_uri, TASK.createdAt)
        claimed_at = self.tasks_graph.value(task_uri, TASK.claimedAt)
        completed_at = self.tasks_graph.value(task_uri, TASK.completedAt)

        instance_id = str(instance_uri).split("/")[-1] if instance_uri else None

        candidate_users = [
            str(u) for u in self.tasks_graph.objects(task_uri, TASK.candidateUser)
        ]
        candidate_groups = [
            str(g) for g in self.tasks_graph.objects(task_uri, TASK.candidateGroup)
        ]

        form_data = {}
        form_uri = self.tasks_graph.value(task_uri, TASK.hasForm)
        if form_uri:
            for field_name in self.tasks_graph.objects(form_uri, TASK.fieldName):
                field_value = self.tasks_graph.value(form_uri, TASK[field_name])
                if field_value:
                    form_data[str(field_name)] = str(field_value)

        return {
            "id": task_id,
            "instance_id": instance_id,
            "node_uri": str(node_uri) if node_uri else None,
            "name": str(name) if name else "User Task",
            "status": str(status) if status else "CREATED",
            "assignee": str(assignee) if assignee else None,
            "candidate_users": candidate_users,
            "candidate_groups": candidate_groups,
            "form_data": form_data,
            "created_at": str(created_at) if created_at else None,
            "claimed_at": str(claimed_at) if claimed_at else None,
            "completed_at": str(completed_at) if completed_at else None,
        }

    def list_tasks(
        self,
        instance_id: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List tasks with optional filtering"""
        tasks = []

        for task_uri in self.tasks_graph.subjects(RDF.type, TASK.UserTask):
            task_id = str(task_uri).split("/")[-1]
            task_data = self.get_task(task_id)

            if not task_data:
                continue

            if instance_id and task_data["instance_id"] != instance_id:
                continue
            if status and task_data["status"] != status:
                continue
            if assignee and task_data["assignee"] != assignee:
                continue

            tasks.append(task_data)

        total = len(tasks)
        start = (page - 1) * page_size
        end = start + page_size
        tasks = tasks[start:end]

        return {"tasks": tasks, "total": total, "page": page, "page_size": page_size}

    def claim_task(self, task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Claim a task for a user"""
        task_uri = TASK[task_id]

        if not (task_uri, RDF.type, TASK.UserTask) in self.tasks_graph:
            return None

        status = self.tasks_graph.value(task_uri, TASK.status)
        if status and str(status) != "CREATED":
            raise ValueError(f"Task {task_id} cannot be claimed (status: {status})")

        assignee = self.tasks_graph.value(task_uri, TASK.assignee)
        if assignee and str(assignee) != user_id:
            candidate_users = [
                str(u) for u in self.tasks_graph.objects(task_uri, TASK.candidateUser)
            ]
            if user_id not in candidate_users:
                raise ValueError(
                    f"User {user_id} is not authorized to claim task {task_id}"
                )

        self.tasks_graph.set((task_uri, TASK.assignee, Literal(user_id)))
        self.tasks_graph.set((task_uri, TASK.status, Literal("CLAIMED")))
        self.tasks_graph.set(
            (task_uri, TASK.claimedAt, Literal(datetime.now().isoformat()))
        )

        self._log_task_event(task_uri, "CLAIMED", user_id)
        self._save_graph(self.tasks_graph, "tasks.ttl")

        logger.info(f"Task {task_id} claimed by user {user_id}")

        return self.get_task(task_id)

    def complete_task(
        self, task_id: str, user_id: str, variables: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Complete a task"""
        task_uri = TASK[task_id]

        if not (task_uri, RDF.type, TASK.UserTask) in self.tasks_graph:
            return None

        status = self.tasks_graph.value(task_uri, TASK.status)
        if status and str(status) not in ["CREATED", "CLAIMED"]:
            raise ValueError(f"Task {task_id} cannot be completed (status: {status})")

        assignee = self.tasks_graph.value(task_uri, TASK.assignee)
        if assignee and str(assignee) != user_id:
            raise ValueError(
                f"User {user_id} cannot complete task {task_id} (assigned to {assignee})"
            )

        self.tasks_graph.set((task_uri, TASK.status, Literal("COMPLETED")))
        self.tasks_graph.set(
            (task_uri, TASK.completedAt, Literal(datetime.now().isoformat()))
        )

        if variables:
            instance_uri = self.tasks_graph.value(task_uri, TASK.instance)
            instance_id = str(instance_uri).split("/")[-1]
            for name, value in variables.items():
                self.set_instance_variable(instance_id, name, value)

        # Execute "complete" task listeners
        node_uri = self.tasks_graph.value(task_uri, TASK.node)
        if node_uri:
            self._execute_task_listeners(
                instance_uri, None, node_uri, instance_id, "complete"
            )

        self._log_task_event(task_uri, "COMPLETED", user_id)
        self._save_graph(self.tasks_graph, "tasks.ttl")

        logger.info(f"Task {task_id} completed by user {user_id}")

        return self.get_task(task_id)

    def assign_task(
        self, task_id: str, assignee: str, assigner: str = "System"
    ) -> Optional[Dict[str, Any]]:
        """Assign a task to a user"""
        task_uri = TASK[task_id]

        if not (task_uri, RDF.type, TASK.UserTask) in self.tasks_graph:
            return None

        old_assignee = self.tasks_graph.value(task_uri, TASK.assignee)

        self.tasks_graph.set((task_uri, TASK.assignee, Literal(assignee)))
        self.tasks_graph.set((task_uri, TASK.status, Literal("ASSIGNED")))

        # Execute "assignment" task listeners
        node_uri = self.tasks_graph.value(task_uri, TASK.node)
        instance_uri = self.tasks_graph.value(task_uri, TASK.instance)
        if node_uri and instance_uri:
            instance_id = str(instance_uri).split("/")[-1]
            self._execute_task_listeners(
                instance_uri, None, node_uri, instance_id, "assignment"
            )

        self._log_task_event(
            task_uri,
            "ASSIGNED",
            assigner,
            f"Assigned from {old_assignee} to {assignee}",
        )
        self._save_graph(self.tasks_graph, "tasks.ttl")

        logger.info(f"Task {task_id} assigned to {assignee}")

        return self.get_task(task_id)

    def _log_task_event(
        self, task_uri: URIRef, event_type: str, user: str, details: str = ""
    ):
        """Log a task event"""
        event_uri = LOG[f"task_event_{str(uuid.uuid4())}"]

        self.audit_graph.add((event_uri, RDF.type, LOG.Event))
        self.audit_graph.add((event_uri, LOG.task, task_uri))
        self.audit_graph.add((event_uri, LOG.eventType, Literal(event_type)))
        self.audit_graph.add((event_uri, LOG.user, Literal(user)))
        self.audit_graph.add(
            (event_uri, LOG.timestamp, Literal(datetime.now().isoformat()))
        )
        if details:
            self.audit_graph.add((event_uri, LOG.details, Literal(details)))

        self._save_graph(self.audit_graph, "audit.ttl")

    def get_task_for_instance_node(
        self, instance_id: str, node_uri: str
    ) -> Optional[Dict[str, Any]]:
        """Get the task associated with a specific instance and node"""
        for task_uri in self.tasks_graph.subjects(RDF.type, TASK.UserTask):
            task_instance = self.tasks_graph.value(task_uri, TASK.instance)
            task_node = self.tasks_graph.value(task_uri, TASK.node)

            if task_instance and task_node:
                task_instance_id = str(task_instance).split("/")[-1]
                if task_instance_id == instance_id and str(task_node) == node_uri:
                    task_id = str(task_uri).split("/")[-1]
                    return self.get_task(task_id)
        return None

    def resume_instance_from_task(self, task_id: str) -> bool:
        """After task completion, resume the instance by moving the token"""
        task_data = self.get_task(task_id)
        if not task_data or task_data["status"] != "COMPLETED":
            return False

        instance_id = task_data["instance_id"]
        node_uri = task_data["node_uri"]

        if not instance_id or not node_uri:
            return False

        instance_uri = INST[instance_id]

        # Find the token waiting at this node
        for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
            current_node = self.instances_graph.value(token_uri, INST.status)
            token_status = self.instances_graph.value(token_uri, INST.status)
            if token_status and str(token_status) == "WAITING":
                token_node = self.instances_graph.value(token_uri, INST.currentNode)
                if token_node and str(token_node) == node_uri:
                    # Move token to next node
                    self._move_token_to_next_node(instance_uri, token_uri, instance_id)
                    self._save_graph(self.instances_graph, "instances.ttl")
                    logger.info(f"Resumed instance {instance_id} after task {task_id}")

                    # Continue execution
                    self._execute_instance(instance_uri, instance_id)
                    return True

        return False

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics"""
        # Count processes
        process_count = len(
            list(self.definitions_graph.subjects(RDF.type, PROC.ProcessDefinition))
        )

        # Count instances
        instance_count = len(
            list(self.instances_graph.subjects(RDF.type, INST.ProcessInstance))
        )

        # Count RDF triples
        triple_count = (
            len(self.definitions_graph)
            + len(self.instances_graph)
            + len(self.audit_graph)
        )

        return {
            "process_count": process_count,
            "instance_count": instance_count,
            "total_triples": triple_count,
        }

    # ==================== Service Task Handlers ====================

    def register_topic_handler(
        self,
        topic: str,
        handler_function: callable,
        description: str = "",
        async_execution: bool = False,
        handler_type: str = "function",
        http_config: Dict = None,
    ) -> bool:
        """
        Register a handler for a topic.

        Args:
            topic: The topic name to register
            handler_function: The function to call when the topic is executed
            description: Human-readable description of the handler
            async_execution: Whether to execute asynchronously
            handler_type: Type of handler (http, script, function, webhook)
            http_config: HTTP handler configuration (if applicable)

        Returns:
            True if registered successfully
        """
        from datetime import datetime

        self.topic_handlers[topic] = {
            "function": handler_function,
            "description": description,
            "async": async_execution,
            "registered_at": datetime.utcnow().isoformat(),
            "handler_type": handler_type,
            "http_config": http_config,
        }

        logger.info(f"Registered handler for topic: {topic}")
        return True

    def update_topic_description(self, topic: str, description: str) -> bool:
        """
        Update the description of a topic handler.

        Args:
            topic: The topic name
            description: New description

        Returns:
            True if updated, False if topic doesn't exist
        """
        if topic not in self.topic_handlers:
            return False

        self.topic_handlers[topic]["description"] = description
        logger.info(f"Updated description for topic: {topic}")
        return True

    def update_topic_async(self, topic: str, async_execution: bool) -> bool:
        """
        Update the async execution setting of a topic handler.

        Args:
            topic: The topic name
            async_execution: New async setting

        Returns:
            True if updated, False if topic doesn't exist
        """
        if topic not in self.topic_handlers:
            return False

        self.topic_handlers[topic]["async"] = async_execution
        logger.info(f"Updated async setting for topic: {topic}")
        return True

    def unregister_topic_handler(self, topic: str) -> bool:
        """
        Unregister a handler for a topic.

        Args:
            topic: The topic name to unregister

        Returns:
            True if unregistered, False if topic didn't exist
        """
        if topic in self.topic_handlers:
            del self.topic_handlers[topic]
            logger.info(f"Unregistered handler for topic: {topic}")
            return True
        return False

    def get_registered_topics(self) -> Dict[str, Any]:
        """
        Get all registered topic handlers.

        Returns:
            Dictionary of topic -> handler info (without the actual function)
        """
        topics = {}
        for topic, info in self.topic_handlers.items():
            topics[topic] = {
                "description": info.get("description", ""),
                "async": info.get("async", False),
                "registered_at": info.get("registered_at", ""),
                "handler_type": info.get("handler_type", "function"),
                "http_config": info.get("http_config"),
            }
        return topics

    def execute_service_task(
        self,
        instance_id: str,
        topic: str,
        variables: Dict[str, Any],
        loop_idx: int = None,
    ) -> Dict[str, Any]:
        """
        Execute a service task handler.

        Args:
            instance_id: The process instance ID
            topic: The topic to execute
            variables: Current process variables
            loop_idx: Loop instance index (for multi-instance activities)

        Returns:
            Updated variables after handler execution

        Raises:
            ValueError: If no handler is registered for the topic
        """
        if topic not in self.topic_handlers:
            raise ValueError(f"No handler registered for topic: {topic}")

        handler_info = self.topic_handlers[topic]
        handler_function = handler_info["function"]

        logger.info(f"Executing service task {topic} for instance {instance_id}")

        try:
            # Execute the handler with loop_idx support
            if handler_info["async"]:
                updated_variables = handler_function(instance_id, variables, loop_idx)
            else:
                updated_variables = handler_function(instance_id, variables, loop_idx)

            logger.info(f"Service task {topic} completed for instance {instance_id}")
            return updated_variables

        except TypeError:
            old_handler_function = handler_function
            logger.debug(
                f"Handler for {topic} doesn't support loop_idx, trying without it"
            )
            updated_variables = old_handler_function(instance_id, variables)
            logger.info(f"Service task {topic} completed for instance {instance_id}")
            return updated_variables

        except Exception as e:
            logger.error(f"Service task {topic} failed for instance {instance_id}: {e}")
            raise

    # ==================== Message Handling ====================

    def register_message_handler(
        self,
        message_name: str,
        handler_function: callable,
        description: str = "",
    ) -> bool:
        """
        Register a handler for a message (for receive tasks and event-based gateways).

        Args:
            message_name: The message name to register
            handler_function: The function to call when message is received
            description: Human-readable description of the handler

        Returns:
            True if registered successfully
        """
        from datetime import datetime

        self.message_handlers[message_name] = {
            "function": handler_function,
            "description": description,
            "registered_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Registered handler for message: {message_name}")
        return True

    def unregister_message_handler(self, message_name: str) -> bool:
        """
        Unregister a handler for a message.

        Args:
            message_name: The message name to unregister

        Returns:
            True if unregistered, False if message didn't exist
        """
        if message_name in self.message_handlers:
            del self.message_handlers[message_name]
            logger.info(f"Unregistered handler for message: {message_name}")
            return True
        return False

    def send_message(
        self,
        message_name: str,
        instance_id: str = None,
        variables: Dict[str, Any] = None,
        correlation_id: str = None,
    ) -> Dict[str, Any]:
        """
        Send a message to waiting receive tasks or event-based gateways.

        Args:
            message_name: The message name
            instance_id: Optional specific instance to target
            variables: Optional variables to merge with the message
            correlation_id: Optional correlation ID for routing

        Returns:
            Dictionary with status and matched task info
        """
        from datetime import datetime

        message = {
            "name": message_name,
            "instance_id": instance_id,
            "variables": variables or {},
            "correlation_id": correlation_id,
            "received_at": datetime.utcnow().isoformat(),
        }

        matched = []

        for token_uri in self.instances_graph.subjects(RDF.type, INST.Token):
            token_status = self.instances_graph.value(token_uri, INST.status)
            if not token_status or str(token_status) != "WAITING":
                continue

            current_node = self.instances_graph.value(token_uri, INST.currentNode)
            if not current_node:
                continue

            node_type = None
            for s, p, o in self.definitions_graph.triples(
                (current_node, RDF.type, None)
            ):
                node_type = o
                break

            if node_type not in [BPMN.ReceiveTask, BPMN.receiveTask]:
                continue

            node_message = None
            for s, p, o in self.definitions_graph.triples(
                (current_node, BPMN.message, None)
            ):
                node_message = str(o)
                break
            if not node_message:
                for s, p, o in self.definitions_graph.triples(
                    (
                        current_node,
                        URIRef("http://camunda.org/schema/1.0/bpmn#message"),
                        None,
                    )
                ):
                    node_message = str(o)
                    break

            if node_message != message_name:
                continue

            instance_uri = self.instances_graph.value(token_uri, INST.belongsTo)
            if instance_uri and instance_id:
                inst_id = str(instance_uri).split("/")[-1]
                if inst_id != instance_id:
                    continue

            matched.append(
                {
                    "token_uri": str(token_uri),
                    "node_uri": str(current_node),
                    "instance_uri": str(instance_uri) if instance_uri else None,
                }
            )

        if matched:
            for match in matched:
                token_uri = URIRef(match["token_uri"])
                self.instances_graph.set((token_uri, INST.status, Literal("ACTIVE")))
                current_node = URIRef(match["node_uri"])
                instance_uri = (
                    URIRef(match["instance_uri"]) if match["instance_uri"] else None
                )

                if variables:
                    instance_id_for_var = (
                        str(match["instance_uri"]).split("/")[-1]
                        if match["instance_uri"]
                        else None
                    )
                    if instance_id_for_var:
                        for var_name, var_value in variables.items():
                            var_uri = VAR[f"{instance_id_for_var}_{var_name}"]
                            self.instances_graph.add(
                                (var_uri, VAR.name, Literal(var_name))
                            )
                            self.instances_graph.add(
                                (var_uri, VAR.value, Literal(str(var_value)))
                            )

                self._log_instance_event(
                    instance_uri,
                    "MESSAGE_RECEIVED",
                    "System",
                    f"Message '{message_name}' received at {current_node}",
                )

            logger.info(
                f"Message '{message_name}' matched {len(matched)} waiting tasks"
            )

        message["matched_count"] = len(matched)

        boundary_matches = []
        for token_uri in self.instances_graph.subjects(RDF.type, INST.Token):
            token_status = self.instances_graph.value(token_uri, INST.status)
            if not token_status or str(token_status) not in ["WAITING", "ACTIVE"]:
                continue

            current_node = self.instances_graph.value(token_uri, INST.currentNode)
            if not current_node:
                continue

            nodes_to_check = [current_node]
            for parent in self.definitions_graph.objects(current_node, BPMN.hasParent):
                nodes_to_check.append(parent)

            for node_to_check in nodes_to_check:
                boundary_events = self.get_boundary_events_for_node(node_to_check)
                for event_info in boundary_events:
                    if (
                        event_info["event_type"] == "message"
                        and event_info["message_name"] == message_name
                    ):
                        instance_uri = self.instances_graph.value(
                            token_uri, INST.belongsTo
                        )
                        if instance_uri and instance_id:
                            inst_id = str(instance_uri).split("/")[-1]
                            if inst_id != instance_id:
                                continue

                        boundary_matches.append(
                            {
                                "token_uri": str(token_uri),
                                "boundary_event_uri": str(event_info["uri"]),
                                "is_interrupting": event_info["is_interrupting"],
                                "instance_uri": str(instance_uri)
                                if instance_uri
                                else None,
                            }
                        )

        if boundary_matches:
            for match in boundary_matches:
                token_uri = URIRef(match["token_uri"])
                instance_uri = (
                    URIRef(match["instance_uri"]) if match["instance_uri"] else None
                )
                boundary_event_uri = URIRef(match["boundary_event_uri"])
                instance_id_for_var = (
                    str(match["instance_uri"]).split("/")[-1]
                    if match["instance_uri"]
                    else None
                )

                self.trigger_boundary_event(
                    token_uri,
                    instance_uri,
                    boundary_event_uri,
                    instance_id_for_var if instance_id_for_var else "",
                    match["is_interrupting"],
                    variables,
                )

            logger.info(
                f"Message '{message_name}' matched {len(boundary_matches)} boundary events"
            )

        message["boundary_matches"] = boundary_matches
        message["total_matches"] = len(matched) + len(boundary_matches)

        return {
            "status": "delivered" if (matched or boundary_matches) else "no_match",
            "message_name": message_name,
            "matched_count": len(matched) + len(boundary_matches),
            "tasks": matched,
            "boundary_events": boundary_matches,
        }

    def _trigger_message_end_event(
        self,
        instance_uri: URIRef,
        message_name: str,
    ) -> None:
        """Trigger a message from a message end event.

        Args:
            instance_uri: URI of the process instance
            message_name: Name of the message to trigger
        """
        instance_id = str(instance_uri).split("/")[-1]

        logger.info(
            f"Message end event threw message '{message_name}' "
            f"from instance {instance_id}"
        )

        self._log_instance_event(
            instance_uri,
            "MESSAGE_THROWN",
            "System",
            f"Message '{message_name}' thrown from message end event",
        )

    def _execute_receive_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ) -> None:
        """
        Execute a receive task - wait for a message.
        """
        message_name = None
        for s, p, o in self.definitions_graph.triples((node_uri, BPMN.message, None)):
            message_name = str(o)
            break
        if not message_name:
            for s, p, o in self.definitions_graph.triples(
                (node_uri, URIRef("http://camunda.org/schema/1.0/bpmn#message"), None)
            ):
                message_name = str(o)
                break

        if message_name:
            self.instances_graph.set((token_uri, INST.status, Literal("WAITING")))
            self._log_instance_event(
                instance_uri,
                "WAITING_FOR_MESSAGE",
                "System",
                f"Waiting for message '{message_name}' at {node_uri}",
            )
            logger.info(
                f"Token at receive task {node_uri}, waiting for message: {message_name}"
            )
        else:
            self._log_instance_event(
                instance_uri,
                "RECEIVE_TASK",
                "System",
                f"{str(node_uri)} (no message configured)",
            )
            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

    def get_boundary_events_for_node(self, node_uri: URIRef) -> List[Dict[str, Any]]:
        """Get all boundary events attached to a node.

        Args:
            node_uri: URI of the node to find boundary events for

        Returns:
            List of boundary event dictionaries with event details
        """
        boundary_events = []

        for event_uri in self.definitions_graph.objects(
            node_uri, BPMN.hasBoundaryEvent
        ):
            event_info = {
                "uri": event_uri,
                "is_interrupting": True,
                "message_name": None,
                "event_type": None,
            }

            for s, p, o in self.definitions_graph.triples((event_uri, RDF.type, None)):
                o_str = str(o)
                if "MessageBoundaryEvent" in o_str:
                    event_info["event_type"] = "message"
                    message_ref = self.definitions_graph.value(
                        event_uri, BPMN.messageRef
                    )
                    if message_ref:
                        event_info["message_name"] = str(message_ref).split("/")[-1]
                    if not event_info["message_name"]:
                        camunda_message = self.definitions_graph.value(
                            event_uri,
                            URIRef("http://camunda.org/schema/1.0/bpmn#message"),
                        )
                        if camunda_message:
                            event_info["message_name"] = str(camunda_message)
                    break
                elif "TimerBoundaryEvent" in o_str:
                    event_info["event_type"] = "timer"
                    break
                elif "ErrorBoundaryEvent" in o_str:
                    event_info["event_type"] = "error"
                    break
                elif "SignalBoundaryEvent" in o_str:
                    event_info["event_type"] = "signal"
                    break

            interrupting = self.definitions_graph.value(event_uri, BPMN.interrupting)
            if interrupting:
                event_info["is_interrupting"] = str(interrupting).lower() == "true"

            boundary_events.append(event_info)

        return boundary_events

    def get_outgoing_flows_for_node(self, node_uri: URIRef) -> List[URIRef]:
        """Get all outgoing flow targets from a node.

        Args:
            node_uri: URI of the node

        Returns:
            List of target node URIs
        """
        targets = []
        for flow_uri in self.definitions_graph.objects(node_uri, BPMN.outgoing):
            target = self.definitions_graph.value(flow_uri, BPMN.targetRef)
            if target:
                targets.append(target)
        return targets

    def trigger_boundary_event(
        self,
        token_uri: URIRef,
        instance_uri: URIRef,
        boundary_event_uri: URIRef,
        instance_id: str,
        is_interrupting: bool,
        variables: Dict[str, Any] = None,
    ) -> bool:
        """Trigger a boundary event on a token.

        Args:
            token_uri: URI of the token at the parent activity
            instance_uri: URI of the process instance
            boundary_event_uri: URI of the boundary event to trigger
            instance_id: Instance ID string
            is_interrupting: Whether this is an interrupting boundary event
            variables: Optional variables to pass with the event

        Returns:
            True if triggered successfully
        """
        logger.info(
            f"Triggering boundary event {boundary_event_uri} "
            f"(interrupting={is_interrupting})"
        )

        if is_interrupting:
            self._log_instance_event(
                instance_uri,
                "BOUNDARY_INTERRUPTED",
                "System",
                f"Activity interrupted by boundary event {str(boundary_event_uri)}",
            )

        outgoing_targets = self.get_outgoing_flows_for_node(boundary_event_uri)
        if not outgoing_targets:
            logger.warning(f"Boundary event {boundary_event_uri} has no outgoing flows")
            return False

        next_node = outgoing_targets[0]

        instance_id_for_vars = ""
        if instance_uri:
            instance_id_for_vars = str(instance_uri).split("/")[-1]
        if not instance_id_for_vars:
            instance_id_for_vars = instance_id if instance_id else ""

        if is_interrupting:
            self.instances_graph.set((token_uri, INST.currentNode, boundary_event_uri))
            self.instances_graph.set((token_uri, INST.status, Literal("ACTIVE")))

            self._log_instance_event(
                instance_uri,
                "BOUNDARY_EVENT_TRIGGERED",
                "System",
                f"Boundary event {str(boundary_event_uri)} triggered",
            )

            if variables:
                for var_name, var_value in variables.items():
                    self.set_instance_variable(
                        instance_id_for_vars, var_name, var_value
                    )

            self._execute_token(instance_uri, token_uri, instance_id_for_vars)
        else:
            boundary_token_uri = INST[
                f"token_{instance_id_for_vars}_{str(uuid.uuid4())[:8]}"
            ]
            self.instances_graph.add((boundary_token_uri, RDF.type, INST.Token))
            self.instances_graph.add((boundary_token_uri, INST.belongsTo, instance_uri))
            self.instances_graph.add(
                (boundary_token_uri, INST.status, Literal("ACTIVE"))
            )
            self.instances_graph.add(
                (boundary_token_uri, INST.currentNode, boundary_event_uri)
            )
            self.instances_graph.add((instance_uri, INST.hasToken, boundary_token_uri))

            self._log_instance_event(
                instance_uri,
                "BOUNDARY_EVENT_NON_INTERRUPTING",
                "System",
                f"Non-interrupting boundary event {str(boundary_event_uri)} triggered",
            )

            if variables:
                for var_name, var_value in variables.items():
                    var_uri = VAR[f"{instance_id_for_vars}_{var_name}"]
                    self.instances_graph.add((var_uri, VAR.name, Literal(var_name)))
                    self.instances_graph.add(
                        (var_uri, VAR.value, Literal(str(var_value)))
                    )

            self._execute_token(instance_uri, boundary_token_uri, instance_id_for_vars)

        return True

    # ==================== Error Event Handlers ====================

    def _execute_cancel_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ) -> None:
        """Execute a cancel end event - terminates the transaction subprocess."""
        logger.info(
            f"Cancel end event reached at {node_uri} for instance {instance_id}"
        )

        self._log_instance_event(
            instance_uri,
            "CANCEL_EVENT",
            "System",
            f"Cancel end event triggered at {str(node_uri)}",
        )

        self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        transaction_subprocess = self._find_enclosing_transaction(
            instance_uri, node_uri
        )
        if transaction_subprocess:
            self._terminate_transaction_subprocess(
                instance_uri, transaction_subprocess, instance_id
            )

        self.instances_graph.set((instance_uri, INST.status, Literal("CANCELLED")))
        self.instances_graph.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        self._log_instance_event(
            instance_uri,
            "INSTANCE_CANCELLED",
            "System",
            f"Instance cancelled via cancel end event",
        )

        self._save_graph(self.instances_graph, "instances.ttl")

    def _execute_compensation_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ) -> None:
        """Execute a compensation end event - triggers the compensation handler."""
        logger.info(
            f"Compensation end event reached at {node_uri} for instance {instance_id}"
        )

        compensate_ref = self.definitions_graph.value(node_uri, BPMN.compensateRef)
        compensate_ref_str = str(compensate_ref) if compensate_ref else None

        self._log_instance_event(
            instance_uri,
            "COMPENSATION_END_EVENT",
            "System",
            f"Compensation end event triggered at {str(node_uri)}"
            + (f", compensateRef: {compensate_ref_str}" if compensate_ref_str else ""),
        )

        compensation_handler = self._find_compensation_handler(node_uri)
        if compensation_handler:
            self._execute_compensation_handler(
                instance_uri, compensation_handler, instance_id
            )

        self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        self._save_graph(self.instances_graph, "instances.ttl")

    def _execute_error_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ) -> None:
        """Execute an error end event - terminates the instance with error."""
        logger.info(f"Error end event reached at {node_uri} for instance {instance_id}")

        error_ref = self.definitions_graph.value(node_uri, BPMN.errorRef)
        error_code = str(error_ref).split("/")[-1] if error_ref else None

        self._log_instance_event(
            instance_uri,
            "ERROR_END_EVENT",
            "System",
            f"Error end event triggered at {str(node_uri)}"
            + (f", errorCode: {error_code}" if error_code else ""),
        )

        self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))
        self.instances_graph.set((instance_uri, INST.status, Literal("ERROR")))
        self.instances_graph.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        self.set_instance_variable(instance_id, "errorCode", error_code or "UNKNOWN")
        self.set_instance_variable(
            instance_id, "errorNode", str(node_uri).split("/")[-1]
        )

        self._save_graph(self.instances_graph, "instances.ttl")

    def _execute_terminate_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ) -> None:
        """Execute a terminate end event - immediately terminates the instance."""
        logger.info(
            f"Terminate end event reached at {node_uri} for instance {instance_id}"
        )

        self._log_instance_event(
            instance_uri,
            "TERMINATE_END_EVENT",
            "System",
            f"Terminate end event triggered at {str(node_uri)} - immediately terminating instance",
        )

        self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        for tok in self.instances_graph.objects(instance_uri, INST.hasToken):
            if tok != token_uri:
                status = self.instances_graph.value(tok, INST.status)
                if status and str(status) in ["ACTIVE", "WAITING"]:
                    self.instances_graph.set((tok, INST.status, Literal("CONSUMED")))

        self.instances_graph.set((instance_uri, INST.status, Literal("TERMINATED")))
        self.instances_graph.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        self._save_graph(self.instances_graph, "instances.ttl")

    def _execute_boundary_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ) -> None:
        """Execute a boundary event (error, compensation, timer, etc.)."""
        event_type = None
        error_ref = None
        compensate_ref = None

        for s, p, o in self.definitions_graph.triples((node_uri, RDF.type, None)):
            o_str = str(o)
            if "ErrorBoundaryEvent" in o_str:
                event_type = "error"
                error_ref = self.definitions_graph.value(node_uri, BPMN.errorRef)
                break
            elif "CompensationBoundaryEvent" in o_str:
                event_type = "compensation"
                compensate_ref = self.definitions_graph.value(
                    node_uri, BPMN.compensateRef
                )
                break
            elif "TimerBoundaryEvent" in o_str:
                event_type = "timer"
                break
            elif "MessageBoundaryEvent" in o_str:
                event_type = "message"
                break
            elif "SignalBoundaryEvent" in o_str:
                event_type = "signal"
                break

        if event_type == "error":
            self._execute_error_boundary_event(
                instance_uri, token_uri, node_uri, instance_id, error_ref
            )
        elif event_type == "compensation":
            self._execute_compensation_boundary_event(
                instance_uri, token_uri, node_uri, instance_id, compensate_ref
            )
        else:
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)

    def _execute_error_boundary_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        error_ref: URIRef,
    ) -> None:
        """Execute an error boundary event."""
        error_code = str(error_ref).split("/")[-1] if error_ref else None

        logger.info(
            f"Error boundary event reached at {node_uri} for instance {instance_id}, error: {error_code}"
        )

        interrupting = True
        interrupting_val = self.definitions_graph.value(node_uri, BPMN.interrupting)
        if interrupting_val:
            interrupting = str(interrupting_val).lower() == "true"

        self._log_instance_event(
            instance_uri,
            "ERROR_BOUNDARY_EVENT",
            "System",
            f"Error boundary event triggered at {str(node_uri)}"
            + (f", errorCode: {error_code}" if error_code else "")
            + f", interrupting: {interrupting}",
        )

        outgoing_targets = self.get_outgoing_flows_for_node(node_uri)
        if outgoing_targets:
            next_node = outgoing_targets[0]

            if interrupting:
                self.instances_graph.set((token_uri, INST.currentNode, next_node))
                self._log_instance_event(
                    instance_uri,
                    "BOUNDARY_ERROR_INTERRUPTED",
                    "System",
                    f"Activity interrupted by error boundary event",
                )
            else:
                boundary_token_uri = INST[
                    f"token_{instance_id}_{str(uuid.uuid4())[:8]}"
                ]
                self.instances_graph.add((boundary_token_uri, RDF.type, INST.Token))
                self.instances_graph.add(
                    (boundary_token_uri, INST.belongsTo, instance_uri)
                )
                self.instances_graph.add(
                    (boundary_token_uri, INST.status, Literal("ACTIVE"))
                )
                self.instances_graph.add(
                    (boundary_token_uri, INST.currentNode, next_node)
                )
                self.instances_graph.add(
                    (instance_uri, INST.hasToken, boundary_token_uri)
                )

            self._save_graph(self.instances_graph, "instances.ttl")
        else:
            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

    def _execute_compensation_boundary_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        compensate_ref: URIRef,
    ) -> None:
        """Execute a compensation boundary event."""
        compensate_ref_str = (
            str(compensate_ref).split("/")[-1] if compensate_ref else None
        )

        logger.info(
            f"Compensation boundary event reached at {node_uri} for instance {instance_id}, compensateRef: {compensate_ref_str}"
        )

        interrupting = True
        interrupting_val = self.definitions_graph.value(node_uri, BPMN.interrupting)
        if interrupting_val:
            interrupting = str(interrupting_val).lower() == "true"

        self._log_instance_event(
            instance_uri,
            "COMPENSATION_BOUNDARY_EVENT",
            "System",
            f"Compensation boundary event triggered at {str(node_uri)}"
            + (f", compensateRef: {compensate_ref_str}" if compensate_ref_str else ""),
        )

        parent_activity = None
        for parent in self.definitions_graph.objects(node_uri, BPMN.attachedTo):
            parent_activity = parent
            break

        if parent_activity:
            self._execute_compensation_for_activity(
                instance_uri, parent_activity, instance_id, compensate_ref_str
            )

        outgoing_targets = self.get_outgoing_flows_for_node(node_uri)
        if outgoing_targets:
            next_node = outgoing_targets[0]

            if not interrupting:
                boundary_token_uri = INST[
                    f"token_{instance_id}_{str(uuid.uuid4())[:8]}"
                ]
                self.instances_graph.add((boundary_token_uri, RDF.type, INST.Token))
                self.instances_graph.add(
                    (boundary_token_uri, INST.belongsTo, instance_uri)
                )
                self.instances_graph.add(
                    (boundary_token_uri, INST.status, Literal("ACTIVE"))
                )
                self.instances_graph.add(
                    (boundary_token_uri, INST.currentNode, next_node)
                )
                self.instances_graph.add(
                    (instance_uri, INST.hasToken, boundary_token_uri)
                )
                self._execute_token(instance_uri, boundary_token_uri, instance_id)

        self._save_graph(self.instances_graph, "instances.ttl")

    def _find_enclosing_transaction(
        self, instance_uri: URIRef, node_uri: URIRef
    ) -> URIRef:
        """Find the enclosing transaction subprocess for a node."""
        current = node_uri
        checked = set()

        while current and str(current) not in checked:
            checked.add(str(current))

            for s, p, o in self.definitions_graph.triples((current, RDF.type, None)):
                if "transaction" in str(o).lower():
                    return current

            parents = list(self.definitions_graph.objects(current, BPMN.hasParent))
            if parents:
                current = parents[0]
            else:
                break

        return None

    def _terminate_transaction_subprocess(
        self,
        instance_uri: URIRef,
        transaction_subprocess: URIRef,
        instance_id: str,
    ) -> None:
        """Terminate all tokens inside a transaction subprocess."""
        logger.info(
            f"Terminating transaction subprocess {transaction_subprocess} for instance {instance_id}"
        )

        self._log_instance_event(
            instance_uri,
            "TRANSACTION_TERMINATED",
            "System",
            f"Transaction subprocess {str(transaction_subprocess)} terminated",
        )

        for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
            current_node = self.instances_graph.value(token_uri, INST.currentNode)
            if current_node:
                is_inside = self._is_node_inside_subprocess(
                    current_node, transaction_subprocess
                )
                if is_inside:
                    status = self.instances_graph.value(token_uri, INST.status)
                    if status and str(status) in ["ACTIVE", "WAITING"]:
                        self.instances_graph.set(
                            (token_uri, INST.status, Literal("CONSUMED"))
                        )

    def _is_node_inside_subprocess(
        self, node_uri: URIRef, subprocess_uri: URIRef
    ) -> bool:
        """Check if a node is inside a subprocess."""
        if node_uri == subprocess_uri:
            return True

        for child in self.definitions_graph.subjects(BPMN.hasParent, subprocess_uri):
            if child == node_uri:
                return True
            if self._is_node_inside_subprocess(child, subprocess_uri):
                return True

        return False

    def _find_compensation_handler(self, node_uri: URIRef) -> URIRef:
        """Find the compensation handler for a compensation end event."""
        for handler in self.definitions_graph.subjects(
            RDF.type,
            URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#compensationHandler"),
        ):
            compensate_ref = self.definitions_graph.value(handler, BPMN.compensateRef)
            if compensate_ref == node_uri:
                return handler

        parent = self.definitions_graph.value(node_uri, BPMN.hasParent)
        if parent:
            return self._find_compensation_handler(parent)

        return None

    def _execute_compensation_handler(
        self,
        instance_uri: URIRef,
        handler_uri: URIRef,
        instance_id: str,
    ) -> None:
        """Execute a compensation handler subprocess."""
        logger.info(
            f"Executing compensation handler {handler_uri} for instance {instance_id}"
        )

        self._log_instance_event(
            instance_uri,
            "COMPENSATION_HANDLER_STARTED",
            "System",
            f"Compensation handler {str(handler_uri)} started",
        )

        for child_uri in self.definitions_graph.subjects(BPMN.hasParent, handler_uri):
            for s, p, o in self.definitions_graph.triples((child_uri, RDF.type, None)):
                if "intermediatethrowevent" in str(o).lower():
                    compensate_ref = self.definitions_graph.value(
                        child_uri, BPMN.compensateRef
                    )
                    if compensate_ref:
                        self._log_instance_event(
                            instance_uri,
                            "COMPENSATION_THROWN",
                            "System",
                            f"Compensation thrown for activity {str(compensate_ref)}",
                        )
                    break

        self._log_instance_event(
            instance_uri,
            "COMPENSATION_HANDLER_COMPLETED",
            "System",
            f"Compensation handler {str(handler_uri)} completed",
        )

    def _execute_compensation_for_activity(
        self,
        instance_uri: URIRef,
        activity_uri: URIRef,
        instance_id: str,
        compensate_ref: str,
    ) -> None:
        """Execute compensation for a specific activity."""
        logger.info(
            f"Executing compensation for activity {activity_uri} (compensateRef: {compensate_ref})"
        )

        self._log_instance_event(
            instance_uri,
            "COMPENSATION_STARTED",
            "System",
            f"Compensation started for activity {str(activity_uri)}",
        )

        compensation_handler = None
        for handler in self.definitions_graph.subjects(
            RDF.type,
            URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#compensationHandler"),
        ):
            handler_compensate_ref = self.definitions_graph.value(
                handler, BPMN.compensateRef
            )
            if handler_compensate_ref and str(handler_compensate_ref).endswith(
                compensate_ref
            ):
                compensation_handler = handler
                break

        if compensation_handler:
            self._execute_compensation_handler(
                instance_uri, compensation_handler, instance_id
            )

        self._log_instance_event(
            instance_uri,
            "COMPENSATION_COMPLETED",
            "System",
            f"Compensation completed for activity {str(activity_uri)}",
        )

    def throw_error(
        self, instance_id: str, error_code: str, error_message: str = None
    ) -> Dict[str, Any]:
        """Throw an error in a process instance (for API-based error injection).

        Args:
            instance_id: The process instance ID
            error_code: The error code to throw
            error_message: Optional error message

        Returns:
            Dictionary with status of the error throw
        """
        instance_uri = INST[instance_id]

        if not (instance_uri, RDF.type, INST.ProcessInstance) in self.instances_graph:
            raise ValueError(f"Instance {instance_id} not found")

        instance_status = self.instances_graph.value(instance_uri, INST.status)
        if instance_status and str(instance_status) not in ["RUNNING", "ACTIVE"]:
            raise ValueError(
                f"Cannot throw error in instance with status: {instance_status}"
            )

        logger.info(
            f"Throwing error {error_code} in instance {instance_id}: {error_message}"
        )

        self._log_instance_event(
            instance_uri,
            "ERROR_THROWN",
            "System",
            f"Error thrown via API: code={error_code}, message={error_message}",
        )

        self.set_instance_variable(instance_id, "lastErrorCode", error_code)
        if error_message:
            self.set_instance_variable(instance_id, "lastErrorMessage", error_message)

        found_error_boundary = False
        for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
            token_status = self.instances_graph.value(token_uri, INST.status)
            if not token_status or str(token_status) not in ["ACTIVE", "WAITING"]:
                continue

            current_node = self.instances_graph.value(token_uri, INST.currentNode)
            if not current_node:
                continue

            boundary_events = self.get_boundary_events_for_node(current_node)
            for event_info in boundary_events:
                if event_info["event_type"] == "error":
                    event_error_ref = self.definitions_graph.value(
                        URIRef(event_info["uri"]), BPMN.errorRef
                    )
                    event_error_code = (
                        str(event_error_ref).split("/")[-1] if event_error_ref else None
                    )

                    if event_error_code == error_code:
                        interrupting = event_info["is_interrupting"]
                        self.trigger_boundary_event(
                            token_uri,
                            instance_uri,
                            URIRef(event_info["uri"]),
                            instance_id,
                            interrupting,
                            {"errorCode": error_code, "errorMessage": error_message},
                        )
                        found_error_boundary = True
                        logger.info(
                            f"Error {error_code} caught by boundary event {event_info['uri']}"
                        )

        if found_error_boundary:
            self._execute_instance(instance_uri, instance_id)
            return {
                "status": "caught",
                "instance_id": instance_id,
                "error_code": error_code,
                "message": error_message,
                "caught_by_boundary_event": True,
            }
        else:
            self.instances_graph.set((instance_uri, INST.status, Literal("ERROR")))
            self.set_instance_variable(instance_id, "errorCode", error_code)
            self._save_graph(self.instances_graph, "instances.ttl")

            return {
                "status": "uncaught",
                "instance_id": instance_id,
                "error_code": error_code,
                "message": error_message,
                "caught_by_boundary_event": False,
            }

    def cancel_instance(self, instance_id: str, reason: str = None) -> Dict[str, Any]:
        """Cancel a process instance (external cancellation).

        Args:
            instance_id: The process instance ID
            reason: Optional cancellation reason

        Returns:
            Dictionary with updated instance state
        """
        instance_uri = INST[instance_id]

        if not (instance_uri, RDF.type, INST.ProcessInstance) in self.instances_graph:
            raise ValueError(f"Instance {instance_id} not found")

        current_status = self.instances_graph.value(instance_uri, INST.status)
        if current_status and str(current_status) in [
            "COMPLETED",
            "TERMINATED",
            "CANCELLED",
        ]:
            raise ValueError(f"Instance {instance_id} is already {current_status}")

        logger.info(f"Cancelling instance {instance_id}: {reason}")

        self._log_instance_event(
            instance_uri,
            "INSTANCE_CANCELLED",
            "System",
            f"Instance cancelled externally: {reason}",
        )

        for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
            status = self.instances_graph.value(token_uri, INST.status)
            if status and str(status) in ["ACTIVE", "WAITING"]:
                self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        self.instances_graph.set((instance_uri, INST.status, Literal("CANCELLED")))
        self.instances_graph.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        self._save_graph(self.instances_graph, "instances.ttl")

        return self.get_instance(instance_id)


# Global storage instance for sharing across modules
_shared_storage = None


def get_storage() -> RDFStorageService:
    """Get or create the shared storage service instance"""
    global _shared_storage
    if _shared_storage is None:
        _shared_storage = RDFStorageService()
    return _shared_storage
