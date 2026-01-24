# Error Handler for SPEAR Engine
# Handles error, compensation, cancel, and terminate events

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING

from rdflib import URIRef, Literal, RDF, Graph

from src.api.storage.base import BPMN, INST

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ErrorHandler:
    """
    Handles error, compensation, cancel, and terminate events in BPMN processes.

    Supports:
    - Error end events: Terminate instance with error status
    - Cancel end events: Cancel transaction subprocess
    - Compensation end events: Trigger compensation handlers
    - Terminate end events: Immediately terminate all tokens
    - Error boundary events: Catch errors from activities
    - Compensation boundary events: Handle compensation triggers
    - External error throwing: API-based error injection
    - External cancellation: API-based instance cancellation
    """

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
    ):
        """
        Initialize the error handler.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
        """
        self._definitions = definitions_graph
        self._instances = instances_graph

    # ==================== End Event Handlers ====================

    def execute_error_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        set_variable_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute an error end event - terminates the instance with error.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the error end event node
            instance_id: ID of the instance
            set_variable_callback: Optional callback to set instance variables
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes
        """
        logger.info(f"Error end event reached at {node_uri} for instance {instance_id}")

        error_ref = self._definitions.value(node_uri, BPMN.errorRef)
        error_code = str(error_ref).split("/")[-1] if error_ref else None

        if log_callback:
            log_callback(
                instance_uri,
                "ERROR_END_EVENT",
                "System",
                f"Error end event triggered at {str(node_uri)}"
                + (f", errorCode: {error_code}" if error_code else ""),
            )

        self._instances.set((token_uri, INST.status, Literal("CONSUMED")))
        self._instances.set((instance_uri, INST.status, Literal("ERROR")))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        if set_variable_callback:
            set_variable_callback(instance_id, "errorCode", error_code or "UNKNOWN")
            set_variable_callback(
                instance_id, "errorNode", str(node_uri).split("/")[-1]
            )

        if save_callback:
            save_callback()

    def execute_cancel_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a cancel end event - terminates the transaction subprocess.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the cancel end event node
            instance_id: ID of the instance
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes
        """
        logger.info(
            f"Cancel end event reached at {node_uri} for instance {instance_id}"
        )

        if log_callback:
            log_callback(
                instance_uri,
                "CANCEL_EVENT",
                "System",
                f"Cancel end event triggered at {str(node_uri)}",
            )

        self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        # Find and terminate enclosing transaction
        transaction_subprocess = self._find_enclosing_transaction(node_uri)
        if transaction_subprocess:
            self._terminate_transaction_subprocess(
                instance_uri, transaction_subprocess, instance_id, log_callback
            )

        self._instances.set((instance_uri, INST.status, Literal("CANCELLED")))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        if log_callback:
            log_callback(
                instance_uri,
                "INSTANCE_CANCELLED",
                "System",
                "Instance cancelled via cancel end event",
            )

        if save_callback:
            save_callback()

    def execute_terminate_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a terminate end event - immediately terminates all tokens.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the terminate end event node
            instance_id: ID of the instance
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes
        """
        logger.info(
            f"Terminate end event reached at {node_uri} for instance {instance_id}"
        )

        if log_callback:
            log_callback(
                instance_uri,
                "TERMINATE_END_EVENT",
                "System",
                f"Terminate end event triggered at {str(node_uri)} - immediately terminating instance",
            )

        self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        # Consume all other active/waiting tokens
        for tok in self._instances.objects(instance_uri, INST.hasToken):
            if tok != token_uri:
                status = self._instances.value(tok, INST.status)
                if status and str(status) in ["ACTIVE", "WAITING"]:
                    self._instances.set((tok, INST.status, Literal("CONSUMED")))

        self._instances.set((instance_uri, INST.status, Literal("TERMINATED")))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        if save_callback:
            save_callback()

    def execute_compensation_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a compensation end event - triggers the compensation handler.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the compensation end event node
            instance_id: ID of the instance
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes
        """
        logger.info(
            f"Compensation end event reached at {node_uri} for instance {instance_id}"
        )

        compensate_ref = self._definitions.value(node_uri, BPMN.compensateRef)
        compensate_ref_str = str(compensate_ref) if compensate_ref else None

        if log_callback:
            log_callback(
                instance_uri,
                "COMPENSATION_END_EVENT",
                "System",
                f"Compensation end event triggered at {str(node_uri)}"
                + (
                    f", compensateRef: {compensate_ref_str}"
                    if compensate_ref_str
                    else ""
                ),
            )

        compensation_handler = self._find_compensation_handler(node_uri)
        if compensation_handler:
            self._execute_compensation_handler(
                instance_uri, compensation_handler, instance_id, log_callback
            )

        self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        if save_callback:
            save_callback()

    # ==================== Boundary Event Handlers ====================

    def execute_boundary_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        move_token_callback: Optional[Callable] = None,
        execute_token_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a boundary event (error, compensation, timer, etc.).

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the boundary event node
            instance_id: ID of the instance
            move_token_callback: Optional callback to move token to next node
            execute_token_callback: Optional callback to execute a token
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes
        """
        event_type = None
        error_ref = None
        compensate_ref = None

        for _, _, o in self._definitions.triples((node_uri, RDF.type, None)):
            o_str = str(o)
            if "ErrorBoundaryEvent" in o_str:
                event_type = "error"
                error_ref = self._definitions.value(node_uri, BPMN.errorRef)
                break
            elif "CompensationBoundaryEvent" in o_str:
                event_type = "compensation"
                compensate_ref = self._definitions.value(node_uri, BPMN.compensateRef)
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
                instance_uri,
                token_uri,
                node_uri,
                instance_id,
                error_ref,
                log_callback,
                save_callback,
            )
        elif event_type == "compensation":
            self._execute_compensation_boundary_event(
                instance_uri,
                token_uri,
                node_uri,
                instance_id,
                compensate_ref,
                execute_token_callback,
                log_callback,
                save_callback,
            )
        else:
            # Timer, message, signal - just move to next node
            if move_token_callback:
                move_token_callback(instance_uri, token_uri, instance_id)

    def _execute_error_boundary_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        error_ref: Optional[URIRef],
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """Execute an error boundary event."""
        error_code = str(error_ref).split("/")[-1] if error_ref else None

        logger.info(
            f"Error boundary event reached at {node_uri} for instance {instance_id}, error: {error_code}"
        )

        interrupting = True
        interrupting_val = self._definitions.value(node_uri, BPMN.interrupting)
        if interrupting_val:
            interrupting = str(interrupting_val).lower() == "true"

        if log_callback:
            log_callback(
                instance_uri,
                "ERROR_BOUNDARY_EVENT",
                "System",
                f"Error boundary event triggered at {str(node_uri)}"
                + (f", errorCode: {error_code}" if error_code else "")
                + f", interrupting: {interrupting}",
            )

        outgoing_targets = self._get_outgoing_targets(node_uri)
        if outgoing_targets:
            next_node = outgoing_targets[0]

            if interrupting:
                self._instances.set((token_uri, INST.currentNode, next_node))
                if log_callback:
                    log_callback(
                        instance_uri,
                        "BOUNDARY_ERROR_INTERRUPTED",
                        "System",
                        "Activity interrupted by error boundary event",
                    )
            else:
                # Non-interrupting: create new token
                boundary_token_uri = INST[
                    f"token_{instance_id}_{str(uuid.uuid4())[:8]}"
                ]
                self._instances.add((boundary_token_uri, RDF.type, INST.Token))
                self._instances.add((boundary_token_uri, INST.belongsTo, instance_uri))
                self._instances.add(
                    (boundary_token_uri, INST.status, Literal("ACTIVE"))
                )
                self._instances.add((boundary_token_uri, INST.currentNode, next_node))
                self._instances.add((instance_uri, INST.hasToken, boundary_token_uri))

            if save_callback:
                save_callback()
        else:
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

    def _execute_compensation_boundary_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        compensate_ref: Optional[URIRef],
        execute_token_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """Execute a compensation boundary event."""
        compensate_ref_str = (
            str(compensate_ref).split("/")[-1] if compensate_ref else None
        )

        logger.info(
            f"Compensation boundary event reached at {node_uri} for instance {instance_id}, "
            f"compensateRef: {compensate_ref_str}"
        )

        interrupting = True
        interrupting_val = self._definitions.value(node_uri, BPMN.interrupting)
        if interrupting_val:
            interrupting = str(interrupting_val).lower() == "true"

        if log_callback:
            log_callback(
                instance_uri,
                "COMPENSATION_BOUNDARY_EVENT",
                "System",
                f"Compensation boundary event triggered at {str(node_uri)}"
                + (
                    f", compensateRef: {compensate_ref_str}"
                    if compensate_ref_str
                    else ""
                ),
            )

        # Find and execute compensation for parent activity
        parent_activity = None
        for parent in self._definitions.objects(node_uri, BPMN.attachedTo):
            parent_activity = parent
            break

        if parent_activity:
            self._execute_compensation_for_activity(
                instance_uri,
                parent_activity,
                instance_id,
                compensate_ref_str,
                log_callback,
            )

        outgoing_targets = self._get_outgoing_targets(node_uri)
        if outgoing_targets:
            next_node = outgoing_targets[0]

            if not interrupting:
                boundary_token_uri = INST[
                    f"token_{instance_id}_{str(uuid.uuid4())[:8]}"
                ]
                self._instances.add((boundary_token_uri, RDF.type, INST.Token))
                self._instances.add((boundary_token_uri, INST.belongsTo, instance_uri))
                self._instances.add(
                    (boundary_token_uri, INST.status, Literal("ACTIVE"))
                )
                self._instances.add((boundary_token_uri, INST.currentNode, next_node))
                self._instances.add((instance_uri, INST.hasToken, boundary_token_uri))

                if execute_token_callback:
                    execute_token_callback(
                        instance_uri, boundary_token_uri, instance_id
                    )

        if save_callback:
            save_callback()

    # ==================== Transaction and Compensation Helpers ====================

    def _find_enclosing_transaction(self, node_uri: URIRef) -> Optional[URIRef]:
        """Find the enclosing transaction subprocess for a node."""
        current = node_uri
        checked = set()

        while current and str(current) not in checked:
            checked.add(str(current))

            for _, _, o in self._definitions.triples((current, RDF.type, None)):
                if "transaction" in str(o).lower():
                    return current

            parents = list(self._definitions.objects(current, BPMN.hasParent))
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
        log_callback: Optional[Callable] = None,
    ) -> None:
        """Terminate all tokens inside a transaction subprocess."""
        logger.info(
            f"Terminating transaction subprocess {transaction_subprocess} "
            f"for instance {instance_id}"
        )

        if log_callback:
            log_callback(
                instance_uri,
                "TRANSACTION_TERMINATED",
                "System",
                f"Transaction subprocess {str(transaction_subprocess)} terminated",
            )

        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            current_node = self._instances.value(token_uri, INST.currentNode)
            if current_node:
                is_inside = self._is_node_inside_subprocess(
                    current_node, transaction_subprocess
                )
                if is_inside:
                    status = self._instances.value(token_uri, INST.status)
                    if status and str(status) in ["ACTIVE", "WAITING"]:
                        self._instances.set(
                            (token_uri, INST.status, Literal("CONSUMED"))
                        )

    def _is_node_inside_subprocess(
        self, node_uri: URIRef, subprocess_uri: URIRef
    ) -> bool:
        """Check if a node is inside a subprocess."""
        if node_uri == subprocess_uri:
            return True

        for child in self._definitions.subjects(BPMN.hasParent, subprocess_uri):
            if child == node_uri:
                return True
            if self._is_node_inside_subprocess(child, subprocess_uri):
                return True

        return False

    def _find_compensation_handler(self, node_uri: URIRef) -> Optional[URIRef]:
        """Find the compensation handler for a compensation end event."""
        compensation_handler_type = URIRef(
            "http://dkm.fbk.eu/index.php/BPMN2_Ontology#compensationHandler"
        )

        for handler in self._definitions.subjects(RDF.type, compensation_handler_type):
            compensate_ref = self._definitions.value(handler, BPMN.compensateRef)
            if compensate_ref == node_uri:
                return handler

        parent = self._definitions.value(node_uri, BPMN.hasParent)
        if parent:
            return self._find_compensation_handler(parent)

        return None

    def _execute_compensation_handler(
        self,
        instance_uri: URIRef,
        handler_uri: URIRef,
        instance_id: str,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """Execute a compensation handler subprocess."""
        logger.info(
            f"Executing compensation handler {handler_uri} for instance {instance_id}"
        )

        if log_callback:
            log_callback(
                instance_uri,
                "COMPENSATION_HANDLER_STARTED",
                "System",
                f"Compensation handler {str(handler_uri)} started",
            )

        # Look for intermediate throw events in the handler
        for child_uri in self._definitions.subjects(BPMN.hasParent, handler_uri):
            for _, _, o in self._definitions.triples((child_uri, RDF.type, None)):
                if "intermediatethrowevent" in str(o).lower():
                    compensate_ref = self._definitions.value(
                        child_uri, BPMN.compensateRef
                    )
                    if compensate_ref and log_callback:
                        log_callback(
                            instance_uri,
                            "COMPENSATION_THROWN",
                            "System",
                            f"Compensation thrown for activity {str(compensate_ref)}",
                        )
                    break

        if log_callback:
            log_callback(
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
        compensate_ref: Optional[str],
        log_callback: Optional[Callable] = None,
    ) -> None:
        """Execute compensation for a specific activity."""
        logger.info(
            f"Executing compensation for activity {activity_uri} "
            f"(compensateRef: {compensate_ref})"
        )

        if log_callback:
            log_callback(
                instance_uri,
                "COMPENSATION_STARTED",
                "System",
                f"Compensation started for activity {str(activity_uri)}",
            )

        compensation_handler_type = URIRef(
            "http://dkm.fbk.eu/index.php/BPMN2_Ontology#compensationHandler"
        )

        compensation_handler = None
        for handler in self._definitions.subjects(RDF.type, compensation_handler_type):
            handler_compensate_ref = self._definitions.value(
                handler, BPMN.compensateRef
            )
            if (
                handler_compensate_ref
                and compensate_ref
                and str(handler_compensate_ref).endswith(compensate_ref)
            ):
                compensation_handler = handler
                break

        if compensation_handler:
            self._execute_compensation_handler(
                instance_uri, compensation_handler, instance_id, log_callback
            )

        if log_callback:
            log_callback(
                instance_uri,
                "COMPENSATION_COMPLETED",
                "System",
                f"Compensation completed for activity {str(activity_uri)}",
            )

    # ==================== External Error/Cancel APIs ====================

    def throw_error(
        self,
        instance_id: str,
        error_code: str,
        error_message: Optional[str] = None,
        get_boundary_events_callback: Optional[Callable] = None,
        trigger_boundary_callback: Optional[Callable] = None,
        execute_instance_callback: Optional[Callable] = None,
        set_variable_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Throw an error in a process instance (for API-based error injection).

        Args:
            instance_id: The process instance ID
            error_code: The error code to throw
            error_message: Optional error message
            get_boundary_events_callback: Callback to get boundary events for a node
            trigger_boundary_callback: Callback to trigger a boundary event
            execute_instance_callback: Callback to continue instance execution
            set_variable_callback: Callback to set instance variables
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes

        Returns:
            Dictionary with status of the error throw
        """
        instance_uri = INST[instance_id]

        if not (instance_uri, RDF.type, INST.ProcessInstance) in self._instances:
            raise ValueError(f"Instance {instance_id} not found")

        instance_status = self._instances.value(instance_uri, INST.status)
        if instance_status and str(instance_status) not in ["RUNNING", "ACTIVE"]:
            raise ValueError(
                f"Cannot throw error in instance with status: {instance_status}"
            )

        logger.info(
            f"Throwing error {error_code} in instance {instance_id}: {error_message}"
        )

        if log_callback:
            log_callback(
                instance_uri,
                "ERROR_THROWN",
                "System",
                f"Error thrown via API: code={error_code}, message={error_message}",
            )

        if set_variable_callback:
            set_variable_callback(instance_id, "lastErrorCode", error_code)
            if error_message:
                set_variable_callback(instance_id, "lastErrorMessage", error_message)

        # Look for error boundary events to catch the error
        found_error_boundary = False
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            token_status = self._instances.value(token_uri, INST.status)
            if not token_status or str(token_status) not in ["ACTIVE", "WAITING"]:
                continue

            current_node = self._instances.value(token_uri, INST.currentNode)
            if not current_node:
                continue

            if get_boundary_events_callback:
                boundary_events = get_boundary_events_callback(current_node)
                for event_info in boundary_events:
                    if event_info["event_type"] == "error":
                        event_error_ref = self._definitions.value(
                            URIRef(event_info["uri"]), BPMN.errorRef
                        )
                        event_error_code = (
                            str(event_error_ref).split("/")[-1]
                            if event_error_ref
                            else None
                        )

                        if event_error_code == error_code:
                            interrupting = event_info["is_interrupting"]
                            if trigger_boundary_callback:
                                trigger_boundary_callback(
                                    token_uri,
                                    instance_uri,
                                    URIRef(event_info["uri"]),
                                    instance_id,
                                    interrupting,
                                    {
                                        "errorCode": error_code,
                                        "errorMessage": error_message,
                                    },
                                )
                            found_error_boundary = True
                            logger.info(
                                f"Error {error_code} caught by boundary event "
                                f"{event_info['uri']}"
                            )

        if found_error_boundary:
            if execute_instance_callback:
                execute_instance_callback(instance_uri, instance_id)
            return {
                "status": "caught",
                "instance_id": instance_id,
                "error_code": error_code,
                "message": error_message,
                "caught_by_boundary_event": True,
            }
        else:
            self._instances.set((instance_uri, INST.status, Literal("ERROR")))
            if set_variable_callback:
                set_variable_callback(instance_id, "errorCode", error_code)
            if save_callback:
                save_callback()

            return {
                "status": "uncaught",
                "instance_id": instance_id,
                "error_code": error_code,
                "message": error_message,
                "caught_by_boundary_event": False,
            }

    def cancel_instance(
        self,
        instance_id: str,
        reason: Optional[str] = None,
        get_instance_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Cancel a process instance (external cancellation).

        Args:
            instance_id: The process instance ID
            reason: Optional cancellation reason
            get_instance_callback: Callback to get instance data
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes

        Returns:
            Dictionary with updated instance state
        """
        instance_uri = INST[instance_id]

        if not (instance_uri, RDF.type, INST.ProcessInstance) in self._instances:
            raise ValueError(f"Instance {instance_id} not found")

        current_status = self._instances.value(instance_uri, INST.status)
        if current_status and str(current_status) in [
            "COMPLETED",
            "TERMINATED",
            "CANCELLED",
        ]:
            raise ValueError(f"Instance {instance_id} is already {current_status}")

        logger.info(f"Cancelling instance {instance_id}: {reason}")

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

        self._instances.set((instance_uri, INST.status, Literal("CANCELLED")))
        self._instances.set(
            (instance_uri, INST.updatedAt, Literal(datetime.now().isoformat()))
        )

        if save_callback:
            save_callback()

        if get_instance_callback:
            return get_instance_callback(instance_id)

        return {"instance_id": instance_id, "status": "CANCELLED"}

    # ==================== Helpers ====================

    def _get_outgoing_targets(self, node_uri: URIRef) -> List[URIRef]:
        """Get target nodes from outgoing sequence flows."""
        targets = []
        for flow_uri in self._definitions.objects(node_uri, BPMN.outgoing):
            target = self._definitions.value(flow_uri, BPMN.targetRef)
            if target:
                targets.append(target)
        return targets

    def get_boundary_events_for_node(self, node_uri: URIRef) -> List[Dict[str, Any]]:
        """
        Get all boundary events attached to a node.

        Args:
            node_uri: URI of the node to find boundary events for

        Returns:
            List of boundary event dictionaries with event details
        """
        boundary_events = []

        for event_uri in self._definitions.objects(node_uri, BPMN.hasBoundaryEvent):
            event_info = {
                "uri": str(event_uri),
                "is_interrupting": True,
                "message_name": None,
                "event_type": None,
                "error_code": None,
            }

            for _, _, o in self._definitions.triples((event_uri, RDF.type, None)):
                o_str = str(o)
                if "MessageBoundaryEvent" in o_str:
                    event_info["event_type"] = "message"
                    message_ref = self._definitions.value(event_uri, BPMN.messageRef)
                    if message_ref:
                        event_info["message_name"] = str(message_ref).split("/")[-1]
                    break
                elif "TimerBoundaryEvent" in o_str:
                    event_info["event_type"] = "timer"
                    break
                elif "ErrorBoundaryEvent" in o_str:
                    event_info["event_type"] = "error"
                    error_ref = self._definitions.value(event_uri, BPMN.errorRef)
                    if error_ref:
                        event_info["error_code"] = str(error_ref).split("/")[-1]
                    break
                elif "SignalBoundaryEvent" in o_str:
                    event_info["event_type"] = "signal"
                    break
                elif "CompensationBoundaryEvent" in o_str:
                    event_info["event_type"] = "compensation"
                    break

            interrupting = self._definitions.value(event_uri, BPMN.interrupting)
            if interrupting:
                event_info["is_interrupting"] = str(interrupting).lower() == "true"

            boundary_events.append(event_info)

        return boundary_events
