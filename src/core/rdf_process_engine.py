from rdflib import Graph, Namespace, RDF, Literal, XSD, URIRef, BNode
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from datetime import datetime
from typing import Dict, List, Any
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RDF Namespaces (must match bpmn2rdf.py)
BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
INST = Namespace("http://example.org/instance/")
VAR = Namespace("http://example.org/variables/")
LOG = Namespace("http://example.org/audit/")
TOKEN = Namespace("http://example.org/token/")

# Error Event Type URIs (for error handling support)
BPMN_CANCEL_END_EVENT = URIRef(BPMN + "cancelEndEvent")
BPMN_ERROR_THROW_EVENT = URIRef(BPMN + "intermediateThrowEvent")
BPMN_COMPENSATION_END_EVENT = URIRef(BPMN + "compensationEndEvent")
BPMN_COMPENSATION_THROW_EVENT = URIRef(BPMN + "compensationIntermediateThrowEvent")
BPMN_COMPENSATION_CATCH_EVENT = URIRef(BPMN + "compensationIntermediateCatchEvent")

# Compensation Relationships
COMPENSATE_REF = URIRef(BPMN + "compensateRef")
COMPENSATION_HANDLER = URIRef(BPMN + "compensationHandler")

# Error References
ERROR_REF = URIRef(BPMN + "errorRef")

# Event Definitions
CANCEL_EVENT_DEFINITION = URIRef(BPMN + "cancelEventDefinition")
COMPENSATION_EVENT_DEFINITION = URIRef(BPMN + "compensationEventDefinition")

# Listener Type URIs (for Camunda listener support)
BPMN_EXECUTION_LISTENER = URIRef(BPMN + "executionListener")
BPMN_TASK_LISTENER = URIRef(BPMN + "taskListener")

# Listener Properties
LISTENER_EXPRESSION = URIRef(BPMN + "listenerExpression")
LISTENER_EVENT = URIRef(BPMN + "listenerEvent")
LISTENER_ELEMENT = URIRef(BPMN + "listenerElement")

# Import ProcessContext from existing rdfengine.py
from .rdfengine import ProcessContext


class ProcessInstance:
    """Represents a running process instance"""

    def __init__(self, process_definition_uri, instance_id=None):
        self.instance_id = instance_id or str(uuid.uuid4())
        self.instance_uri = INST[self.instance_id]
        self.process_definition_uri = URIRef(process_definition_uri)
        self.status = "CREATED"  # CREATED, RUNNING, SUSPENDED, COMPLETED, TERMINATED
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.tokens = []

    def to_dict(self):
        return {
            "instance_id": self.instance_id,
            "instance_uri": str(self.instance_uri),
            "process_definition_uri": str(self.process_definition_uri),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "token_count": len(self.tokens),
        }


class Token:
    """Represents a token in the process execution"""

    def __init__(self, token_id=None):
        self.token_id = token_id or str(uuid.uuid4())
        self.token_uri = TOKEN[self.token_id]
        self.current_node = None
        self.status = "ACTIVE"  # ACTIVE, WAITING, CONSUMED

    def move_to_node(self, node_uri):
        """Move token to a new node"""
        self.current_node = node_uri
        self.status = "ACTIVE"


class RDFProcessEngine:
    """
    RDF-based BPMN Process Engine for managing process instances
    """

    def __init__(self, definition_graph, instance_graph=None):
        """
        Initialize the process engine

        Args:
            definition_graph: RDF graph containing process definitions
            instance_graph: RDF graph for storing instance state (optional)
        """
        self.definition_graph = definition_graph
        self.instance_graph = instance_graph or definition_graph
        self.instances = {}
        self.topics = {}
        self.uri_base = (
            "http://example.org/bpmn/"  # For instance URIs, not BPMN element URIs
        )

    def register_topic_handler(self, topic, handler):
        """Register a handler function for a service task topic"""
        self.topics[topic] = handler

    def start_process_instance(
        self, process_definition_uri, initial_variables=None, start_event_id=None
    ):
        """
        Start a new process instance

        Args:
            process_definition_uri: URI of the process definition to start
            initial_variables: Dictionary of initial process variables
            start_event_id: Specific start event ID (optional)

        Returns:
            ProcessInstance: The created and started process instance
        """

        # Create new instance
        instance = ProcessInstance(process_definition_uri)
        self.instances[instance.instance_id] = instance

        # Set initial variables
        if initial_variables:
            context = ProcessContext(self.instance_graph, instance.instance_uri)
            for name, value in initial_variables.items():
                context.set_variable(name, value)

        # Find start event(s)
        start_events = self._find_start_events(process_definition_uri, start_event_id)
        if not start_events:
            raise ValueError(
                f"No start events found in process {process_definition_uri}"
            )

        # Create tokens at start events
        for start_event_uri in start_events:
            token = Token()
            token.move_to_node(start_event_uri)
            instance.tokens.append(token)

            # Log instance start
            if start_event_uri:
                self._log_event(
                    instance.instance_uri, start_event_uri, "START", "System"
                )

        # Change status to running
        instance.status = "RUNNING"
        instance.updated_at = datetime.now()

        # Persist instance state
        self._persist_instance_state(instance)

        # Start execution
        self._execute_instance(instance)

        logger.info(
            f"Started process instance {instance.instance_id} for process {process_definition_uri}"
        )
        return instance

    def stop_process_instance(self, instance_id, reason="User request"):
        """
        Stop a running process instance

        Args:
            instance_id: ID of the instance to stop
            reason: Reason for stopping the instance

        Returns:
            bool: True if successfully stopped, False otherwise
        """

        if instance_id not in self.instances:
            logger.warning(f"Instance {instance_id} not found")
            return False

        instance = self.instances[instance_id]

        if instance.status in ["COMPLETED", "TERMINATED"]:
            logger.warning(f"Instance {instance_id} is already {instance.status}")
            return False

        # Change status to terminated
        instance.status = "TERMINATED"
        instance.updated_at = datetime.now()

        # Clean up tokens
        for token in instance.tokens:
            if token.status == "ACTIVE":
                token.status = "CONSUMED"
                # Log token consumption
                if token.current_node:
                    self._log_event(
                        instance.instance_uri,
                        token.current_node,
                        "TERMINATE",
                        "System",
                        reason,
                    )

        # Cancel any scheduled activities (timers, etc.)
        self._cancel_scheduled_activities(instance)

        # Persist final state
        self._persist_instance_state(instance)

        logger.info(f"Stopped process instance {instance_id}: {reason}")
        return True

    def get_instance_status(self, instance_id):
        """Get the current status of a process instance"""
        if instance_id not in self.instances:
            return None
        return self.instances[instance_id].to_dict()

    def list_instances(self, process_definition_uri=None, status=None):
        """List process instances with optional filtering"""
        instances = []
        for instance in self.instances.values():
            if (
                process_definition_uri
                and str(instance.process_definition_uri) != process_definition_uri
            ):
                continue
            if status and instance.status != status:
                continue
            instances.append(instance.to_dict())
        return instances

    def _find_start_events(self, process_definition_uri, start_event_id=None):
        """Find start events in a process definition"""

        if start_event_id:
            # Find specific start event
            start_event_uri = URIRef(f"http://example.org/bpmn/{start_event_id}")
            if (start_event_uri, RDF.type, BPMN.StartEvent) in self.definition_graph:
                return [start_event_uri]
            else:
                raise ValueError(f"Start event {start_event_id} not found")

        # Find all start events (simplified - just find all StartEvent instances)
        start_events = []
        for s, p, o in self.definition_graph.triples((None, RDF.type, BPMN.StartEvent)):
            start_events.append(s)

        return start_events

    def _execute_instance(self, instance):
        """Execute a process instance by processing active tokens"""

        while any(token.status == "ACTIVE" for token in instance.tokens):
            active_tokens = [t for t in instance.tokens if t.status == "ACTIVE"]

            for token in active_tokens:
                self._execute_token(instance, token)

                # Check if instance completed
                if self._is_instance_completed(instance):
                    instance.status = "COMPLETED"
                    instance.updated_at = datetime.now()
                    self._persist_instance_state(instance)
                    break

            # Break if instance completed
            if instance.status == "COMPLETED":
                break

    def _execute_token(self, instance, token):
        """Execute a single token"""

        if not token.current_node:
            return

        # Determine node type
        node_type = self.definition_graph.value(token.current_node, RDF.type)

        if node_type == BPMN.StartEvent:
            self._execute_start_event(instance, token)
        elif node_type == BPMN.EndEvent:
            self._execute_end_event(instance, token)
        elif node_type == BPMN.ServiceTask:
            self._execute_service_task(instance, token)
        elif node_type == BPMN.UserTask:
            self._execute_user_task(instance, token)
        elif node_type == BPMN.ExclusiveGateway:
            self._execute_gateway(instance, token)
        elif node_type == BPMN.ParallelGateway:
            self._execute_gateway(instance, token)
        else:
            # Move to next node for unsupported types
            self._move_token_to_next_node(instance, token)

    def _execute_start_event(self, instance, token):
        """Execute a start event"""
        logger.info(f"Executing start event for instance {instance.instance_id}")
        self._move_token_to_next_node(instance, token)

    def _execute_end_event(self, instance, token):
        """Execute an end event"""
        logger.info(f"Executing end event for instance {instance.instance_id}")
        token.status = "CONSUMED"
        if token.current_node:
            self._log_event(instance.instance_uri, token.current_node, "END", "System")

    def _execute_service_task(self, instance, token):
        """Execute a service task"""
        topic = str(self.definition_graph.value(token.current_node, BPMN.topic))

        if topic in self.topics:
            try:
                context = ProcessContext(self.instance_graph, instance.instance_uri)
                self.topics[topic](context)
                if token.current_node:
                    self._log_event(
                        instance.instance_uri, token.current_node, "COMPLETE", "System"
                    )
                self._move_token_to_next_node(instance, token)
            except Exception as e:
                logger.error(f"Service task {topic} failed: {e}")
                # Could implement error handling here
                token.status = "WAITING"  # Wait for manual intervention
        else:
            logger.warning(f"No handler registered for topic: {topic}")
            token.status = "WAITING"

    def _execute_user_task(self, instance, token):
        """Execute a user task"""
        logger.info(f"User task reached for instance {instance.instance_id}")
        # In a real implementation, this would assign to users/groups
        # For now, just mark as waiting
        token.status = "WAITING"

    def _execute_gateway(self, instance, token):
        """Execute a gateway"""
        node_type = self.definition_graph.value(token.current_node, RDF.type)
        if node_type == BPMN.ExclusiveGateway:
            self._execute_exclusive_gateway(instance, token)
            return

        # Parallel or other gateways: move to all outgoing
        self._move_token_to_next_node(instance, token)

    def _execute_exclusive_gateway(self, instance, token):
        """Execute an exclusive gateway with condition evaluation."""
        gateway = token.current_node
        default_flow = self.definition_graph.value(gateway, BPMN.default)

        query = f"""
        SELECT ?flow ?target ?conditionQuery WHERE {{
            <{gateway}> bpmn:outgoing ?flow .
            ?flow bpmn:targetRef ?target .
            OPTIONAL {{ ?flow bpmn:conditionQuery ?conditionQuery . }}
        }}
        """
        results = list(self.definition_graph.query(query))

        chosen_target = None
        for flow, target, condition_query in results:
            if condition_query:
                try:
                    ask = self.instance_graph.query(
                        str(condition_query),
                        initBindings={"instance": instance.instance_uri},
                        initNs={"var": VAR},
                    )
                    if bool(ask.askAnswer):
                        chosen_target = URIRef(target)
                        break
                except Exception as e:
                    logger.warning(f"Condition query failed: {e}")
                    continue
            elif default_flow and flow == default_flow:
                chosen_target = URIRef(target)

        if chosen_target is None:
            # If no condition matched, fall back to default flow or first flow.
            if default_flow:
                for flow, target, _ in results:
                    if flow == default_flow:
                        chosen_target = URIRef(target)
                        break
            if chosen_target is None and results:
                chosen_target = URIRef(results[0][1])

        if chosen_target:
            token.move_to_node(chosen_target)
        else:
            token.status = "CONSUMED"

    def _move_token_to_next_node(self, instance, token):
        """Move token to the next node in the sequence"""

        # Find outgoing sequence flows
        query = f"""
        SELECT ?next WHERE {{
            <{token.current_node}> bpmn:outgoing ?flow .
            ?flow bpmn:targetRef ?next .
        }}
        """

        results = list(self.definition_graph.query(query))

        if len(results) == 1:
            # Single outgoing flow
            next_node = URIRef(results[0][0])
            token.move_to_node(next_node)
        elif len(results) > 1:
            # Multiple outgoing flows - create new tokens for each
            for row in results[1:]:  # Skip first, reuse current token
                new_token = Token()
                new_token.move_to_node(URIRef(row[0]))
                instance.tokens.append(new_token)
            # Move current token to first target
            token.move_to_node(URIRef(results[0][0]))
        else:
            # No outgoing flows - consume token
            token.status = "CONSUMED"

    def _is_instance_completed(self, instance):
        """Check if a process instance has completed"""
        return all(token.status == "CONSUMED" for token in instance.tokens)

    def _persist_instance_state(self, instance):
        """Persist instance state to RDF graph"""
        # This is a simplified implementation
        # In a real system, you'd want more sophisticated persistence

        instance_uri = instance.instance_uri

        # Remove old instance metadata, preserve variables and external links
        for _, pred, _ in list(self.instance_graph.triples((instance_uri, None, None))):
            if str(pred).startswith(str(INST)):
                self.instance_graph.remove((instance_uri, pred, None))

        # Add current state
        self.instance_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        self.instance_graph.add((instance_uri, INST.status, Literal(instance.status)))
        self.instance_graph.add(
            (instance_uri, INST.processDefinition, instance.process_definition_uri)
        )
        self.instance_graph.add(
            (
                instance_uri,
                INST.createdAt,
                Literal(instance.created_at.isoformat(), datatype=XSD.dateTime),
            )
        )
        self.instance_graph.add(
            (
                instance_uri,
                INST.updatedAt,
                Literal(instance.updated_at.isoformat(), datatype=XSD.dateTime),
            )
        )

    def _log_event(self, instance_uri, node_uri, event_type, user, details=""):
        """Log an audit event"""
        event_uri = LOG[f"event_{str(uuid.uuid4())}"]

        self.instance_graph.add((event_uri, RDF.type, LOG.Event))
        self.instance_graph.add((event_uri, LOG.instance, instance_uri))
        if node_uri:
            self.instance_graph.add((event_uri, LOG.node, node_uri))
        self.instance_graph.add((event_uri, LOG.eventType, Literal(event_type)))
        self.instance_graph.add(
            (
                event_uri,
                LOG.timestamp,
                Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
            )
        )
        self.instance_graph.add((event_uri, LOG.user, Literal(user)))
        if details:
            self.instance_graph.add((event_uri, LOG.details, Literal(details)))

    def _cancel_scheduled_activities(self, instance):
        """Cancel any scheduled activities for an instance"""
        # This would cancel timers, scheduled tasks, etc.
        # Implementation depends on your scheduling system
        pass
