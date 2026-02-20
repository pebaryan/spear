# Execution Engine for SPEAR Engine
# Orchestrates process instance execution

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Callable, TYPE_CHECKING

from rdflib import URIRef, Literal, RDF, RDFS, Graph

from src.api.storage.base import BPMN, INST

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Orchestrates the execution of BPMN process instances.

    This is the main execution loop that:
    - Processes active tokens through the process graph
    - Delegates to specialized handlers for different node types
    - Manages instance lifecycle (running, completed, error)
    - Handles gateway merging and forking
    """

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
    ):
        """
        Initialize the execution engine.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
        """
        self._definitions = definitions_graph
        self._instances = instances_graph

    # ==================== Main Execution Loop ====================

    def execute_instance(
        self,
        instance_uri: URIRef,
        instance_id: str,
        node_executor: Callable,
        save_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a process instance by processing all active tokens.

        Args:
            instance_uri: URI of the process instance
            instance_id: ID of the instance
            node_executor: Callback to execute a single token/node
            save_callback: Optional callback to save graph changes
            log_callback: Optional callback for logging events
        """
        while True:
            # Find all active tokens
            active_tokens = self.get_active_tokens(instance_uri)

            if not active_tokens:
                break

            # Track merged gateways to avoid double-processing
            merged_gateways: Set[URIRef] = set()

            # Execute each active token
            for token_uri in active_tokens:
                node_executor(instance_uri, token_uri, instance_id, merged_gateways)

            if save_callback:
                save_callback()

        # Check if instance is completed
        if self.is_instance_completed(instance_uri):
            self._instances.set((instance_uri, INST.status, Literal("COMPLETED")))
            self._instances.set(
                (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
            )

            if log_callback:
                log_callback(instance_uri, "COMPLETED", "System", "")

            if save_callback:
                save_callback()

    def get_active_tokens(self, instance_uri: URIRef) -> List[URIRef]:
        """Get all active tokens for an instance."""
        active_tokens = []
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            token_status = self._instances.value(token_uri, INST.status)
            if token_status and str(token_status) == "ACTIVE":
                active_tokens.append(token_uri)
        return active_tokens

    def is_instance_completed(self, instance_uri: URIRef) -> bool:
        """Check if all tokens in an instance are consumed."""
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            status = self._instances.value(token_uri, INST.status)
            if not status or str(status) != "CONSUMED":
                return False
        return True

    # ==================== Token Execution ====================

    def execute_token(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        instance_id: str,
        merged_gateways: Optional[Set[URIRef]] = None,
        handlers: Optional[Dict[str, Callable]] = None,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a single token through the process.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token to execute
            instance_id: ID of the instance
            merged_gateways: Set of gateways already merged in this iteration
            handlers: Dictionary of node type handlers
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes
        """
        if merged_gateways is None:
            merged_gateways = set()

        if handlers is None:
            handlers = {}

        current_node = self._instances.value(token_uri, INST.currentNode)
        if not current_node:
            self._instances.set((token_uri, INST.status, Literal("ERROR")))
            if log_callback:
                log_callback(
                    instance_uri,
                    "TOKEN_ERROR",
                    "System",
                    "Token has no current node",
                )
            return

        # Skip tokens that are no longer active
        token_status = self._instances.value(token_uri, INST.status)
        if token_status and str(token_status) in ["CONSUMED", "ERROR", "WAITING"]:
            return

        # Get node types
        node_types = self.get_node_types(current_node)

        logger.debug(f"Executing token at {current_node}, types: {node_types}")

        # Determine node category and dispatch to appropriate handler
        node_category = self.categorize_node(node_types)

        if node_category in handlers:
            handlers[node_category](
                instance_uri, token_uri, current_node, instance_id, merged_gateways
            )
        else:
            # Default: move to next node
            self.move_token_to_next(instance_uri, token_uri, instance_id)

        if save_callback:
            save_callback()

    def get_node_types(self, node_uri: URIRef) -> List[URIRef]:
        """Get all RDF types for a node."""
        node_types = []
        for _, _, o in self._definitions.triples((node_uri, RDF.type, None)):
            node_types.append(o)
        return node_types

    def categorize_node(self, node_types: List[URIRef]) -> str:
        """
        Categorize a node based on its types.

        Args:
            node_types: List of RDF type URIs

        Returns:
            String category name
        """
        type_strs = [str(t).lower() for t in node_types]
        type_str_combined = " ".join(type_strs)

        # Check for specific end event types first
        if "cancelendevent" in type_str_combined:
            return "cancel_end_event"
        if "compensationendevent" in type_str_combined:
            return "compensation_end_event"
        if "errorendevent" in type_str_combined:
            return "error_end_event"
        if "terminateendevent" in type_str_combined:
            return "terminate_end_event"
        if "messageendevent" in type_str_combined:
            return "message_end_event"

        # Check for boundary events
        if "boundaryevent" in type_str_combined:
            return "boundary_event"

        # Check for start/end events
        if BPMN.StartEvent in node_types or BPMN.startEvent in node_types:
            return "start_event"
        if BPMN.EndEvent in node_types or BPMN.endEvent in node_types:
            return "end_event"

        # Check for tasks
        if BPMN.ServiceTask in node_types or BPMN.serviceTask in node_types:
            return "service_task"
        if "sendtask" in type_str_combined:
            return "send_task"
        if "scripttask" in type_str_combined:
            return "script_task"
        if BPMN.UserTask in node_types or BPMN.userTask in node_types:
            return "user_task"
        if "manualtask" in type_str_combined:
            return "manual_task"
        if BPMN.ReceiveTask in node_types or BPMN.receiveTask in node_types:
            return "receive_task"

        # Check for gateways
        if BPMN.EventBasedGateway in node_types:
            return "event_based_gateway"
        if (
            BPMN.ExclusiveGateway in node_types
            or "exclusivegateway" in type_str_combined
        ):
            return "exclusive_gateway"
        if BPMN.ParallelGateway in node_types:
            return "parallel_gateway"
        if (
            BPMN.InclusiveGateway in node_types
            or "inclusivegateway" in type_str_combined
        ):
            return "inclusive_gateway"

        # Check for subprocesses
        if "expandedsubprocess" in type_str_combined:
            return "expanded_subprocess"
        if "callactivity" in type_str_combined:
            return "call_activity"
        if "eventsubprocess" in type_str_combined:
            return "event_subprocess"

        # Check for intermediate events
        if "intermediatecatchevent" in type_str_combined:
            return "intermediate_catch_event"
        if "intermediatethrowevent" in type_str_combined:
            return "intermediate_throw_event"

        return "default"

    # ==================== Token Movement ====================

    def move_token_to_next(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        instance_id: str,
    ) -> List[URIRef]:
        """
        Move token to the next node(s) via sequence flows.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            instance_id: ID of the instance

        Returns:
            List of target node URIs
        """
        current_node = self._instances.value(token_uri, INST.currentNode)
        if not current_node:
            return []

        # Find outgoing sequence flows and their targets
        next_nodes = self.get_outgoing_targets(current_node)

        if next_nodes:
            # Move token to first target
            self._instances.set((token_uri, INST.currentNode, next_nodes[0]))

            # Create new tokens for additional targets (parallel paths)
            for additional_target in next_nodes[1:]:
                new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                self._instances.add((new_token_uri, RDF.type, INST.Token))
                self._instances.add((new_token_uri, INST.belongsTo, instance_uri))
                self._instances.add((new_token_uri, INST.status, Literal("ACTIVE")))
                self._instances.add(
                    (new_token_uri, INST.currentNode, additional_target)
                )
                self._instances.add((instance_uri, INST.hasToken, new_token_uri))
        else:
            # No outgoing flows - consume token
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        return next_nodes

    def get_outgoing_targets(self, node_uri: URIRef) -> List[URIRef]:
        """Get target nodes from outgoing sequence flows."""
        targets = []
        for _, _, flow_uri in self._definitions.triples(
            (node_uri, BPMN.outgoing, None)
        ):
            for _, _, target in self._definitions.triples(
                (flow_uri, BPMN.targetRef, None)
            ):
                targets.append(target)
                break
        return targets

    # ==================== Gateway Handling ====================

    def handle_exclusive_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        evaluate_conditions_callback: Callable,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """
        Handle an exclusive gateway by evaluating conditions.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the gateway
            instance_id: ID of the instance
            evaluate_conditions_callback: Callback to evaluate gateway conditions
            log_callback: Optional callback for logging events
        """
        next_node = evaluate_conditions_callback(instance_uri, node_uri)

        if next_node:
            self._instances.set((token_uri, INST.currentNode, next_node))
        else:
            logger.error(f"No valid path found at exclusive gateway {node_uri}")
            self._instances.set((token_uri, INST.status, Literal("ERROR")))
            if log_callback:
                log_callback(
                    instance_uri,
                    "GATEWAY_ERROR",
                    "System",
                    f"No valid path at {str(node_uri)}",
                )

    def handle_parallel_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """
        Handle a parallel gateway (fork).

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the gateway
            instance_id: ID of the instance
            log_callback: Optional callback for logging events
        """
        next_nodes = self.get_outgoing_targets(node_uri)

        if len(next_nodes) > 1:
            # Move token to first target
            self._instances.set((token_uri, INST.currentNode, next_nodes[0]))

            # Create tokens for additional targets
            for additional_target in next_nodes[1:]:
                new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                self._instances.add((new_token_uri, RDF.type, INST.Token))
                self._instances.add((new_token_uri, INST.belongsTo, instance_uri))
                self._instances.add((new_token_uri, INST.status, Literal("ACTIVE")))
                self._instances.add(
                    (new_token_uri, INST.currentNode, additional_target)
                )
                self._instances.add((instance_uri, INST.hasToken, new_token_uri))

            if log_callback:
                log_callback(
                    instance_uri,
                    "PARALLEL_GATEWAY_FORK",
                    "System",
                    f"Parallel gateway {str(node_uri)} forked to {len(next_nodes)} paths",
                )

            logger.info(
                f"Parallel gateway {node_uri} created {len(next_nodes)} parallel paths"
            )
        elif len(next_nodes) == 1:
            self._instances.set((token_uri, INST.currentNode, next_nodes[0]))

    def count_incoming_flows(self, node_uri: URIRef) -> int:
        """Count incoming sequence flows to a node."""
        count = 0
        for _ in self._definitions.triples((node_uri, BPMN.incoming, None)):
            count += 1
        return count

    def count_waiting_tokens_at_gateway(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
    ) -> int:
        """Count tokens waiting at or heading to a gateway."""
        count = 0
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            current_node = self._instances.value(token_uri, INST.currentNode)
            status = self._instances.value(token_uri, INST.status)
            if (
                current_node == gateway_uri
                and status
                and str(status) in ["ACTIVE", "WAITING"]
            ):
                count += 1
        return count

    # ==================== Instance Status ====================

    def set_instance_status(
        self,
        instance_uri: URIRef,
        status: str,
    ) -> None:
        """Set the status of an instance."""
        self._instances.set((instance_uri, INST.status, Literal(status)))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

    def get_instance_status(self, instance_uri: URIRef) -> Optional[str]:
        """Get the status of an instance."""
        status = self._instances.value(instance_uri, INST.status)
        return str(status) if status else None

    # ==================== Token Management ====================

    def create_token(
        self,
        instance_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        status: str = "ACTIVE",
        loop_instance: Optional[int] = None,
    ) -> URIRef:
        """
        Create a new token.

        Args:
            instance_uri: URI of the process instance
            node_uri: URI of the node
            instance_id: ID of the instance
            status: Initial token status
            loop_instance: Optional loop instance number

        Returns:
            URI of the created token
        """
        token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]

        self._instances.add((token_uri, RDF.type, INST.Token))
        self._instances.add((token_uri, INST.belongsTo, instance_uri))
        self._instances.add((token_uri, INST.status, Literal(status)))
        self._instances.add((token_uri, INST.currentNode, node_uri))
        self._instances.add((instance_uri, INST.hasToken, token_uri))

        if loop_instance is not None:
            self._instances.add(
                (token_uri, INST.loopInstance, Literal(str(loop_instance)))
            )

        return token_uri

    def consume_token(self, token_uri: URIRef) -> None:
        """Mark a token as consumed."""
        self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

    def set_token_waiting(self, token_uri: URIRef) -> None:
        """Mark a token as waiting."""
        self._instances.set((token_uri, INST.status, Literal("WAITING")))

    def set_token_error(self, token_uri: URIRef) -> None:
        """Mark a token as error."""
        self._instances.set((token_uri, INST.status, Literal("ERROR")))

    def get_token_status(self, token_uri: URIRef) -> Optional[str]:
        """Get the status of a token."""
        status = self._instances.value(token_uri, INST.status)
        return str(status) if status else None

    def get_token_current_node(self, token_uri: URIRef) -> Optional[URIRef]:
        """Get the current node of a token."""
        return self._instances.value(token_uri, INST.currentNode)

    def set_token_current_node(self, token_uri: URIRef, node_uri: URIRef) -> None:
        """Set the current node of a token."""
        self._instances.set((token_uri, INST.currentNode, node_uri))
