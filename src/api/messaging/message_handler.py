# Message Handler for SPEAR Engine
# Handles message sending, receiving, and routing

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING

from rdflib import URIRef, Literal, RDF, Graph

from src.api.storage.base import BPMN, INST, VAR

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MessageHandler:
    """
    Handles message sending and receiving in BPMN processes.

    Supports:
    - Message handlers: Register callbacks for message events
    - Send message: Route messages to waiting receive tasks
    - Boundary message events: Trigger message boundary events
    - Event-based gateways: Route messages to event-based gateway paths
    """

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
    ):
        """
        Initialize the message handler.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
        """
        self._definitions = definitions_graph
        self._instances = instances_graph
        self._handlers: Dict[str, Dict[str, Any]] = {}

    # ==================== Handler Registration ====================

    def register_handler(
        self,
        message_name: str,
        handler_function: Callable,
        description: str = "",
    ) -> bool:
        """
        Register a handler for a message.

        Args:
            message_name: The message name to register
            handler_function: The function to call when message is received
            description: Human-readable description of the handler

        Returns:
            True if registered successfully
        """
        self._handlers[message_name] = {
            "function": handler_function,
            "description": description,
            "registered_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Registered handler for message: {message_name}")
        return True

    def unregister_handler(self, message_name: str) -> bool:
        """
        Unregister a handler for a message.

        Args:
            message_name: The message name to unregister

        Returns:
            True if unregistered, False if message didn't exist
        """
        if message_name in self._handlers:
            del self._handlers[message_name]
            logger.info(f"Unregistered handler for message: {message_name}")
            return True
        return False

    def get_all_handlers(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all registered message handlers.

        Returns:
            Dictionary of message_name -> handler info (without the function)
        """
        handlers = {}
        for msg_name, info in self._handlers.items():
            handlers[msg_name] = {
                "description": info.get("description", ""),
                "registered_at": info.get("registered_at", ""),
            }
        return handlers

    def handler_exists(self, message_name: str) -> bool:
        """Check if a handler exists for a message."""
        return message_name in self._handlers

    # ==================== Message Sending ====================

    def send_message(
        self,
        message_name: str,
        instance_id: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        log_callback: Optional[Callable] = None,
        boundary_event_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to waiting receive tasks or event-based gateways.

        Args:
            message_name: The message name
            instance_id: Optional specific instance to target
            variables: Optional variables to merge with the message
            correlation_id: Optional correlation ID for routing
            log_callback: Optional callback for logging events
            boundary_event_callback: Optional callback for boundary event handling

        Returns:
            Dictionary with status and matched task info
        """
        message = {
            "name": message_name,
            "instance_id": instance_id,
            "variables": variables or {},
            "correlation_id": correlation_id,
            "received_at": datetime.utcnow().isoformat(),
        }

        # Find matching receive tasks
        matched = self._find_matching_receive_tasks(message_name, instance_id)

        if matched:
            self._activate_matched_tasks(matched, message_name, variables, log_callback)
            logger.info(
                f"Message '{message_name}' matched {len(matched)} waiting tasks"
            )

        message["matched_count"] = len(matched)

        # Find matching boundary events
        boundary_matches = self._find_matching_boundary_events(
            message_name, instance_id
        )

        if boundary_matches and boundary_event_callback:
            for match in boundary_matches:
                boundary_event_callback(
                    URIRef(match["token_uri"]),
                    URIRef(match["instance_uri"]) if match["instance_uri"] else None,
                    URIRef(match["boundary_event_uri"]),
                    match["instance_uri"].split("/")[-1]
                    if match["instance_uri"]
                    else "",
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

    def _find_matching_receive_tasks(
        self,
        message_name: str,
        instance_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find receive tasks waiting for this message."""
        matched = []

        for token_uri in self._instances.subjects(RDF.type, INST.Token):
            token_status = self._instances.value(token_uri, INST.status)
            if not token_status or str(token_status) != "WAITING":
                continue

            current_node = self._instances.value(token_uri, INST.currentNode)
            if not current_node:
                continue

            # Check node type
            node_type = None
            for _, _, o in self._definitions.triples((current_node, RDF.type, None)):
                node_type = o
                break

            if node_type not in [BPMN.ReceiveTask, BPMN.receiveTask]:
                continue

            # Get message name from node
            node_message = self._get_node_message_name(current_node)
            if node_message != message_name:
                continue

            # Check instance filter
            instance_uri = self._instances.value(token_uri, INST.belongsTo)
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

        return matched

    def _get_node_message_name(self, node_uri: URIRef) -> Optional[str]:
        """Get the message name configured on a node."""
        # Try standard BPMN message property
        for _, _, o in self._definitions.triples((node_uri, BPMN.message, None)):
            return str(o)

        # Try Camunda extension
        camunda_msg = URIRef("http://camunda.org/schema/1.0/bpmn#message")
        for _, _, o in self._definitions.triples((node_uri, camunda_msg, None)):
            return str(o)

        return None

    def _activate_matched_tasks(
        self,
        matched: List[Dict[str, Any]],
        message_name: str,
        variables: Optional[Dict[str, Any]],
        log_callback: Optional[Callable],
    ) -> None:
        """Activate matched waiting tasks."""
        for match in matched:
            token_uri = URIRef(match["token_uri"])
            self._instances.set((token_uri, INST.status, Literal("ACTIVE")))
            current_node = URIRef(match["node_uri"])
            instance_uri = (
                URIRef(match["instance_uri"]) if match["instance_uri"] else None
            )

            # Set variables
            if variables:
                instance_id_for_var = (
                    str(match["instance_uri"]).split("/")[-1]
                    if match["instance_uri"]
                    else None
                )
                if instance_id_for_var:
                    for var_name, var_value in variables.items():
                        var_uri = VAR[f"{instance_id_for_var}_{var_name}"]
                        self._instances.add(
                            (
                                URIRef(match["instance_uri"]),
                                INST.hasVariable,
                                var_uri,
                            )
                        )
                        self._instances.add((var_uri, VAR.name, Literal(var_name)))
                        self._instances.add(
                            (var_uri, VAR.value, Literal(str(var_value)))
                        )

            # Log event
            if log_callback and instance_uri:
                log_callback(
                    instance_uri,
                    "MESSAGE_RECEIVED",
                    "System",
                    f"Message '{message_name}' received at {current_node}",
                )

    def _find_matching_boundary_events(
        self,
        message_name: str,
        instance_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find boundary events waiting for this message."""
        boundary_matches = []

        for token_uri in self._instances.subjects(RDF.type, INST.Token):
            token_status = self._instances.value(token_uri, INST.status)
            if not token_status or str(token_status) not in ["WAITING", "ACTIVE"]:
                continue

            current_node = self._instances.value(token_uri, INST.currentNode)
            if not current_node:
                continue

            # Check current node and parents
            nodes_to_check = [current_node]
            for parent in self._definitions.objects(current_node, BPMN.hasParent):
                nodes_to_check.append(parent)

            for node_to_check in nodes_to_check:
                boundary_events = self._get_boundary_events(node_to_check)
                for event_info in boundary_events:
                    if (
                        event_info["event_type"] == "message"
                        and event_info["message_name"] == message_name
                    ):
                        instance_uri = self._instances.value(token_uri, INST.belongsTo)
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

        return boundary_matches

    def _get_boundary_events(self, node_uri: URIRef) -> List[Dict[str, Any]]:
        """Get all boundary events attached to a node."""
        boundary_events = []

        for event_uri in self._definitions.objects(node_uri, BPMN.hasBoundaryEvent):
            event_info = {
                "uri": event_uri,
                "is_interrupting": True,
                "message_name": None,
                "event_type": None,
            }

            for _, _, o in self._definitions.triples((event_uri, RDF.type, None)):
                o_str = str(o)
                if "MessageBoundaryEvent" in o_str:
                    event_info["event_type"] = "message"
                    message_ref = self._definitions.value(event_uri, BPMN.messageRef)
                    if message_ref:
                        event_info["message_name"] = str(message_ref).split("/")[-1]
                    if not event_info["message_name"]:
                        camunda_msg = self._definitions.value(
                            event_uri,
                            URIRef("http://camunda.org/schema/1.0/bpmn#message"),
                        )
                        if camunda_msg:
                            event_info["message_name"] = str(camunda_msg)
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

            # Check interrupting property
            interrupting = self._definitions.value(event_uri, BPMN.interrupting)
            if interrupting:
                event_info["is_interrupting"] = str(interrupting).lower() == "true"

            boundary_events.append(event_info)

        return boundary_events

    # ==================== Receive Task Handling ====================

    def execute_receive_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a receive task - wait for a message.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the receive task node
            instance_id: ID of the instance
            log_callback: Optional callback for logging events
        """
        message_name = self._get_node_message_name(node_uri)

        if message_name:
            self._instances.set((token_uri, INST.status, Literal("WAITING")))

            if log_callback:
                log_callback(
                    instance_uri,
                    "WAITING_FOR_MESSAGE",
                    "System",
                    f"Waiting for message '{message_name}' at {node_uri}",
                )

            logger.info(
                f"Token at receive task {node_uri}, waiting for message: {message_name}"
            )
        else:
            if log_callback:
                log_callback(
                    instance_uri,
                    "RECEIVE_TASK",
                    "System",
                    f"{str(node_uri)} (no message configured)",
                )

            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

    # ==================== Message End Event ====================

    def trigger_message_end_event(
        self,
        instance_uri: URIRef,
        message_name: str,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """
        Trigger a message from a message end event.

        Args:
            instance_uri: URI of the process instance
            message_name: Name of the message to trigger
            log_callback: Optional callback for logging events
        """
        instance_id = str(instance_uri).split("/")[-1]

        logger.info(
            f"Message end event threw message '{message_name}' "
            f"from instance {instance_id}"
        )

        if log_callback:
            log_callback(
                instance_uri,
                "MESSAGE_THROWN",
                "System",
                f"Message '{message_name}' thrown from message end event",
            )

    # ==================== Boundary Event Handling ====================

    def get_outgoing_flows(self, node_uri: URIRef) -> List[URIRef]:
        """
        Get all outgoing flow targets from a node.

        Args:
            node_uri: URI of the node

        Returns:
            List of target node URIs
        """
        targets = []
        for flow_uri in self._definitions.objects(node_uri, BPMN.outgoing):
            target = self._definitions.value(flow_uri, BPMN.targetRef)
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
        variables: Optional[Dict[str, Any]] = None,
        log_callback: Optional[Callable] = None,
        execute_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Trigger a boundary event on a token.

        Args:
            token_uri: URI of the token at the parent activity
            instance_uri: URI of the process instance
            boundary_event_uri: URI of the boundary event to trigger
            instance_id: Instance ID string
            is_interrupting: Whether this is an interrupting boundary event
            variables: Optional variables to pass with the event
            log_callback: Optional callback for logging events
            execute_callback: Optional callback for executing the token

        Returns:
            True if triggered successfully
        """
        logger.info(
            f"Triggering boundary event {boundary_event_uri} "
            f"(interrupting={is_interrupting})"
        )

        if is_interrupting and log_callback:
            log_callback(
                instance_uri,
                "BOUNDARY_INTERRUPTED",
                "System",
                f"Activity interrupted by boundary event {str(boundary_event_uri)}",
            )

        outgoing_targets = self.get_outgoing_flows(boundary_event_uri)
        if not outgoing_targets:
            logger.warning(f"Boundary event {boundary_event_uri} has no outgoing flows")
            return False

        instance_id_for_vars = ""
        if instance_uri:
            instance_id_for_vars = str(instance_uri).split("/")[-1]
        if not instance_id_for_vars:
            instance_id_for_vars = instance_id if instance_id else ""

        if is_interrupting:
            self._instances.set((token_uri, INST.currentNode, boundary_event_uri))
            self._instances.set((token_uri, INST.status, Literal("ACTIVE")))

            if log_callback:
                log_callback(
                    instance_uri,
                    "BOUNDARY_EVENT_TRIGGERED",
                    "System",
                    f"Boundary event {str(boundary_event_uri)} triggered",
                )

            # Set variables
            if variables:
                for var_name, var_value in variables.items():
                    var_uri = VAR[f"{instance_id_for_vars}_{var_name}"]
                    self._instances.add((var_uri, VAR.name, Literal(var_name)))
                    self._instances.add((var_uri, VAR.value, Literal(str(var_value))))

            # Execute token
            if execute_callback:
                execute_callback(instance_uri, token_uri, instance_id_for_vars)
        else:
            # Non-interrupting: create new token
            boundary_token_uri = INST[
                f"token_{instance_id_for_vars}_{str(uuid.uuid4())[:8]}"
            ]
            self._instances.add((boundary_token_uri, RDF.type, INST.Token))
            self._instances.add((boundary_token_uri, INST.belongsTo, instance_uri))
            self._instances.add((boundary_token_uri, INST.status, Literal("ACTIVE")))
            self._instances.add(
                (boundary_token_uri, INST.currentNode, boundary_event_uri)
            )
            self._instances.add((instance_uri, INST.hasToken, boundary_token_uri))

            if log_callback:
                log_callback(
                    instance_uri,
                    "BOUNDARY_EVENT_NON_INTERRUPTING",
                    "System",
                    f"Non-interrupting boundary event {str(boundary_event_uri)} triggered",
                )

            # Set variables
            if variables:
                for var_name, var_value in variables.items():
                    var_uri = VAR[f"{instance_id_for_vars}_{var_name}"]
                    self._instances.add((var_uri, VAR.name, Literal(var_name)))
                    self._instances.add((var_uri, VAR.value, Literal(str(var_value))))

            # Execute token
            if execute_callback:
                execute_callback(instance_uri, boundary_token_uri, instance_id_for_vars)

        return True
