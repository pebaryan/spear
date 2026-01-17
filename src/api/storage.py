# RDF Storage Service for SPEAR API
# Handles all process definitions and instances as RDF triples

import os
import uuid
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
        
        # Main graph for process definitions
        self.definitions_graph = Graph()
        self._load_graph("definitions.ttl")
        
        # Graph for process instances
        self.instances_graph = Graph()
        self._load_graph("instances.ttl")
        
        # Graph for audit logs
        self.audit_graph = Graph()
        self._load_graph("audit.ttl")
        
        # Graph for tasks
        self.tasks_graph = Graph()
        self._load_graph("tasks.ttl")
        
        # Topic registry for service task handlers
        self.topic_handlers = {}
        
        # BPMN converter for deployment
        self.converter = BPMNToRDFConverter()
        
        logger.info(f"Initialized RDF storage at {storage_path}")

    def _load_graph(self, filename: str):
        """Load a graph from file if it exists"""
        filepath = os.path.join(self.storage_path, filename)
        if os.path.exists(filepath):
            try:
                self.definitions_graph.parse(filepath, format="turtle")
                logger.info(f"Loaded graph from {filepath}")
            except Exception as e:
                logger.warning(f"Failed to load {filepath}: {e}")

    def _save_graph(self, graph: Graph, filename: str):
        """Save a graph to file"""
        filepath = os.path.join(self.storage_path, filename)
        graph.serialize(filepath, format="turtle")
        logger.debug(f"Saved graph to {filepath}")

    # ==================== Process Definition Operations ====================

    def deploy_process(self, name: str, description: Optional[str], 
                      bpmn_content: str, version: str = "1.0.0") -> str:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bpmn', delete=False) as tmp:
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
            self.definitions_graph.add((process_uri, META.deployedAt, 
                                       Literal(datetime.now().isoformat())))
            self.definitions_graph.add((process_uri, RDFS.comment, Literal(description or "")))
            
            # Add the BPMN triples to definitions graph
            for s, p, o in bpmn_graph:
                self.definitions_graph.add((s, p, o))
            
            # Link process to its BPMN elements
            for s, p, o in bpmn_graph.triples((None, RDF.type, None)):
                if "StartEvent" in str(o) or "Process" in str(o):
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
        if not (process_uri, RDF.type, PROC.ProcessDefinition) in self.definitions_graph:
            return None
        
        # Get metadata
        name = self.definitions_graph.value(process_uri, META.name)
        version = self.definitions_graph.value(process_uri, META.version)
        status = self.definitions_graph.value(process_uri, META.status)
        description = self.definitions_graph.value(process_uri, RDFS.comment)
        deployed_at = self.definitions_graph.value(process_uri, META.deployedAt)
        updated_at = self.definitions_graph.value(process_uri, META.updatedAt)
        
        # Count BPMN triples
        triples_count = len(list(self.definitions_graph.triples(
            (None, None, None))))
        
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
            "updated_at": updated_at or created_at
        }

    def list_processes(self, status: Optional[str] = None, 
                      page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """List all process definitions"""
        processes = []
        
        for process_uri in self.definitions_graph.subjects(
            RDF.type, PROC.ProcessDefinition):
            
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
            "page_size": page_size
        }

    def update_process(self, process_id: str, name: Optional[str] = None,
                      description: Optional[str] = None, 
                      status: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Update a process definition"""
        process_uri = PROC[process_id]
        
        if not (process_uri, RDF.type, PROC.ProcessDefinition) in self.definitions_graph:
            return None
        
        if name:
            self.definitions_graph.set((process_uri, META.name, Literal(name)))
        if description is not None:
            self.definitions_graph.set((process_uri, RDFS.comment, Literal(description)))
        if status:
            self.definitions_graph.set((process_uri, META.status, Literal(status)))
        
        self.definitions_graph.set((process_uri, META.updatedAt, 
                                   Literal(datetime.now().isoformat())))
        
        self._save_graph(self.definitions_graph, "definitions.ttl")
        
        return self.get_process(process_id)

    def delete_process(self, process_id: str) -> bool:
        """Delete a process definition"""
        process_uri = PROC[process_id]
        
        # Remove all triples about this process
        triples_to_remove = list(self.definitions_graph.triples((process_uri, None, None)))
        triples_to_remove += list(self.definitions_graph.triples((None, None, process_uri)))
        
        for s, p, o in triples_to_remove:
            self.definitions_graph.remove((s, p, o))
        
        self._save_graph(self.definitions_graph, "definitions.ttl")
        
        logger.info(f"Deleted process: {process_id}")
        return True

    def get_process_graph(self, process_id: str) -> Optional[Graph]:
        """Get the RDF graph for a specific process"""
        process_uri = PROC[process_id]
        
        if not (process_uri, RDF.type, PROC.ProcessDefinition) in self.definitions_graph:
            return None
        
        # Extract process-specific triples
        process_graph = Graph()
        for s, p, o in self.definitions_graph:
            # Include if subject or object is part of this process
            if str(s).startswith(str(process_uri)) or str(s).startswith("http://example.org/bpmn/"):
                process_graph.add((s, p, o))
            if str(o).startswith(str(process_uri)) or str(o).startswith("http://example.org/bpmn/"):
                process_graph.add((s, p, o))
        
        return process_graph

    # ==================== Process Instance Operations ====================

    def create_instance(self, process_id: str, variables: Optional[Dict[str, Any]] = None,
                       start_event_id: Optional[str] = None) -> Dict[str, Any]:
        """Create and start a new process instance"""
        process_uri = PROC[process_id]
        
        if not (process_uri, RDF.type, PROC.ProcessDefinition) in self.definitions_graph:
            raise ValueError(f"Process {process_id} not found")
        
        instance_id = str(uuid.uuid4())
        instance_uri = INST[instance_id]
        
        # Create instance metadata
        self.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        self.instances_graph.add((instance_uri, INST.processDefinition, process_uri))
        self.instances_graph.add((instance_uri, INST.status, Literal("RUNNING")))
        self.instances_graph.add((instance_uri, INST.createdAt,
                                  Literal(datetime.now().isoformat())))
        
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
            # Find first start event (check both StartEvent and startEvent)
            for s, p, o in self.definitions_graph.triples(
                (None, RDF.type, BPMN.StartEvent)):
                start_event_uri = s
                break
            if not start_event_uri:
                for s, p, o in self.definitions_graph.triples(
                    (None, RDF.type, BPMN.startEvent)):
                    start_event_uri = s
                    break
        
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
            "variables": variables or {}
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
            "updated_at": str(updated_at) if updated_at else None
        }

    def list_instances(self, process_id: Optional[str] = None,
                      status: Optional[str] = None,
                      page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """List process instances"""
        instances = []
        
        for instance_uri in self.instances_graph.subjects(
            RDF.type, INST.ProcessInstance):
            
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
            "page_size": page_size
        }

    def stop_instance(self, instance_id: str, reason: str = "User request") -> Dict[str, Any]:
        """Stop a running process instance"""
        instance_uri = INST[instance_id]
        
        if not (instance_uri, RDF.type, INST.ProcessInstance) in self.instances_graph:
            raise ValueError(f"Instance {instance_id} not found")
        
        # Update status
        self.instances_graph.set((instance_uri, INST.status, Literal("TERMINATED")))
        self.instances_graph.set((instance_uri, INST.updatedAt,
                                  Literal(datetime.now().isoformat())))
        
        # Log termination
        self._log_instance_event(instance_uri, "TERMINATED", "System", reason)
        
        self._save_graph(self.instances_graph, "instances.ttl")
        
        logger.info(f"Stopped instance {instance_id}: {reason}")
        
        return self.get_instance(instance_id)

    def set_instance_variable(self, instance_id: str, name: str, value: Any) -> bool:
        """Set a variable on a process instance"""
        instance_uri = INST[instance_id]
        
        # Find existing variable
        var_uri = None
        for v in self.instances_graph.objects(instance_uri, INST.hasVariable):
            if self.instances_graph.value(v, VAR.name) == Literal(name):
                var_uri = v
                break
        
        if var_uri:
            # Update existing variable
            self.instances_graph.set((var_uri, VAR.value, Literal(str(value))))
        else:
            # Create new variable
            var_uri = VAR[f"{instance_id}_{name}"]
            self.instances_graph.add((instance_uri, INST.hasVariable, var_uri))
            self.instances_graph.add((var_uri, VAR.name, Literal(name)))
            self.instances_graph.add((var_uri, VAR.value, Literal(str(value))))
        
        self._save_graph(self.instances_graph, "instances.ttl")
        
        return True

    def get_instance_variables(self, instance_id: str) -> Dict[str, Any]:
        """Get all variables for a process instance"""
        instance_data = self.get_instance(instance_id)
        return instance_data.get("variables", {}) if instance_data else {}

    # ==================== Audit Log Operations ====================

    def _log_instance_event(self, instance_uri: URIRef, event_type: str, 
                           user: str, details: str = ""):
        """Log an event for an instance"""
        event_uri = LOG[f"event_{str(uuid.uuid4())}"]
        
        self.audit_graph.add((event_uri, RDF.type, LOG.Event))
        self.audit_graph.add((event_uri, LOG.instance, instance_uri))
        self.audit_graph.add((event_uri, LOG.eventType, Literal(event_type)))
        self.audit_graph.add((event_uri, LOG.user, Literal(user)))
        self.audit_graph.add((event_uri, LOG.timestamp,
                             Literal(datetime.now().isoformat())))
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
            
            events.append({
                "type": str(event_type) if event_type else "",
                "user": str(user) if user else "",
                "timestamp": str(timestamp) if timestamp else "",
                "details": str(details) if details else ""
            })
        
        return sorted(events, key=lambda x: x["timestamp"])

    # ==================== Instance Execution ====================

    def _execute_instance(self, instance_uri: URIRef, instance_id: str):
        """Execute a process instance by processing all tokens"""
        while True:
            # Get all active tokens
            active_tokens = []
            for token_uri in self.instances_graph.objects(instance_uri, INST.hasToken):
                token_status = self.instances_graph.value(token_uri, INST.status)
                if token_status and str(token_status) == "ACTIVE":
                    active_tokens.append(token_uri)

            if not active_tokens:
                break

            # Execute each active token
            for token_uri in active_tokens:
                self._execute_token(instance_uri, token_uri, instance_id)

            # Check if instance completed
            if self._is_instance_completed(instance_uri):
                self.instances_graph.set((instance_uri, INST.status, Literal("COMPLETED")))
                self.instances_graph.set((instance_uri, INST.updatedAt,
                                          Literal(datetime.now().isoformat())))
                self._log_instance_event(instance_uri, "COMPLETED", "System")
                self._save_graph(self.instances_graph, "instances.ttl")
                break

    def _execute_token(self, instance_uri: URIRef, token_uri: URIRef, instance_id: str):
        """Execute a single token through the process"""
        current_node = self.instances_graph.value(token_uri, INST.currentNode)
        if not current_node:
            return

        # Get node type
        node_type = None
        for s, p, o in self.definitions_graph.triples((current_node, RDF.type, None)):
            node_type = o
            break

        logger.debug(f"Executing token at {current_node}, type: {node_type}")
        
        if node_type == BPMN.StartEvent:
            self._log_instance_event(instance_uri, "START", "System", str(current_node))
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)

        elif node_type == BPMN.EndEvent:
            self._log_instance_event(instance_uri, "END", "System", str(current_node))
            self.instances_graph.set((token_uri, INST.status, Literal("CONSUMED")))

        elif node_type == BPMN.ServiceTask or node_type == BPMN.serviceTask:
            self._execute_service_task(instance_uri, token_uri, current_node, instance_id)

        elif node_type == BPMN.UserTask or node_type == BPMN.userTask:
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
                candidate_groups=candidate_groups if candidate_groups else None
            )
            
            self._log_instance_event(instance_uri, "USER_TASK", "System",
                                     f"{str(current_node)} (task: {task['id']})")
            self.instances_graph.set((token_uri, INST.status, Literal("WAITING")))

        elif node_type == BPMN.ExclusiveGateway or node_type == BPMN.ParallelGateway:
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)

        else:
            # For other node types, just move to next node
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)

        self._save_graph(self.instances_graph, "instances.ttl")

    def _execute_service_task(self, instance_uri: URIRef, token_uri: URIRef,
                              node_uri: URIRef, instance_id: str):
        """Execute a service task and move token to next node"""
        # Get topic from node
        topic = None
        for s, p, o in self.definitions_graph.triples((node_uri, BPMN.topic, None)):
            topic = str(o)
            break
        # Also check camunda:topic
        if not topic:
            for s, p, o in self.definitions_graph.triples((node_uri, URIRef("http://camunda.org/schema/1.0/bpmn#topic"), None)):
                topic = str(o)
                break
        
        if not topic:
            # No topic, just move to next node
            self._log_instance_event(instance_uri, "SERVICE_TASK", "System", 
                                     f"{str(node_uri)} (no topic configured)")
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)
            return
        
        # Get current variables
        variables = {}
        for var_uri in self.instances_graph.objects(instance_uri, INST.hasVariable):
            name = self.instances_graph.value(var_uri, VAR.name)
            value = self.instances_graph.value(var_uri, VAR.value)
            if name and value:
                variables[str(name)] = str(value)
        
        try:
            # Execute the handler
            updated_variables = self.execute_service_task(instance_id, topic, variables)
            
            # Update variables
            for name, value in updated_variables.items():
                self.set_instance_variable(instance_id, name, value)
            
            # Log completion
            self._log_instance_event(instance_uri, "SERVICE_TASK", "System",
                                     f"{str(node_uri)} (topic: {topic})")
            
            # Move to next node
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)
            
        except ValueError as e:
            # No handler registered - log warning and continue
            logger.warning(str(e))
            self._log_instance_event(instance_uri, "SERVICE_TASK_SKIPPED", "System",
                                     f"{str(node_uri)} (topic: {topic}) - no handler")
            self._move_token_to_next_node(instance_uri, token_uri, instance_id)
            
        except Exception as e:
            # Handler failed - set token to error state
            logger.error(f"Service task failed: {e}")
            self.instances_graph.set((token_uri, INST.status, Literal("ERROR")))
            self._log_instance_event(instance_uri, "SERVICE_TASK_ERROR", "System",
                                     f"{str(node_uri)} (topic: {topic}): {str(e)}")

    def _move_token_to_next_node(self, instance_uri: URIRef, token_uri: URIRef, instance_id: str):
        """Move token to the next node via sequence flows"""
        current_node = self.instances_graph.value(token_uri, INST.currentNode)
        if not current_node:
            return

        # Find outgoing sequence flows and their targets
        next_nodes = []
        for s, p, o in self.definitions_graph.triples((current_node, BPMN.outgoing, None)):
            # o is the sequence flow URI, find its target
            for ss, pp, target in self.definitions_graph.triples((o, BPMN.targetRef, None)):
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
                self.instances_graph.add((new_token_uri, INST.status, Literal("ACTIVE")))
                self.instances_graph.add((new_token_uri, INST.currentNode, additional_target))
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

    # ==================== Task Management ====================

    def create_task(self, instance_id: str, node_uri: str, name: str = "User Task",
                   assignee: Optional[str] = None, candidate_users: Optional[List[str]] = None,
                   candidate_groups: Optional[List[str]] = None,
                   form_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        self.tasks_graph.add((task_uri, TASK.createdAt, Literal(datetime.now().isoformat())))
        
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
        
        candidate_users = [str(u) for u in self.tasks_graph.objects(task_uri, TASK.candidateUser)]
        candidate_groups = [str(g) for g in self.tasks_graph.objects(task_uri, TASK.candidateGroup)]
        
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
            "completed_at": str(completed_at) if completed_at else None
        }

    def list_tasks(self, instance_id: Optional[str] = None,
                  status: Optional[str] = None,
                  assignee: Optional[str] = None,
                  page: int = 1, page_size: int = 20) -> Dict[str, Any]:
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
        
        return {
            "tasks": tasks,
            "total": total,
            "page": page,
            "page_size": page_size
        }

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
            candidate_users = [str(u) for u in self.tasks_graph.objects(task_uri, TASK.candidateUser)]
            if user_id not in candidate_users:
                raise ValueError(f"User {user_id} is not authorized to claim task {task_id}")
        
        self.tasks_graph.set((task_uri, TASK.assignee, Literal(user_id)))
        self.tasks_graph.set((task_uri, TASK.status, Literal("CLAIMED")))
        self.tasks_graph.set((task_uri, TASK.claimedAt, Literal(datetime.now().isoformat())))
        
        self._log_task_event(task_uri, "CLAIMED", user_id)
        self._save_graph(self.tasks_graph, "tasks.ttl")
        
        logger.info(f"Task {task_id} claimed by user {user_id}")
        
        return self.get_task(task_id)

    def complete_task(self, task_id: str, user_id: str,
                     variables: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Complete a task"""
        task_uri = TASK[task_id]
        
        if not (task_uri, RDF.type, TASK.UserTask) in self.tasks_graph:
            return None
        
        status = self.tasks_graph.value(task_uri, TASK.status)
        if status and str(status) not in ["CREATED", "CLAIMED"]:
            raise ValueError(f"Task {task_id} cannot be completed (status: {status})")
        
        assignee = self.tasks_graph.value(task_uri, TASK.assignee)
        if assignee and str(assignee) != user_id:
            raise ValueError(f"User {user_id} cannot complete task {task_id} (assigned to {assignee})")
        
        self.tasks_graph.set((task_uri, TASK.status, Literal("COMPLETED")))
        self.tasks_graph.set((task_uri, TASK.completedAt, Literal(datetime.now().isoformat())))
        
        if variables:
            instance_uri = self.tasks_graph.value(task_uri, TASK.instance)
            instance_id = str(instance_uri).split("/")[-1]
            for name, value in variables.items():
                self.set_instance_variable(instance_id, name, value)
        
        self._log_task_event(task_uri, "COMPLETED", user_id)
        self._save_graph(self.tasks_graph, "tasks.ttl")
        
        logger.info(f"Task {task_id} completed by user {user_id}")
        
        return self.get_task(task_id)

    def assign_task(self, task_id: str, assignee: str, assigner: str = "System") -> Optional[Dict[str, Any]]:
        """Assign a task to a user"""
        task_uri = TASK[task_id]
        
        if not (task_uri, RDF.type, TASK.UserTask) in self.tasks_graph:
            return None
        
        old_assignee = self.tasks_graph.value(task_uri, TASK.assignee)
        
        self.tasks_graph.set((task_uri, TASK.assignee, Literal(assignee)))
        self.tasks_graph.set((task_uri, TASK.status, Literal("ASSIGNED")))
        
        self._log_task_event(task_uri, "ASSIGNED", assigner, f"Assigned from {old_assignee} to {assignee}")
        self._save_graph(self.tasks_graph, "tasks.ttl")
        
        logger.info(f"Task {task_id} assigned to {assignee}")
        
        return self.get_task(task_id)

    def _log_task_event(self, task_uri: URIRef, event_type: str, user: str, details: str = ""):
        """Log a task event"""
        event_uri = LOG[f"task_event_{str(uuid.uuid4())}"]
        
        self.audit_graph.add((event_uri, RDF.type, LOG.Event))
        self.audit_graph.add((event_uri, LOG.task, task_uri))
        self.audit_graph.add((event_uri, LOG.eventType, Literal(event_type)))
        self.audit_graph.add((event_uri, LOG.user, Literal(user)))
        self.audit_graph.add((event_uri, LOG.timestamp, Literal(datetime.now().isoformat())))
        if details:
            self.audit_graph.add((event_uri, LOG.details, Literal(details)))
        
        self._save_graph(self.audit_graph, "audit.ttl")

    def get_task_for_instance_node(self, instance_id: str, node_uri: str) -> Optional[Dict[str, Any]]:
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
        process_count = len(list(self.definitions_graph.subjects(
            RDF.type, PROC.ProcessDefinition)))
        
        # Count instances
        instance_count = len(list(self.instances_graph.subjects(
            RDF.type, INST.ProcessInstance)))
        
        # Count RDF triples
        triple_count = (len(self.definitions_graph) + 
                       len(self.instances_graph) + 
                       len(self.audit_graph))
        
        return {
            "process_count": process_count,
            "instance_count": instance_count,
            "total_triples": triple_count
        }

    # ==================== Service Task Handlers ====================

    def register_topic_handler(self, topic: str, handler_function: callable,
                              description: str = "",
                              async_execution: bool = False,
                              handler_type: str = "function",
                              http_config: Dict = None) -> bool:
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
            "http_config": http_config
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
                "http_config": info.get("http_config")
            }
        return topics

    def execute_service_task(self, instance_id: str, topic: str, 
                            variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a service task handler.
        
        Args:
            instance_id: The process instance ID
            topic: The topic to execute
            variables: Current process variables
            
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
            # Execute the handler
            if handler_info["async"]:
                # For async execution, we would queue the task
                # For now, still execute synchronously
                updated_variables = handler_function(instance_id, variables)
            else:
                updated_variables = handler_function(instance_id, variables)
            
            logger.info(f"Service task {topic} completed for instance {instance_id}")
            return updated_variables
            
        except Exception as e:
            logger.error(f"Service task {topic} failed for instance {instance_id}: {e}")
            raise


# Global storage instance for sharing across modules
_shared_storage = None


def get_storage() -> RDFStorageService:
    """Get or create the shared storage service instance"""
    global _shared_storage
    if _shared_storage is None:
        _shared_storage = RDFStorageService()
    return _shared_storage
