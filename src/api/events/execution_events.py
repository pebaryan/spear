# Execution Events for SPEAR Engine
# Event classes for the event-driven execution architecture

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from rdflib import URIRef


@dataclass
class ExecutionEvent:
    """Base class for all execution events.

    Events are used to decouple node handlers from other services.
    Handlers publish events, and services subscribe to handle them.
    """

    pass


@dataclass
class TokenMovedEvent(ExecutionEvent):
    """Fired when a token should move to the next node(s).

    The token handler subscribes to this event to perform the actual
    token movement in the RDF graph.
    """

    token_uri: URIRef
    target_nodes: List[URIRef]
    instance_uri: URIRef
    consume_token: bool = True  # Whether to consume the original token


@dataclass
class TokenCreatedEvent(ExecutionEvent):
    """Fired when a new token should be created.

    Used for parallel gateways and multi-instance activities
    where multiple tokens need to be spawned.
    """

    instance_uri: URIRef
    node_uri: URIRef
    parent_token_uri: Optional[URIRef] = None
    loop_index: Optional[int] = None


@dataclass
class TokenConsumedEvent(ExecutionEvent):
    """Fired when a token should be consumed/removed.

    Used when tokens merge at gateways or when execution
    reaches an end event.
    """

    token_uri: URIRef
    instance_uri: URIRef


@dataclass
class TaskCreatedEvent(ExecutionEvent):
    """Fired when a user task needs to be created.

    The task repository subscribes to this event to create
    the task in the tasks graph.
    """

    instance_uri: URIRef
    node_uri: URIRef
    token_uri: URIRef
    task_name: str
    assignee: Optional[str] = None
    candidate_users: List[str] = field(default_factory=list)
    candidate_groups: List[str] = field(default_factory=list)
    form_data: Dict[str, Any] = field(default_factory=dict)
    due_date: Optional[str] = None
    priority: Optional[int] = None


@dataclass
class TaskCompletedEvent(ExecutionEvent):
    """Fired when a user task has been completed.

    Triggers the instance to resume execution from the task node.
    """

    task_id: str
    instance_uri: URIRef
    node_uri: URIRef
    token_uri: URIRef
    completed_by: str
    variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VariableSetEvent(ExecutionEvent):
    """Fired when a variable should be set on an instance.

    The variables service subscribes to this to update the
    instance graph.
    """

    instance_uri: URIRef
    name: str
    value: Any
    datatype: Optional[URIRef] = None
    loop_index: Optional[int] = None


@dataclass
class MessageSentEvent(ExecutionEvent):
    """Fired when a message should be sent.

    The message handler subscribes to this to deliver messages
    to waiting receive tasks or message start events.
    """

    message_name: str
    correlation_key: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    source_instance_uri: Optional[URIRef] = None
    source_node_uri: Optional[URIRef] = None


@dataclass
class MessageReceivedEvent(ExecutionEvent):
    """Fired when a message has been received by a waiting task.

    Triggers the instance to resume execution.
    """

    instance_uri: URIRef
    node_uri: URIRef
    token_uri: URIRef
    message_name: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorThrownEvent(ExecutionEvent):
    """Fired when an error is thrown during execution.

    The error handler subscribes to this to find and trigger
    appropriate error boundary events.
    """

    instance_uri: URIRef
    source_node_uri: URIRef
    error_code: str
    error_message: str = ""
    token_uri: Optional[URIRef] = None


@dataclass
class CompensationTriggeredEvent(ExecutionEvent):
    """Fired when compensation should be triggered.

    The compensation handler subscribes to this to execute
    compensation activities.
    """

    instance_uri: URIRef
    activity_uri: Optional[URIRef] = None  # None means compensate all
    source_node_uri: Optional[URIRef] = None


@dataclass
class CancelTriggeredEvent(ExecutionEvent):
    """Fired when a transaction should be cancelled.

    The cancel handler subscribes to this to terminate the
    transaction subprocess and trigger cancel boundary events.
    """

    instance_uri: URIRef
    transaction_uri: URIRef
    source_node_uri: Optional[URIRef] = None


@dataclass
class TerminateTriggeredEvent(ExecutionEvent):
    """Fired when the entire process instance should terminate.

    All tokens are consumed and the instance is marked as terminated.
    """

    instance_uri: URIRef
    source_node_uri: Optional[URIRef] = None


@dataclass
class ServiceTaskExecuteEvent(ExecutionEvent):
    """Fired when a service task should execute its handler.

    The topic registry subscribes to this to execute the
    registered handler for the task's topic.
    """

    instance_uri: URIRef
    node_uri: URIRef
    token_uri: URIRef
    topic: str
    input_variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceTaskCompletedEvent(ExecutionEvent):
    """Fired when a service task handler has completed.

    Contains output variables to be set on the instance.
    """

    instance_uri: URIRef
    node_uri: URIRef
    token_uri: URIRef
    output_variables: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubprocessStartedEvent(ExecutionEvent):
    """Fired when a subprocess should start execution.

    Used for expanded subprocesses and call activities.
    """

    instance_uri: URIRef
    subprocess_uri: URIRef
    parent_token_uri: URIRef
    input_variables: Dict[str, Any] = field(default_factory=dict)
    loop_index: Optional[int] = None


@dataclass
class SubprocessCompletedEvent(ExecutionEvent):
    """Fired when a subprocess has completed execution.

    Triggers the parent process to continue.
    """

    instance_uri: URIRef
    subprocess_uri: URIRef
    parent_token_uri: URIRef
    output_variables: Dict[str, Any] = field(default_factory=dict)
    loop_index: Optional[int] = None


@dataclass
class BoundaryEventTriggeredEvent(ExecutionEvent):
    """Fired when a boundary event should be triggered.

    Used for timer, message, error, and other boundary events.
    """

    instance_uri: URIRef
    boundary_event_uri: URIRef
    attached_to_uri: URIRef
    is_interrupting: bool = True
    event_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditLogEvent(ExecutionEvent):
    """Fired when an audit log entry should be created.

    The audit repository subscribes to this to record the event.
    """

    instance_uri: URIRef
    event_type: str
    node_uri: Optional[URIRef] = None
    details: Dict[str, Any] = field(default_factory=dict)
    user: Optional[str] = None


@dataclass
class InstanceStateChangedEvent(ExecutionEvent):
    """Fired when an instance's state changes.

    Used to track instance lifecycle (started, completed, failed, etc.)
    """

    instance_uri: URIRef
    old_state: Optional[str] = None
    new_state: str = ""
    reason: Optional[str] = None


@dataclass
class GatewayEvaluatedEvent(ExecutionEvent):
    """Fired when a gateway has been evaluated.

    Contains the results of condition evaluation for routing.
    """

    instance_uri: URIRef
    gateway_uri: URIRef
    token_uri: URIRef
    selected_flows: List[URIRef] = field(default_factory=list)
    gateway_type: str = ""  # exclusive, parallel, inclusive, event-based


@dataclass
class ListenerExecuteEvent(ExecutionEvent):
    """Fired when an execution or task listener should run.

    Listeners are hooks that run at specific points in task/execution lifecycle.
    """

    instance_uri: URIRef
    node_uri: URIRef
    listener_type: str  # 'start', 'end', 'take', 'create', 'assignment', 'complete'
    listener_class: Optional[str] = None
    listener_expression: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)
