# Storage Facade for SPEAR Engine
# Wires together all extracted modules into a unified interface

import logging
from typing import Dict, Any, List, Optional, Callable

from rdflib import Graph, URIRef

from src.api.storage.base import BaseStorageService, INST, BPMN
from src.api.storage.process_repository import ProcessRepository
from src.api.storage.instance_repository import InstanceRepository
from src.api.storage.task_repository import TaskRepository
from src.api.storage.audit_repository import AuditRepository
from src.api.storage.variables import VariablesService

from src.api.execution.engine import ExecutionEngine
from src.api.execution.gateway_evaluator import GatewayEvaluator
from src.api.execution.token_handler import TokenHandler
from src.api.execution.multi_instance import MultiInstanceHandler
from src.api.execution.error_handler import ErrorHandler
from src.api.execution.node_handlers import NodeHandlers

from src.api.messaging.topic_registry import TopicRegistry
from src.api.messaging.message_handler import MessageHandler

from src.api.events.event_bus import ExecutionEventBus

logger = logging.getLogger(__name__)


class StorageFacade(BaseStorageService):
    """
    Unified facade that wires together all storage and execution modules.

    This facade provides backward-compatible access to all functionality
    while internally delegating to specialized modules. It serves as the
    main entry point for the SPEAR engine.

    Components:
    - ProcessRepository: Process definition CRUD
    - InstanceRepository: Instance lifecycle management
    - TaskRepository: User task management
    - AuditRepository: Audit log persistence
    - VariablesService: Variable management with loop-scoping
    - ExecutionEngine: Main execution orchestration
    - GatewayEvaluator: Gateway condition evaluation
    - TokenHandler: Token movement and flow control
    - MultiInstanceHandler: Multi-instance activity handling
    - ErrorHandler: Error/cancel/terminate/compensation events
    - NodeHandlers: Service/script tasks, event gateways
    - TopicRegistry: Service task handler registration
    - MessageHandler: Message sending/receiving/routing
    - EventBus: Event-driven architecture support
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize the storage facade and all components.

        Args:
            data_dir: Directory for persisting data
        """
        # Initialize base storage which sets up graphs
        super().__init__(data_dir)

        # Initialize event bus
        self._event_bus = ExecutionEventBus()

        # Initialize repositories/services - these expect BaseStorageService (self)
        self._process_repo = ProcessRepository(self)
        self._task_repo = TaskRepository(self)
        self._audit_repo = AuditRepository(self)
        self._variables_service = VariablesService(self)

        # Initialize instance repository with direct graph access
        self._instance_repo = InstanceRepository(
            self._definitions_graph,
            self._instances_graph,
            self._audit_graph,
            data_dir,
        )

        # Initialize messaging components
        self._topic_registry = TopicRegistry()

        self._message_handler = MessageHandler(
            self._definitions_graph,
            self._instances_graph,
        )

        # Initialize execution components
        self._execution_engine = ExecutionEngine(
            self._definitions_graph,
            self._instances_graph,
        )

        self._gateway_evaluator = GatewayEvaluator(
            self._definitions_graph,
            self._instances_graph,
        )

        self._token_handler = TokenHandler(
            self._definitions_graph,
            self._instances_graph,
        )

        self._multi_instance = MultiInstanceHandler(
            self._definitions_graph,
            self._instances_graph,
        )

        self._error_handler = ErrorHandler(
            self._definitions_graph,
            self._instances_graph,
        )

        self._node_handlers = NodeHandlers(
            self._definitions_graph,
            self._instances_graph,
        )

        logger.info(f"StorageFacade initialized with data_dir: {data_dir}")

    # ==================== Properties for Component Access ====================

    @property
    def definitions_graph(self) -> Graph:
        """Access the definitions graph."""
        return self._definitions_graph

    @property
    def instances_graph(self) -> Graph:
        """Access the instances graph."""
        return self._instances_graph

    @property
    def audit_graph(self) -> Graph:
        """Access the audit graph."""
        return self._audit_graph

    @property
    def event_bus(self) -> ExecutionEventBus:
        """Access the event bus."""
        return self._event_bus

    @property
    def process_repository(self) -> ProcessRepository:
        """Access the process repository."""
        return self._process_repo

    @property
    def instance_repository(self) -> InstanceRepository:
        """Access the instance repository."""
        return self._instance_repo

    @property
    def task_repository(self) -> TaskRepository:
        """Access the task repository."""
        return self._task_repo

    @property
    def audit_repository(self) -> AuditRepository:
        """Access the audit repository."""
        return self._audit_repo

    @property
    def variables_service(self) -> VariablesService:
        """Access the variables service."""
        return self._variables_service

    @property
    def topic_registry(self) -> TopicRegistry:
        """Access the topic registry."""
        return self._topic_registry

    @property
    def message_handler(self) -> MessageHandler:
        """Access the message handler."""
        return self._message_handler

    @property
    def execution_engine(self) -> ExecutionEngine:
        """Access the execution engine."""
        return self._execution_engine

    @property
    def gateway_evaluator(self) -> GatewayEvaluator:
        """Access the gateway evaluator."""
        return self._gateway_evaluator

    @property
    def token_handler(self) -> TokenHandler:
        """Access the token handler."""
        return self._token_handler

    @property
    def multi_instance_handler(self) -> MultiInstanceHandler:
        """Access the multi-instance handler."""
        return self._multi_instance

    @property
    def error_handler(self) -> ErrorHandler:
        """Access the error handler."""
        return self._error_handler

    @property
    def node_handlers(self) -> NodeHandlers:
        """Access the node handlers."""
        return self._node_handlers

    # ==================== Process Definition Operations ====================

    def deploy_process(
        self,
        name: str,
        bpmn_content: str,
        description: Optional[str] = None,
        version: str = "1.0",
    ) -> str:
        """
        Deploy a process definition.

        Args:
            name: Human-readable process name
            bpmn_content: BPMN XML content
            description: Optional process description
            version: Process version

        Returns:
            The generated process definition ID
        """
        return self._process_repo.deploy(name, bpmn_content, description, version)

    def get_process(self, process_id: str) -> Optional[Dict[str, Any]]:
        """Get a process definition by ID."""
        return self._process_repo.get(process_id)

    def list_processes(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List all process definitions."""
        return self._process_repo.list(status, page, page_size)

    def delete_process(self, process_id: str) -> bool:
        """Delete a process definition."""
        return self._process_repo.delete(process_id)

    def update_process(
        self,
        process_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a process definition."""
        return self._process_repo.update(process_id, name, description, status)

    def get_process_graph(self, process_id: str) -> Optional[Graph]:
        """Get the RDF graph for a specific process."""
        return self._process_repo.get_graph(process_id)

    # ==================== Instance Operations ====================

    def create_instance(
        self,
        process_id: str,
        variables: Optional[Dict[str, Any]] = None,
        start_event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and start a new process instance."""

        # Create callback for logging events
        def log_callback(instance_uri, event, user, details):
            self._audit_repo.log_event(instance_uri, event, user, details)

        # Create callback for executing the instance
        def execute_callback(instance_uri, instance_id):
            self._execute_instance(instance_uri, instance_id)

        return self._instance_repo.create_instance(
            process_id,
            variables,
            start_event_id,
            execute_callback=execute_callback,
            log_callback=log_callback,
        )

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get a process instance by ID."""
        return self._instance_repo.get_instance(instance_id)

    def list_instances(
        self,
        process_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List process instances."""
        return self._instance_repo.list_instances(process_id, status, page, page_size)

    def stop_instance(
        self, instance_id: str, reason: str = "User request"
    ) -> Dict[str, Any]:
        """Stop a running process instance."""

        def log_callback(instance_uri, event, user, details):
            self._audit_repo.log_event(instance_uri, event, user, details)

        return self._instance_repo.stop_instance(
            instance_id, reason, log_callback=log_callback
        )

    def cancel_instance(
        self, instance_id: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cancel a process instance."""

        def log_callback(instance_uri, event, user, details):
            self._audit_repo.log_event(instance_uri, event, user, details)

        return self._instance_repo.cancel_instance(
            instance_id, reason, log_callback=log_callback
        )

    # ==================== Variable Operations ====================

    def get_instance_variables(
        self,
        instance_id: str,
        loop_idx: Optional[int] = None,
        mi_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get variables for a process instance."""
        return self._variables_service.get_variables(instance_id, loop_idx, mi_info)

    def set_instance_variable(
        self,
        instance_id: str,
        name: str,
        value: Any,
        loop_idx: Optional[int] = None,
    ) -> bool:
        """Set a variable on a process instance."""
        return self._variables_service.set_variable(instance_id, name, value, loop_idx)

    # ==================== Task Operations ====================

    def list_tasks(
        self,
        instance_id: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """List user tasks."""
        return self._task_repo.list(instance_id, status, assignee, page, page_size)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID."""
        return self._task_repo.get(task_id)

    def complete_task(
        self,
        task_id: str,
        user_id: str = "System",
        variables: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Complete a user task."""
        # Get task details first
        task = self._task_repo.get(task_id)
        if not task:
            return False

        # Set variables if provided
        if variables:
            instance_id = task.get("instance_id")
            if instance_id:
                for name, value in variables.items():
                    self._variables_service.set_variable(instance_id, name, value)

        # Complete the task
        result = self._task_repo.complete(task_id, user_id, variables)
        if not result:
            return False

        # Resume instance execution - this finds the waiting token and moves it
        self.resume_instance_from_task(task_id)

        return True

    def claim_task(self, task_id: str, assignee: str) -> Optional[Dict[str, Any]]:
        """Claim a task for an assignee."""
        return self._task_repo.claim(task_id, assignee)

    def assign_task(
        self, task_id: str, assignee: str, assigner: str = "System"
    ) -> Optional[Dict[str, Any]]:
        """Assign a task to a user."""
        return self._task_repo.assign(task_id, assignee, assigner)

    def resume_instance_from_task(self, task_id: str) -> bool:
        """After task completion, resume the instance by moving the token."""
        from rdflib import Literal

        task_data = self._task_repo.get(task_id)
        if not task_data or task_data["status"] != "COMPLETED":
            return False

        instance_id = task_data["instance_id"]
        node_uri = task_data["node_uri"]

        if not instance_id or not node_uri:
            return False

        instance_uri = INST[instance_id]

        # Find the token waiting at this node
        for token_uri in self._instances_graph.objects(instance_uri, INST.hasToken):
            token_status = self._instances_graph.value(token_uri, INST.status)
            if token_status and str(token_status) == "WAITING":
                token_node = self._instances_graph.value(token_uri, INST.currentNode)
                if token_node and str(token_node) == node_uri:
                    # Set token to ACTIVE before moving
                    self._instances_graph.set(
                        (URIRef(token_uri), INST.status, Literal("ACTIVE"))
                    )

                    # Move token to next node
                    self._execution_engine.move_token_to_next(
                        instance_uri, URIRef(token_uri), instance_id
                    )
                    self._save_graph(self._instances_graph, "instances.ttl")
                    logger.info(f"Resumed instance {instance_id} after task {task_id}")

                    # Continue execution
                    self._execute_instance(instance_uri, instance_id)
                    return True

        return False

    # ==================== Audit Operations ====================

    def get_instance_audit_log(self, instance_id: str) -> List[Dict[str, Any]]:
        """Get the audit log for an instance."""
        return self._audit_repo.get_instance_audit_log(instance_id)

    # ==================== Service Task Registration ====================

    def register_service_task_handler(
        self,
        topic: str,
        handler: Callable,
        description: str = "",
        async_execution: bool = False,
    ) -> bool:
        """Register a handler for a service task topic."""
        return self._topic_registry.register(
            topic, handler, description, async_execution
        )

    def unregister_service_task_handler(self, topic: str) -> bool:
        """Unregister a service task handler."""
        return self._topic_registry.unregister(topic)

    def get_service_task_handler(self, topic: str) -> Optional[Callable]:
        """Get a registered service task handler."""
        if self._topic_registry.exists(topic):
            # Access the internal _handlers dict to get the function
            # Note: This is an internal access, consider adding a proper method
            return self._topic_registry._handlers[topic].get("function")
        return None

    # ==================== Message Operations ====================

    def send_message(
        self,
        message_name: str,
        correlation_key: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a message to a process instance."""
        # TODO: Implement with message_handler
        return {
            "status": "not_implemented",
            "message_name": message_name,
            "correlation_key": correlation_key,
        }

    # ==================== Internal Execution ====================

    def _execute_instance(self, instance_uri: URIRef, instance_id: str) -> None:
        """
        Execute a process instance by processing all active tokens.

        This method orchestrates the execution by calling the execution engine
        with appropriate callbacks for saving and logging.
        """

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def node_executor(inst_uri, token_uri, inst_id, merged_gateways):
            self._execute_token(inst_uri, token_uri, inst_id, merged_gateways)

        self._execution_engine.execute_instance(
            instance_uri,
            instance_id,
            node_executor=node_executor,
            save_callback=save_callback,
            log_callback=log_callback,
        )

    def _execute_token(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """
        Execute a single token through the process.

        This method determines the node type and dispatches to the appropriate
        handler.
        """
        current_node = self._instances_graph.value(token_uri, INST.currentNode)
        if not current_node:
            return

        # Get node types (cast to URIRef for type safety)
        node_types = self._execution_engine.get_node_types(URIRef(current_node))
        node_category = self._execution_engine.categorize_node(node_types)

        # Build handlers dictionary
        handlers = {
            "start_event": self._handle_start_event,
            "end_event": self._handle_end_event,
            "message_end_event": self._handle_message_end_event,
            "service_task": self._handle_service_task,
            "user_task": self._handle_user_task,
            "exclusive_gateway": self._handle_exclusive_gateway,
            "parallel_gateway": self._handle_parallel_gateway,
            "inclusive_gateway": self._handle_inclusive_gateway,
            "event_based_gateway": self._handle_event_based_gateway,
            "script_task": self._handle_script_task,
            "receive_task": self._handle_receive_task,
            "boundary_event": self._handle_boundary_event,
            "error_end_event": self._handle_error_end_event,
            "cancel_end_event": self._handle_cancel_end_event,
            "compensation_end_event": self._handle_compensation_end_event,
            "terminate_end_event": self._handle_terminate_end_event,
            # Add more handlers as needed
        }

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        self._execution_engine.execute_token(
            instance_uri,
            token_uri,
            instance_id,
            merged_gateways,
            handlers=handlers,
            log_callback=log_callback,
            save_callback=save_callback,
        )

    # ==================== Node Handlers ====================

    def _handle_start_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle start event - move to next node."""
        self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)

    def _handle_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle end event - consume token."""
        self._execution_engine.consume_token(token_uri)

    def _handle_message_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle message end event - trigger message and consume token."""
        message_name = self._definitions_graph.value(node_uri, BPMN.messageRef)
        if not message_name:
            camunda_msg = URIRef("http://camunda.org/schema/1.0/bpmn#message")
            message_name = self._definitions_graph.value(node_uri, camunda_msg)

        if message_name:
            self._audit_repo.log_event(
                instance_uri,
                "MESSAGE_END_EVENT",
                "System",
                f"Message end event triggered: {message_name}",
            )
            self._message_handler.trigger_message_end_event(
                instance_uri,
                str(message_name),
                log_callback=self._audit_repo.log_event,
            )

        self._audit_repo.log_event(instance_uri, "END", "System", str(node_uri))
        self._execution_engine.consume_token(token_uri)

    def _handle_service_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle service task - execute handler and move to next."""
        from rdflib import Literal

        # Get topic from node definition
        topic = self._definitions_graph.value(node_uri, BPMN.topic)
        if not topic:
            # Try Camunda namespace
            camunda_topic = URIRef("http://camunda.org/schema/1.0/bpmn#topic")
            topic = self._definitions_graph.value(node_uri, camunda_topic)

        if not topic:
            # No topic configured - log and move on
            self._audit_repo.log_event(
                instance_uri,
                "SERVICE_TASK",
                "System",
                f"{str(node_uri)} (no topic configured)",
            )
            self._execution_engine.move_token_to_next(
                instance_uri, token_uri, instance_id
            )
            return

        topic_str = str(topic)

        # Get loop index for multi-instance activities
        loop_idx = None
        loop_instance = self._instances_graph.value(token_uri, INST.loopInstance)
        if loop_instance:
            try:
                loop_idx = int(str(loop_instance))
            except ValueError:
                pass

        # Get variables (with loop scoping if applicable)
        variables = self._variables_service.get_variables(instance_id, loop_idx)

        try:
            # Execute the service task handler
            updated_variables = self._execute_service_task_handler(
                instance_id, topic_str, variables, loop_idx
            )

            # Store updated variables (with loop scoping)
            if updated_variables:
                for name, value in updated_variables.items():
                    self._variables_service.set_variable(
                        instance_id, name, value, loop_idx
                    )

            self._audit_repo.log_event(
                instance_uri,
                "SERVICE_TASK",
                "System",
                f"{str(node_uri)} (topic: {topic_str})",
            )

        except ValueError as e:
            # No handler registered
            logger.warning(str(e))
            self._audit_repo.log_event(
                instance_uri,
                "SERVICE_TASK_SKIPPED",
                "System",
                f"{str(node_uri)} (topic: {topic_str}) - no handler",
            )

        except Exception as e:
            logger.error(f"Service task failed: {e}")
            self._instances_graph.set((token_uri, INST.status, Literal("ERROR")))
            self._audit_repo.log_event(
                instance_uri,
                "SERVICE_TASK_ERROR",
                "System",
                f"{str(node_uri)} (topic: {topic_str}): {str(e)}",
            )
            return

        # Move to next node
        self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)

    def _execute_service_task_handler(
        self,
        instance_id: str,
        topic: str,
        variables: Dict[str, Any],
        loop_idx: Optional[int] = None,
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
        if not self._topic_registry.exists(topic):
            raise ValueError(f"No handler registered for topic: {topic}")

        handler_info = self._topic_registry.get(topic)
        handler_function = handler_info["function"]

        logger.info(f"Executing service task {topic} for instance {instance_id}")

        try:
            # Execute the handler with loop_idx support
            updated_variables = handler_function(instance_id, variables, loop_idx)
            logger.info(f"Service task {topic} completed for instance {instance_id}")
            return updated_variables

        except TypeError:
            # Handler doesn't support loop_idx, try without it
            logger.debug(
                f"Handler for {topic} doesn't support loop_idx, trying without it"
            )
            updated_variables = handler_function(instance_id, variables)
            logger.info(f"Service task {topic} completed for instance {instance_id}")
            return updated_variables

    def _handle_user_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle user task - create task and wait."""
        # Create task record using task repository's create method
        self._task_repo.create(instance_id, node_uri)

        # Set token to waiting
        self._execution_engine.set_token_waiting(token_uri)

    def _handle_exclusive_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle exclusive gateway - evaluate conditions."""

        def evaluate_callback(
            inst_uri: URIRef, gateway_uri: URIRef
        ) -> Optional[URIRef]:
            # GatewayEvaluator.evaluate_exclusive_gateway gets variables internally
            return self._gateway_evaluator.evaluate_exclusive_gateway(
                inst_uri, gateway_uri
            )

        def log_callback(inst_uri: URIRef, event: str, user: str, details: str) -> None:
            self._audit_repo.log_event(inst_uri, event, user, details)

        self._execution_engine.handle_exclusive_gateway(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            evaluate_callback,
            log_callback,
        )

    def _handle_parallel_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle parallel gateway - fork or join."""

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        # Check if this is a join (merge) or fork (split)
        incoming_count = self._execution_engine.count_incoming_flows(node_uri)

        if incoming_count > 1:
            if node_uri in merged_gateways:
                self._execution_engine.consume_token(token_uri)
                return

            waiting_count = self._execution_engine.count_waiting_tokens_at_gateway(
                instance_uri, node_uri
            )

            if waiting_count < incoming_count:
                self._execution_engine.set_token_waiting(token_uri)
                return

            merged_gateways.add(node_uri)
            next_nodes = self._execution_engine.get_outgoing_targets(node_uri)
            if not next_nodes:
                for tok in self._instances_graph.objects(instance_uri, INST.hasToken):
                    if self._instances_graph.value(tok, INST.currentNode) == node_uri:
                        self._execution_engine.consume_token(tok)
                return

            merged_token = self._token_handler.merge_parallel_tokens(
                instance_uri, node_uri, instance_id, next_nodes[0]
            )
            for additional_target in next_nodes[1:]:
                self._execution_engine.create_token(
                    instance_uri, additional_target, instance_id
                )

            if log_callback:
                log_callback(
                    instance_uri,
                    "PARALLEL_GATEWAY_MERGE",
                    "System",
                    f"Parallel gateway {str(node_uri)} merged to {len(next_nodes)} paths",
                )
            return

        # Fork or single path
        self._execution_engine.handle_parallel_gateway(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            log_callback,
        )

    def _handle_inclusive_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle inclusive gateway - evaluate conditions and merge when needed."""
        outgoing_flows = []
        for flow_uri in self._definitions_graph.objects(node_uri, BPMN.outgoing):
            target = self._definitions_graph.value(flow_uri, BPMN.targetRef)
            if target:
                outgoing_flows.append((flow_uri, target))

        if not outgoing_flows:
            self._execution_engine.consume_token(token_uri)
            return

        incoming_count = self._execution_engine.count_incoming_flows(node_uri)
        if incoming_count > 1:
            if node_uri in merged_gateways:
                self._execution_engine.consume_token(token_uri)
                return

            waiting_count = self._execution_engine.count_waiting_tokens_at_gateway(
                instance_uri, node_uri
            )
            if waiting_count < incoming_count:
                self._execution_engine.set_token_waiting(token_uri)
                return

            merged_gateways.add(node_uri)
            matching_targets = self._gateway_evaluator.evaluate_inclusive_gateway(
                instance_uri, node_uri
            )
            if not matching_targets:
                for tok in self._instances_graph.objects(instance_uri, INST.hasToken):
                    if self._instances_graph.value(tok, INST.currentNode) == node_uri:
                        self._execution_engine.consume_token(tok)
                return

            self._token_handler.merge_inclusive_tokens(
                instance_uri, node_uri, instance_id, matching_targets
            )
            return

        matching_targets = self._gateway_evaluator.evaluate_inclusive_gateway(
            instance_uri, node_uri
        )
        if not matching_targets:
            self._execution_engine.consume_token(token_uri)
            return

        self._execution_engine.set_token_current_node(token_uri, matching_targets[0])
        for additional_target in matching_targets[1:]:
            self._execution_engine.create_token(
                instance_uri, additional_target, instance_id
            )

    def _handle_event_based_gateway(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle event-based gateway - wait for the first event to occur."""

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        self._node_handlers.execute_event_based_gateway(
            instance_uri, token_uri, node_uri, instance_id, log_callback=log_callback
        )

    def _handle_script_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle script task - execute in safe sandbox if enabled."""

        def get_vars(inst_id):
            return self._variables_service.get_variables(inst_id)

        def set_var(inst_id, name, value):
            return self._variables_service.set_variable(inst_id, name, value)

        def move_token(inst_uri, tok_uri, inst_id):
            self._execution_engine.move_token_to_next(inst_uri, tok_uri, inst_id)

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        self._node_handlers.execute_script_task(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            get_variables_callback=get_vars,
            set_variable_callback=set_var,
            move_token_callback=move_token,
            log_callback=log_callback,
            save_callback=save_callback,
        )

    def _handle_receive_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle receive task - wait for a message."""
        message_name = None
        for _, _, o in self._definitions_graph.triples((node_uri, BPMN.message, None)):
            message_name = str(o)
            break
        if not message_name:
            camunda_msg = URIRef("http://camunda.org/schema/1.0/bpmn#message")
            for _, _, o in self._definitions_graph.triples((node_uri, camunda_msg, None)):
                message_name = str(o)
                break

        if message_name:
            self._execution_engine.set_token_waiting(token_uri)
            self._audit_repo.log_event(
                instance_uri,
                "WAITING_FOR_MESSAGE",
                "System",
                f"Waiting for message '{message_name}' at {node_uri}",
            )
        else:
            self._audit_repo.log_event(
                instance_uri,
                "RECEIVE_TASK",
                "System",
                f"{str(node_uri)} (no message configured)",
            )
            self._execution_engine.consume_token(token_uri)

    def _handle_boundary_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle boundary events via error handler."""

        def move_token(inst_uri, tok_uri, inst_id):
            self._execution_engine.move_token_to_next(inst_uri, tok_uri, inst_id)

        def execute_token(inst_uri, tok_uri, inst_id):
            self._execute_token(inst_uri, tok_uri, inst_id, merged_gateways)

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        self._error_handler.execute_boundary_event(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            move_token_callback=move_token,
            execute_token_callback=execute_token,
            log_callback=log_callback,
            save_callback=save_callback,
        )

    def _handle_error_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle error end event via error handler."""

        def set_var(inst_id, name, value):
            self._variables_service.set_variable(inst_id, name, value)

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        self._error_handler.execute_error_end_event(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            set_variable_callback=set_var,
            log_callback=log_callback,
            save_callback=save_callback,
        )

    def _handle_cancel_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle cancel end event via error handler."""

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        self._error_handler.execute_cancel_end_event(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            log_callback=log_callback,
            save_callback=save_callback,
        )

    def _handle_compensation_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle compensation end event via error handler."""

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        self._error_handler.execute_compensation_end_event(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            log_callback=log_callback,
            save_callback=save_callback,
        )

    def _handle_terminate_end_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle terminate end event via error handler."""

        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def save_callback():
            self._save_graph(self._instances_graph, "instances.ttl")

        self._error_handler.execute_terminate_end_event(
            instance_uri,
            token_uri,
            node_uri,
            instance_id,
            log_callback=log_callback,
            save_callback=save_callback,
        )

    # ==================== Persistence ====================

    def save(self) -> None:
        """Save all graphs to disk."""
        self._save_graph(self._definitions_graph, "definitions.ttl")
        self._save_graph(self._instances_graph, "instances.ttl")
        self._save_graph(self._audit_graph, "audit.ttl")

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get system statistics.

        Returns:
            Dictionary with process_count, instance_count, total_triples
        """
        from rdflib import RDF
        from src.api.storage.base import PROC, INST

        # Count processes
        process_count = len(
            list(self._definitions_graph.subjects(RDF.type, PROC.ProcessDefinition))
        )

        # Count instances
        instance_count = len(
            list(self._instances_graph.subjects(RDF.type, INST.ProcessInstance))
        )

        # Count RDF triples
        triple_count = (
            len(self._definitions_graph)
            + len(self._instances_graph)
            + len(self._audit_graph)
        )

        return {
            "process_count": process_count,
            "instance_count": instance_count,
            "total_triples": triple_count,
        }


# Global facade instance for sharing across modules
_shared_facade: Optional[StorageFacade] = None


def get_facade(data_dir: str = "data") -> StorageFacade:
    """Get or create the shared storage facade instance."""
    global _shared_facade
    if _shared_facade is None:
        _shared_facade = StorageFacade(data_dir)
    return _shared_facade


def reset_facade() -> None:
    """Reset the shared facade (useful for testing)."""
    global _shared_facade
    _shared_facade = None
