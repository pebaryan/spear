# Node Handlers for SPEAR Engine
# Handles execution of BPMN node types (service tasks, script tasks, gateways, etc.)

import ast
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING

from rdflib import URIRef, Literal, RDF, Graph

from src.api.storage.base import BPMN, INST

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class NodeHandlers:
    """
    Handles execution of various BPMN node types.

    Supports:
    - Service tasks: Execute registered topic handlers
    - Script tasks: Execute Python scripts
    - Event-based gateways: Wait for multiple event paths
    - Execution listeners: Execute start/end listeners
    - Task listeners: Execute task-specific listeners
    """

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
        script_tasks_enabled: bool = False,
    ):
        """
        Initialize the node handlers.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
            script_tasks_enabled: Whether to allow script task execution
        """
        self._definitions = definitions_graph
        self._instances = instances_graph
        self._script_tasks_enabled = script_tasks_enabled

    # ==================== Service Task ====================

    def execute_service_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        get_variables_callback: Callable,
        set_variable_callback: Callable,
        execute_topic_callback: Callable,
        get_multi_instance_info_callback: Callable,
        move_token_callback: Callable,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a service task.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the service task node
            instance_id: ID of the instance
            get_variables_callback: Callback to get instance variables
            set_variable_callback: Callback to set instance variables
            execute_topic_callback: Callback to execute topic handler
            get_multi_instance_info_callback: Callback to get multi-instance info
            move_token_callback: Callback to move token to next node
            log_callback: Optional callback for logging events
        """
        # Get topic from node
        topic = self._get_node_topic(node_uri)

        if not topic:
            if log_callback:
                log_callback(
                    instance_uri,
                    "SERVICE_TASK",
                    "System",
                    f"{str(node_uri)} (no topic configured)",
                )
            move_token_callback(instance_uri, token_uri, instance_id)
            return

        # Get loop index for multi-instance activities
        loop_idx = self._get_loop_index(token_uri)

        # Get multi-instance info for dataInput/dataOutput handling
        mi_info = get_multi_instance_info_callback(node_uri)

        # Get loop-scoped variables
        variables = get_variables_callback(instance_id, loop_idx, mi_info)

        try:
            updated_variables = execute_topic_callback(
                instance_id, topic, variables, loop_idx
            )

            # Store loop-scoped results
            if updated_variables:
                for name, value in updated_variables.items():
                    set_variable_callback(instance_id, name, value, loop_idx)

            if log_callback:
                log_callback(
                    instance_uri,
                    "SERVICE_TASK",
                    "System",
                    f"{str(node_uri)} (topic: {topic})",
                )

        except ValueError as e:
            logger.warning(str(e))
            if log_callback:
                log_callback(
                    instance_uri,
                    "SERVICE_TASK_SKIPPED",
                    "System",
                    f"{str(node_uri)} (topic: {topic}) - no handler",
                )

        except Exception as e:
            logger.error(f"Service task failed: {e}")
            self._instances.set((token_uri, INST.status, Literal("ERROR")))
            if log_callback:
                log_callback(
                    instance_uri,
                    "SERVICE_TASK_ERROR",
                    "System",
                    f"{str(node_uri)} (topic: {topic}): {str(e)}",
                )
            return

        move_token_callback(instance_uri, token_uri, instance_id)

    def _get_node_topic(self, node_uri: URIRef) -> Optional[str]:
        """Get the topic configured on a service task node."""
        # Try standard BPMN topic
        for _, _, o in self._definitions.triples((node_uri, BPMN.topic, None)):
            return str(o)

        # Try Camunda extension
        camunda_topic = URIRef("http://camunda.org/schema/1.0/bpmn#topic")
        for _, _, o in self._definitions.triples((node_uri, camunda_topic, None)):
            return str(o)

        return None

    def _get_loop_index(self, token_uri: URIRef) -> Optional[int]:
        """Get the loop index from a token."""
        loop_instance = self._instances.value(token_uri, INST.loopInstance)
        if loop_instance is not None:
            try:
                return int(str(loop_instance))
            except (ValueError, TypeError):
                pass
        return None

    # ==================== Script Task ====================

    def execute_script_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        get_variables_callback: Callable,
        set_variable_callback: Callable,
        move_token_callback: Callable,
        log_callback: Optional[Callable] = None,
        save_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute a script task.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the script task node
            instance_id: ID of the instance
            get_variables_callback: Callback to get instance variables
            set_variable_callback: Callback to set instance variables
            move_token_callback: Callback to move token to next node
            log_callback: Optional callback for logging events
            save_callback: Optional callback to save graph changes
        """
        # Get script format and code
        script_format = None
        script_code = None

        for _, _, o in self._definitions.triples((node_uri, BPMN.scriptFormat, None)):
            script_format = str(o)
            break

        for _, _, o in self._definitions.triples((node_uri, BPMN.script, None)):
            script_code = str(o)
            break

        node_id = str(node_uri).split("/")[-1]

        # Check if script content exists
        if not script_code:
            logger.warning(
                f"ScriptTask {node_id} has no script content - skipping execution"
            )
            if log_callback:
                log_callback(
                    instance_uri,
                    "SCRIPT_TASK_SKIPPED",
                    "System",
                    f"ScriptTask {node_id} - no script content",
                )
            move_token_callback(instance_uri, token_uri, instance_id)
            return

        # Check if script execution is enabled
        if not self._script_tasks_enabled:
            logger.info(
                f"ScriptTask {node_id} execution disabled by configuration - skipping"
            )
            if log_callback:
                log_callback(
                    instance_uri,
                    "SCRIPT_TASK_DISABLED",
                    "System",
                    f"ScriptTask {node_id} - script execution disabled",
                )
            move_token_callback(instance_uri, token_uri, instance_id)
            return

        logger.info(
            f"Executing ScriptTask {node_id} (format: {script_format or 'python'})"
        )
        if log_callback:
            log_callback(
                instance_uri,
                "SCRIPT_TASK_STARTED",
                "System",
                f"ScriptTask {node_id} started",
            )

        try:
            self._run_script(
                instance_id,
                script_code,
                script_format,
                get_variables_callback,
                set_variable_callback,
            )

            logger.info(f"ScriptTask {node_id} completed successfully")
            if log_callback:
                log_callback(
                    instance_uri,
                    "SCRIPT_TASK_COMPLETED",
                    "System",
                    f"ScriptTask {node_id} completed",
                )
        except Exception as e:
            logger.error(f"ScriptTask {node_id} failed: {e}")
            if log_callback:
                log_callback(
                    instance_uri,
                    "SCRIPT_TASK_ERROR",
                    "System",
                    f"ScriptTask {node_id} failed: {str(e)}",
                )
            self._instances.set((token_uri, INST.status, Literal("ERROR")))
            if save_callback:
                save_callback()
            return

        move_token_callback(instance_uri, token_uri, instance_id)

    def _run_script(
        self,
        instance_id: str,
        script_code: str,
        script_format: Optional[str],
        get_variables_callback: Callable,
        set_variable_callback: Callable,
    ) -> None:
        """Execute a Python script with access to process variables."""
        self._validate_script(script_code)
        variables = get_variables_callback(instance_id)

        local_vars = {"variables": dict(variables)}

        safe_builtins = {
            "print": print,
            "len": len,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "round": round,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "dict": dict,
            "list": list,
            "set": set,
            "tuple": tuple,
            "range": range,
            "enumerate": enumerate,
        }
        safe_globals = {"__builtins__": safe_builtins, "datetime": datetime}
        exec(script_code, safe_globals, local_vars)

        updated_vars = {
            k: v
            for k, v in local_vars.items()
            if k != "variables" and not k.startswith("_")
        }

        for name, value in updated_vars.items():
            set_variable_callback(instance_id, name, value)

    def _validate_script(self, script_code: str) -> None:
        """Reject unsafe syntax before executing a script."""
        tree = ast.parse(script_code, mode="exec")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise ValueError("Script imports are not allowed")
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                raise ValueError("Global/nonlocal statements are not allowed")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError("Dunder attribute access is not allowed")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise ValueError("Dunder names are not allowed")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"eval", "exec", "compile", "open", "input"}:
                    raise ValueError(f"Call to {node.func.id} is not allowed")

    # ==================== Event-Based Gateway ====================

    def execute_event_based_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        log_callback: Optional[Callable] = None,
    ) -> None:
        """
        Execute an event-based gateway.

        Event-based gateways wait for one of several possible events:
        - Message events (receive tasks)
        - Timer events

        The first event to trigger determines the path taken.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the event-based gateway node
            instance_id: ID of the instance
            log_callback: Optional callback for logging events
        """
        # Find outgoing sequence flows and their targets
        outgoing_targets = []
        for _, _, flow_uri in self._definitions.triples(
            (node_uri, BPMN.outgoing, None)
        ):
            for _, _, target in self._definitions.triples(
                (flow_uri, BPMN.targetRef, None)
            ):
                outgoing_targets.append((flow_uri, target))

        if not outgoing_targets:
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))
            return

        # Find waiting tasks (receive tasks with messages)
        waiting_tasks = []
        for flow_uri, target in outgoing_targets:
            target_type = None
            for _, _, o in self._definitions.triples((target, RDF.type, None)):
                target_type = o
                break

            if target_type in [BPMN.ReceiveTask, BPMN.receiveTask]:
                message_name = self._get_node_message_name(target)

                if message_name:
                    waiting_tasks.append(
                        {
                            "type": "message",
                            "target": target,
                            "message": message_name,
                        }
                    )
                else:
                    waiting_tasks.append({"type": "receive", "target": target})

        if waiting_tasks:
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

            # Create waiting tokens for each target
            for task_info in waiting_tasks:
                target = task_info["target"]
                existing_tokens = self._find_existing_tokens_at_node(
                    instance_uri, target
                )

                if not existing_tokens:
                    new_token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]
                    self._instances.add((new_token_uri, RDF.type, INST.Token))
                    self._instances.add((new_token_uri, INST.belongsTo, instance_uri))
                    self._instances.add(
                        (new_token_uri, INST.status, Literal("WAITING"))
                    )
                    self._instances.add((new_token_uri, INST.currentNode, target))
                    self._instances.add((instance_uri, INST.hasToken, new_token_uri))

            if log_callback:
                log_callback(
                    instance_uri,
                    "WAITING_FOR_EVENT",
                    "System",
                    f"Event-based gateway {node_uri} waiting for {len(waiting_tasks)} events",
                )

            logger.info(
                f"Event-based gateway at {node_uri}, created {len(waiting_tasks)} waiting tokens"
            )
        else:
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))
            logger.warning(
                f"Event-based gateway {node_uri} has no message/receive targets"
            )

    def _get_node_message_name(self, node_uri: URIRef) -> Optional[str]:
        """Get the message name configured on a node."""
        for _, _, o in self._definitions.triples((node_uri, BPMN.message, None)):
            return str(o)

        camunda_msg = URIRef("http://camunda.org/schema/1.0/bpmn#message")
        for _, _, o in self._definitions.triples((node_uri, camunda_msg, None)):
            return str(o)

        return None

    def _find_existing_tokens_at_node(
        self, instance_uri: URIRef, node_uri: URIRef
    ) -> List[URIRef]:
        """Find existing active or waiting tokens at a node."""
        existing_tokens = []
        for tok in self._instances.objects(instance_uri, INST.hasToken):
            current = self._instances.value(tok, INST.currentNode)
            if current != node_uri:
                continue
            status = self._instances.value(tok, INST.status)
            if status and str(status) in ["ACTIVE", "WAITING"]:
                existing_tokens.append(tok)
        return existing_tokens

    # ==================== Execution Listeners ====================

    def execute_execution_listeners(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        event: str,
        topic_handlers: Dict[str, Any],
        execute_listener_callback: Callable,
    ) -> None:
        """
        Execute all execution listeners for a specific event.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the node
            instance_id: ID of the instance
            event: The event type ("start" or "end")
            topic_handlers: Dictionary of registered topic handlers
            execute_listener_callback: Callback to execute a listener
        """
        for listener_uri in self._definitions.subjects(BPMN.listenerElement, node_uri):
            listener_type = self._definitions.value(listener_uri, RDF.type)
            if listener_type and "ExecutionListener" not in str(listener_type):
                continue

            listener_event = self._definitions.value(listener_uri, BPMN.listenerEvent)
            if listener_event and str(listener_event) != event:
                continue

            expression = self._definitions.value(listener_uri, BPMN.listenerExpression)
            if expression and str(expression) in topic_handlers:
                execute_listener_callback(
                    instance_uri,
                    node_uri,
                    instance_id,
                    str(expression),
                    "execution",
                    event,
                )

    def execute_task_listeners(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        event: str,
        topic_handlers: Dict[str, Any],
        execute_listener_callback: Callable,
    ) -> None:
        """
        Execute all task listeners for a specific event.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token
            node_uri: URI of the node
            instance_id: ID of the instance
            event: The event type ("create", "assignment", "complete", "delete")
            topic_handlers: Dictionary of registered topic handlers
            execute_listener_callback: Callback to execute a listener
        """
        for listener_uri in self._definitions.subjects(BPMN.listenerElement, node_uri):
            listener_type = self._definitions.value(listener_uri, RDF.type)
            if listener_type and "TaskListener" not in str(listener_type):
                continue

            listener_event = self._definitions.value(listener_uri, BPMN.listenerEvent)
            if listener_event and str(listener_event) != event:
                continue

            expression = self._definitions.value(listener_uri, BPMN.listenerExpression)
            if expression and str(expression) in topic_handlers:
                execute_listener_callback(
                    instance_uri,
                    node_uri,
                    instance_id,
                    str(expression),
                    "task",
                    event,
                )

    # ==================== Node Type Detection ====================

    def get_node_type(self, node_uri: URIRef) -> Optional[str]:
        """
        Get the BPMN type of a node.

        Args:
            node_uri: URI of the node

        Returns:
            String type name or None if not found
        """
        for _, _, o in self._definitions.triples((node_uri, RDF.type, None)):
            type_str = str(o)
            # Extract the type name from the URI
            if "#" in type_str:
                return type_str.split("#")[-1]
            elif "/" in type_str:
                return type_str.split("/")[-1]
        return None

    def is_end_event(self, node_uri: URIRef) -> bool:
        """Check if a node is an end event."""
        node_type = self.get_node_type(node_uri)
        if not node_type:
            return False
        return "EndEvent" in node_type or "endevent" in node_type.lower()

    def is_start_event(self, node_uri: URIRef) -> bool:
        """Check if a node is a start event."""
        node_type = self.get_node_type(node_uri)
        if not node_type:
            return False
        return "StartEvent" in node_type or "startevent" in node_type.lower()

    def is_gateway(self, node_uri: URIRef) -> bool:
        """Check if a node is a gateway."""
        node_type = self.get_node_type(node_uri)
        if not node_type:
            return False
        return "Gateway" in node_type or "gateway" in node_type.lower()

    def is_task(self, node_uri: URIRef) -> bool:
        """Check if a node is a task."""
        node_type = self.get_node_type(node_uri)
        if not node_type:
            return False
        return "Task" in node_type or "task" in node_type.lower()

    def is_subprocess(self, node_uri: URIRef) -> bool:
        """Check if a node is a subprocess."""
        node_type = self.get_node_type(node_uri)
        if not node_type:
            return False
        return "SubProcess" in node_type or "subprocess" in node_type.lower()

    # ==================== Helpers ====================

    def get_outgoing_targets(self, node_uri: URIRef) -> List[URIRef]:
        """Get target nodes from outgoing sequence flows."""
        targets = []
        for flow_uri in self._definitions.objects(node_uri, BPMN.outgoing):
            target = self._definitions.value(flow_uri, BPMN.targetRef)
            if target:
                targets.append(target)
        return targets

    def get_incoming_sources(self, node_uri: URIRef) -> List[URIRef]:
        """Get source nodes from incoming sequence flows."""
        sources = []
        for flow_uri in self._definitions.objects(node_uri, BPMN.incoming):
            source = self._definitions.value(flow_uri, BPMN.sourceRef)
            if source:
                sources.append(source)
        return sources
