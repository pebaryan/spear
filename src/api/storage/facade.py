# Storage Facade for SPEAR Engine
# Wires together all extracted modules into a unified interface

import logging
import os
import contextlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable

from rdflib import Graph, URIRef, RDF, Literal

from src.api.storage.base import BaseStorageService, INST, BPMN, PROC
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

try:
    import fcntl
except Exception:  # pragma: no cover - non-posix platforms
    fcntl = None


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

    def __init__(self, data_dir: str = "data/spear_rdf"):
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

    # ==================== Timer Jobs ====================

    @contextlib.contextmanager
    def _timer_jobs_lock(self):
        """Serialize timer claim/finalize updates across workers."""
        lock_path = os.path.join(self.storage_path, "timer_jobs.lock")
        os.makedirs(self.storage_path, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _refresh_instances_graph_from_disk(self) -> None:
        """Refresh instances graph in place to keep component references valid."""
        latest = self._load_graph("instances.ttl")
        self._instances_graph.remove((None, None, None))
        for triple in latest:
            self._instances_graph.add(triple)

    def _claim_due_timer_jobs(
        self,
        now: datetime,
        worker_id: str,
        lease_seconds: float,
    ) -> List[Dict[str, Any]]:
        """Claim due timer jobs using a lease to avoid duplicate execution."""
        claimed: List[Dict[str, Any]] = []
        lease_until = now + timedelta(seconds=max(float(lease_seconds), 1.0))

        with self._timer_jobs_lock():
            self._refresh_instances_graph_from_disk()

            for instance_uri in list(self._instances_graph.subjects(RDF.type, INST.ProcessInstance)):
                instance_id = str(instance_uri).split("/")[-1]
                for job_uri in list(self._instances_graph.objects(instance_uri, INST.hasTimerJob)):
                    status = str(
                        self._instances_graph.value(job_uri, INST.timerStatus) or "SCHEDULED"
                    )
                    due_at = self._parse_due_at(self._instances_graph.value(job_uri, INST.dueAt))
                    if due_at and due_at > now:
                        continue

                    if status == "FIRED" or status == "FAILED":
                        continue

                    if status == "CLAIMED":
                        leased_until = self._parse_due_at(
                            self._instances_graph.value(job_uri, INST.leaseUntil)
                        )
                        if leased_until and leased_until > now:
                            continue
                    elif status != "SCHEDULED":
                        continue

                    self._instances_graph.set((job_uri, INST.timerStatus, Literal("CLAIMED")))
                    self._instances_graph.set((job_uri, INST.claimedBy, Literal(worker_id)))
                    self._instances_graph.set((job_uri, INST.claimedAt, Literal(now.isoformat())))
                    self._instances_graph.set(
                        (job_uri, INST.leaseUntil, Literal(lease_until.isoformat()))
                    )

                    claimed.append(
                        {
                            "instance_uri": URIRef(instance_uri),
                            "instance_id": instance_id,
                            "job_uri": URIRef(job_uri),
                            "token_uri": self._instances_graph.value(job_uri, INST.forToken),
                            "node_uri": self._instances_graph.value(job_uri, INST.forNode),
                            "kind": str(
                                self._instances_graph.value(job_uri, INST.timerKind)
                                or "TOKEN_TIMER"
                            ),
                        }
                    )

            self._save_graph(self._instances_graph, "instances.ttl")

        return claimed

    def _finalize_timer_job(
        self,
        job_uri: URIRef,
        worker_id: str,
        final_status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """Finalize a claimed timer job if still owned by this worker."""
        if final_status not in {"FIRED", "FAILED"}:
            return False

        with self._timer_jobs_lock():
            status = str(self._instances_graph.value(job_uri, INST.timerStatus) or "")
            claimed_by = str(self._instances_graph.value(job_uri, INST.claimedBy) or "")

            if status != "CLAIMED" or claimed_by != worker_id:
                return False

            self._instances_graph.set((job_uri, INST.timerStatus, Literal(final_status)))
            if final_status == "FIRED":
                self._instances_graph.set(
                    (job_uri, INST.firedAt, Literal(datetime.utcnow().isoformat()))
                )
            else:
                self._instances_graph.set(
                    (job_uri, INST.failedAt, Literal(datetime.utcnow().isoformat()))
                )
                if error_message:
                    self._instances_graph.set(
                        (job_uri, INST.lastError, Literal(str(error_message)))
                    )

            self._instances_graph.remove((job_uri, INST.claimedBy, None))
            self._instances_graph.remove((job_uri, INST.claimedAt, None))
            self._instances_graph.remove((job_uri, INST.leaseUntil, None))

            self._save_graph(self._instances_graph, "instances.ttl")
            return True

    def _schedule_timer_job(
        self,
        instance_uri: URIRef,
        token_uri: Optional[URIRef],
        timer_node_uri: URIRef,
        due_at: Optional[datetime] = None,
        kind: str = "TOKEN_TIMER",
    ) -> URIRef:
        """Persist a timer job for future activation."""
        due_at = due_at or datetime.utcnow()

        # Avoid duplicate jobs for the same token/timer/kind.
        for job_uri in self._instances_graph.objects(instance_uri, INST.hasTimerJob):
            job_token = self._instances_graph.value(job_uri, INST.forToken)
            job_node = self._instances_graph.value(job_uri, INST.forNode)
            job_kind = self._instances_graph.value(job_uri, INST.timerKind)
            if (
                job_token == token_uri
                and job_node == timer_node_uri
                and str(job_kind or "TOKEN_TIMER") == kind
            ):
                return URIRef(job_uri)

        job_uri = INST[f"timer_job_{str(uuid.uuid4())[:8]}"]
        self._instances_graph.add((job_uri, RDF.type, INST.TimerJob))
        if token_uri is not None:
            self._instances_graph.add((job_uri, INST.forToken, token_uri))
        self._instances_graph.add((job_uri, INST.forNode, timer_node_uri))
        self._instances_graph.add((job_uri, INST.timerKind, Literal(kind)))
        self._instances_graph.add((job_uri, INST.timerStatus, Literal("SCHEDULED")))
        self._instances_graph.add((job_uri, INST.dueAt, Literal(due_at.isoformat())))
        self._instances_graph.add(
            (job_uri, INST.createdAt, Literal(datetime.utcnow().isoformat()))
        )
        self._instances_graph.add((instance_uri, INST.hasTimerJob, job_uri))
        self._save_graph(self._instances_graph, "instances.ttl")
        return job_uri

    def _parse_due_at(self, due_literal: Any) -> Optional[datetime]:
        if not due_literal:
            return None
        try:
            return datetime.fromisoformat(str(due_literal))
        except Exception:
            return None

    def _timer_due_for_node(self, node_uri: URIRef) -> datetime:
        """Compute due time for a timer node. Defaults to immediate fire."""
        now = datetime.utcnow()
        delay_literal = self._definitions_graph.value(node_uri, BPMN.timerDelaySeconds)
        if delay_literal is not None:
            try:
                delay = float(str(delay_literal))
                return now + timedelta(seconds=delay)
            except Exception:
                pass

        due_literal = self._definitions_graph.value(node_uri, BPMN.timerDueAt)
        parsed_due = self._parse_due_at(due_literal)
        if parsed_due:
            return parsed_due

        camunda_due = self._definitions_graph.value(
            node_uri, URIRef("http://camunda.org/schema/1.0/bpmn#dueDate")
        )
        parsed_camunda_due = self._parse_due_at(camunda_due)
        if parsed_camunda_due:
            return parsed_camunda_due

        return now

    def _is_timer_boundary_event(self, node_uri: URIRef) -> bool:
        for _, _, node_type in self._definitions_graph.triples((node_uri, RDF.type, None)):
            if "TimerBoundaryEvent" in str(node_type):
                return True
        return False

    def _node_has_timer_definition(self, node_uri: URIRef) -> bool:
        for child in self._definitions_graph.subjects(BPMN.hasParent, node_uri):
            for _, _, child_type in self._definitions_graph.triples((child, RDF.type, None)):
                if (
                    "timerEventDefinition" in str(child_type)
                    or "TimerEventDefinition" in str(child_type)
                ):
                    return True
        return False

    def _schedule_boundary_timer_jobs(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
    ) -> int:
        count = 0
        for boundary_uri in self._definitions_graph.objects(node_uri, BPMN.hasBoundaryEvent):
            if not self._is_timer_boundary_event(URIRef(boundary_uri)):
                continue
            due_at = self._timer_due_for_node(URIRef(boundary_uri))
            self._schedule_timer_job(
                instance_uri,
                token_uri,
                URIRef(boundary_uri),
                due_at=due_at,
            )
            count += 1
        return count

    def _is_event_subprocess(self, node_uri: URIRef) -> bool:
        for _, _, node_type in self._definitions_graph.triples((node_uri, RDF.type, None)):
            if "eventsubprocess" in str(node_type).lower():
                return True
        return False

    def _get_parent_scope(self, node_uri: URIRef) -> Optional[URIRef]:
        parent = self._definitions_graph.value(node_uri, BPMN.hasParent)
        return URIRef(parent) if parent else None

    def _is_node_within_scope(self, node_uri: URIRef, scope_uri: URIRef) -> bool:
        current = URIRef(node_uri)
        while current is not None:
            if current == scope_uri:
                return True
            parent = self._definitions_graph.value(current, BPMN.hasParent)
            current = URIRef(parent) if parent else None
        return False

    def _is_interrupting_event_subprocess_start(self, start_uri: URIRef) -> bool:
        """Determine whether an event subprocess start is interrupting."""
        for pred in (
            BPMN.interrupting,
            URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#isInterrupting"),
            URIRef("http://www.omg.org/spec/BPMN/20100524/MODEL#isInterrupting"),
            URIRef("http://camunda.org/schema/1.0/bpmn#isInterrupting"),
        ):
            raw = self._definitions_graph.value(start_uri, pred)
            if raw is not None:
                return str(raw).strip().lower() in {"1", "true", "yes", "on"}
        # Preserve existing runtime compatibility: default to non-interrupting
        # unless explicitly marked as interrupting.
        return False

    def _consume_interrupting_scope_tokens(
        self,
        instance_uri: URIRef,
        event_scope_uri: URIRef,
        parent_scope_uri: Optional[URIRef],
    ) -> int:
        """Consume active/waiting tokens in parent scope except event subprocess tokens."""
        consumed = 0
        for token_uri in list(self._instances_graph.objects(instance_uri, INST.hasToken)):
            status = self._instances_graph.value(token_uri, INST.status)
            if not status or str(status) not in {"ACTIVE", "WAITING"}:
                continue

            current_node = self._instances_graph.value(token_uri, INST.currentNode)
            if not current_node:
                continue

            if self._is_node_within_scope(URIRef(current_node), event_scope_uri):
                continue

            if parent_scope_uri and not self._is_node_within_scope(
                URIRef(current_node), parent_scope_uri
            ):
                continue

            self._execution_engine.consume_token(URIRef(token_uri))
            consumed += 1

        return consumed

    def _schedule_event_subprocess_timers(self, instance_uri: URIRef) -> int:
        process_def_uri = self._instances_graph.value(instance_uri, INST.processDefinition)
        if not process_def_uri:
            return 0

        scheduled = 0
        for elem in self._definitions_graph.objects(process_def_uri, PROC.hasElement):
            scope_uri = URIRef(elem)
            if not self._is_event_subprocess(scope_uri):
                continue
            for start_uri in self._find_scope_start_events(scope_uri):
                if not self._node_has_timer_definition(start_uri):
                    continue
                due_at = self._timer_due_for_node(start_uri)
                self._schedule_timer_job(
                    instance_uri=instance_uri,
                    token_uri=None,
                    timer_node_uri=start_uri,
                    due_at=due_at,
                    kind="EVENT_SUBPROCESS_START",
                )
                scheduled += 1
        return scheduled

    def _trigger_event_subprocess_start(
        self,
        instance_id: str,
        start_uri: URIRef,
        variables: Optional[Dict[str, Any]] = None,
        source: str = "event",
    ) -> bool:
        instance_uri = INST[instance_id]
        if (instance_uri, RDF.type, INST.ProcessInstance) not in self._instances_graph:
            return False

        scope_uri = self._get_parent_scope(start_uri)
        if scope_uri and self._is_interrupting_event_subprocess_start(start_uri):
            parent_scope_uri = self._get_parent_scope(scope_uri)
            consumed = self._consume_interrupting_scope_tokens(
                instance_uri=instance_uri,
                event_scope_uri=scope_uri,
                parent_scope_uri=parent_scope_uri,
            )
            self._audit_repo.log_event(
                instance_uri,
                "EVENT_SUBPROCESS_INTERRUPTED_SCOPE",
                "System",
                (
                    f"Interrupting start {str(start_uri)} consumed {consumed} "
                    f"token(s) in parent scope"
                ),
            )

        sub_instance_id = f"{instance_id}_event_{str(uuid.uuid4())[:8]}"
        sub_token_uri = self._execution_engine.create_token(instance_uri, start_uri, sub_instance_id)

        parent_vars = self._variables_service.get_variables(instance_id)
        for name, value in parent_vars.items():
            self._variables_service.set_variable(sub_instance_id, name, value, save=False)

        if variables:
            for name, value in variables.items():
                self._variables_service.set_variable(sub_instance_id, name, value, save=False)

        self._audit_repo.log_event(
            instance_uri,
            "EVENT_SUBPROCESS_TRIGGERED",
            "System",
            f"Triggered start {str(start_uri)} via {source}",
        )

        while self._execution_engine.get_token_status(sub_token_uri) == "ACTIVE":
            self._execute_token(instance_uri, sub_token_uri, sub_instance_id, merged_gateways=set())

        return True

    def run_due_timers(
        self,
        now: Optional[datetime] = None,
        worker_id: Optional[str] = None,
        lease_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """Fire due timer jobs and resume affected instances."""
        now = now or datetime.utcnow()
        worker_id = worker_id or f"worker-{str(uuid.uuid4())[:8]}"
        fired = 0
        affected_instance_ids = set()
        claimed_jobs = self._claim_due_timer_jobs(
            now=now, worker_id=worker_id, lease_seconds=lease_seconds
        )

        for claimed in claimed_jobs:
            instance_uri = URIRef(claimed["instance_uri"])
            instance_id = claimed["instance_id"]
            job_uri = URIRef(claimed["job_uri"])
            token_uri = claimed["token_uri"]
            node_uri = claimed["node_uri"]
            kind = claimed["kind"]
            try:
                if not node_uri:
                    self._finalize_timer_job(
                        job_uri=job_uri,
                        worker_id=worker_id,
                        final_status="FAILED",
                        error_message="Timer job missing target node",
                    )
                    continue

                if kind == "EVENT_SUBPROCESS_START":
                    if not self._trigger_event_subprocess_start(
                        instance_id=instance_id,
                        start_uri=URIRef(node_uri),
                        source="timer",
                    ):
                        self._finalize_timer_job(
                            job_uri=job_uri,
                            worker_id=worker_id,
                            final_status="FAILED",
                            error_message="Failed to trigger event subprocess start",
                        )
                        continue
                    self._audit_repo.log_event(
                        URIRef(instance_uri),
                        "TIMER_FIRED",
                        "System",
                        f"Event subprocess timer fired at {str(node_uri)}",
                    )
                elif self._is_timer_boundary_event(URIRef(node_uri)):
                    if not token_uri:
                        self._finalize_timer_job(
                            job_uri=job_uri,
                            worker_id=worker_id,
                            final_status="FAILED",
                            error_message="Boundary timer missing token",
                        )
                        continue
                    interrupting = True
                    interrupting_val = self._definitions_graph.value(
                        URIRef(node_uri), BPMN.interrupting
                    )
                    if interrupting_val:
                        interrupting = str(interrupting_val).lower() == "true"

                    def log_callback(inst_uri, event, user, details):
                        self._audit_repo.log_event(inst_uri, event, user, details)

                    def execute_callback(inst_uri, tok_uri, inst_id):
                        self._execute_token(inst_uri, tok_uri, inst_id, merged_gateways=set())

                    self._message_handler.trigger_boundary_event(
                        token_uri=URIRef(token_uri),
                        instance_uri=URIRef(instance_uri),
                        boundary_event_uri=URIRef(node_uri),
                        instance_id=instance_id,
                        is_interrupting=interrupting,
                        log_callback=log_callback,
                        execute_callback=execute_callback,
                    )
                else:
                    # Intermediate timer catch event path: activate and continue.
                    if not token_uri:
                        self._finalize_timer_job(
                            job_uri=job_uri,
                            worker_id=worker_id,
                            final_status="FAILED",
                            error_message="Intermediate timer missing token",
                        )
                        continue
                    self._instances_graph.set((URIRef(token_uri), INST.status, Literal("ACTIVE")))
                    self._execution_engine.move_token_to_next(
                        URIRef(instance_uri), URIRef(token_uri), instance_id
                    )
                    self._audit_repo.log_event(
                        URIRef(instance_uri),
                        "TIMER_FIRED",
                        "System",
                        f"Timer fired at {str(node_uri)}",
                    )

                if self._finalize_timer_job(
                    job_uri=job_uri,
                    worker_id=worker_id,
                    final_status="FIRED",
                ):
                    fired += 1
                    affected_instance_ids.add(instance_id)
            except Exception as exc:
                self._finalize_timer_job(
                    job_uri=job_uri,
                    worker_id=worker_id,
                    final_status="FAILED",
                    error_message=str(exc),
                )

        for instance_id in affected_instance_ids:
            self._execute_instance(INST[instance_id], instance_id, process_timers=False)

        return {
            "fired": fired,
            "claimed": len(claimed_jobs),
            "worker_id": worker_id,
            "affected_instances": sorted(affected_instance_ids),
        }

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

    # Backward-compatible aliases used by API layer and legacy tests

    def register_topic_handler(
        self,
        topic: str,
        handler_function: Callable,
        description: str = "",
        async_execution: bool = False,
        handler_type: str = "function",
        http_config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Backward-compatible topic registration method."""
        return self._topic_registry.register(
            topic=topic,
            handler_function=handler_function,
            description=description,
            async_execution=async_execution,
            handler_type=handler_type,
            http_config=http_config,
        )

    def update_topic_description(self, topic: str, description: str) -> bool:
        """Backward-compatible topic description update method."""
        return self._topic_registry.update_description(topic, description)

    def update_topic_async(self, topic: str, async_execution: bool) -> bool:
        """Backward-compatible topic async update method."""
        return self._topic_registry.update_async(topic, async_execution)

    def unregister_topic_handler(self, topic: str) -> bool:
        """Backward-compatible topic unregister method."""
        return self._topic_registry.unregister(topic)

    def get_registered_topics(self) -> Dict[str, Any]:
        """Backward-compatible topic listing method."""
        return self._topic_registry.get_all()

    def execute_service_task(
        self,
        instance_id: str,
        topic: str,
        variables: Dict[str, Any],
        loop_idx: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible service task execution method."""
        return self._topic_registry.execute(instance_id, topic, variables, loop_idx)

    # ==================== Message Operations ====================

    def send_message(
        self,
        message_name: str,
        correlation_key: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a message to a process instance."""
        def log_callback(inst_uri, event, user, details):
            self._audit_repo.log_event(inst_uri, event, user, details)

        def execute_callback(inst_uri, tok_uri, inst_id):
            self._execute_token(inst_uri, tok_uri, inst_id, set())

        def boundary_event_callback(
            token_uri,
            instance_uri,
            boundary_event_uri,
            instance_id,
            is_interrupting,
            vars_payload,
        ):
            self._message_handler.trigger_boundary_event(
                token_uri,
                instance_uri,
                boundary_event_uri,
                instance_id,
                is_interrupting,
                vars_payload,
                log_callback=log_callback,
                execute_callback=execute_callback,
            )

        result = self._message_handler.send_message(
            message_name=message_name,
            instance_id=correlation_key,
            variables=variables,
            correlation_id=correlation_key,
            log_callback=log_callback,
            boundary_event_callback=boundary_event_callback,
        )

        if variables:
            for match in result.get("tasks", []):
                instance_uri = match.get("instance_uri")
                if instance_uri:
                    instance_id = str(instance_uri).split("/")[-1]
                    for name, value in variables.items():
                        self._variables_service.set_variable(
                            instance_id, name, value, save=False
                        )
            self._save_graph(self._instances_graph, "instances.ttl")

        instance_ids = set()
        for match in result.get("tasks", []):
            instance_uri = match.get("instance_uri")
            if instance_uri:
                instance_ids.add(str(instance_uri).split("/")[-1])
        for match in result.get("boundary_events", []):
            instance_uri = match.get("instance_uri")
            if instance_uri:
                instance_ids.add(str(instance_uri).split("/")[-1])

        for instance_id in instance_ids:
            self._execute_instance(INST[instance_id], instance_id)

        # Event subprocess message-start support.
        triggered = []
        candidate_instance_ids = set(instance_ids)
        if correlation_key:
            candidate_instance_ids.add(correlation_key)
        if not candidate_instance_ids:
            for inst_uri in self._instances_graph.subjects(RDF.type, INST.ProcessInstance):
                candidate_instance_ids.add(str(inst_uri).split("/")[-1])

        for instance_id in candidate_instance_ids:
            event_result = self._trigger_event_subprocess_variant(
                instance_id=instance_id,
                variant="message",
                trigger_value=message_name,
                variables=variables,
                source=f"message:{message_name}",
            )
            if event_result.get("triggered"):
                triggered.append(instance_id)

        if triggered:
            result["event_subprocess_triggers"] = triggered

        return result

    def _event_subprocess_scopes(self, process_def_uri: URIRef) -> List[URIRef]:
        scopes = []
        for elem in self._definitions_graph.objects(process_def_uri, PROC.hasElement):
            for _, _, node_type in self._definitions_graph.triples((elem, RDF.type, None)):
                if "eventsubprocess" in str(node_type).lower():
                    scopes.append(URIRef(elem))
                    break
        return scopes

    def _event_start_info(self, start_uri: URIRef) -> Dict[str, Any]:
        info: Dict[str, Any] = {"variants": set(), "defs": []}
        camunda_ns = "http://camunda.org/schema/1.0/bpmn#"

        for pred in (BPMN.message, BPMN.messageRef, URIRef(f"{camunda_ns}message")):
            configured = self._definitions_graph.value(start_uri, pred)
            if configured:
                info["variants"].add("message")
                info["message"] = str(configured)
                break

        for child in self._definitions_graph.subjects(BPMN.hasParent, start_uri):
            child_uri = URIRef(child)
            child_types = [
                str(t).lower()
                for _, _, t in self._definitions_graph.triples((child_uri, RDF.type, None))
            ]
            if not child_types:
                continue

            variant = None
            if any("messageeventdefinition" in t for t in child_types):
                variant = "message"
                for pred in (BPMN.message, BPMN.messageRef, URIRef(f"{camunda_ns}message")):
                    configured = self._definitions_graph.value(child_uri, pred)
                    if configured:
                        info["message"] = str(configured)
                        break
            elif any("timereventdefinition" in t for t in child_types):
                variant = "timer"
            elif any("erroreventdefinition" in t for t in child_types):
                variant = "error"
                for pred in (BPMN.errorRef, URIRef(f"{camunda_ns}error"), URIRef(f"{camunda_ns}errorRef")):
                    configured = self._definitions_graph.value(child_uri, pred)
                    if configured:
                        info["error"] = str(configured)
                        break
            elif any("escalationeventdefinition" in t for t in child_types):
                variant = "escalation"
                for pred in (
                    BPMN.escalationRef,
                    URIRef(f"{camunda_ns}escalation"),
                    URIRef(f"{camunda_ns}escalationRef"),
                ):
                    configured = self._definitions_graph.value(child_uri, pred)
                    if configured:
                        info["escalation"] = str(configured)
                        break
            elif any("signaleventdefinition" in t for t in child_types):
                variant = "signal"
                for pred in (BPMN.signalRef, URIRef(f"{camunda_ns}signal"), URIRef(f"{camunda_ns}signalRef")):
                    configured = self._definitions_graph.value(child_uri, pred)
                    if configured:
                        info["signal"] = str(configured)
                        break
            elif any("conditionaleventdefinition" in t for t in child_types):
                variant = "conditional"
                for pred in (
                    BPMN.conditionExpression,
                    BPMN.conditionBody,
                    URIRef(f"{camunda_ns}conditionExpression"),
                ):
                    configured = self._definitions_graph.value(child_uri, pred)
                    if configured:
                        info["condition"] = str(configured)
                        break
            else:
                info["defs"].append({"uri": child_uri, "variant": "unsupported"})
                continue

            if variant:
                info["variants"].add(variant)
                info["defs"].append({"uri": child_uri, "variant": variant})

        if "conditional" not in info["variants"]:
            for pred in (
                BPMN.conditionExpression,
                BPMN.conditionBody,
                URIRef(f"{camunda_ns}conditionExpression"),
            ):
                configured = self._definitions_graph.value(start_uri, pred)
                if configured:
                    info["variants"].add("conditional")
                    info["condition"] = str(configured)
                    break

        return info

    def _matches_conditional_trigger(
        self,
        condition_expr: Optional[str],
        variables: Optional[Dict[str, Any]],
    ) -> bool:
        payload = variables or {}
        if not payload and not condition_expr:
            return False
        if not condition_expr:
            return any(bool(v) for v in payload.values())

        expr = condition_expr.strip()
        if "==" in expr:
            left, right = expr.split("==", 1)
            left = left.strip().strip("${} ")
            right = right.strip().strip("'\" ")
            return str(payload.get(left)) == right

        key = expr.strip().strip("${} ")
        return bool(payload.get(key))

    def _trigger_event_subprocess_variant(
        self,
        instance_id: str,
        variant: str,
        trigger_value: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Trigger event subprocess starts of a specific variant."""
        supported = {"message", "timer", "error", "escalation", "signal", "conditional"}
        if variant not in supported:
            raise ValueError(f"Unsupported event subprocess start variant: {variant}")

        instance_uri = INST[instance_id]
        if (instance_uri, RDF.type, INST.ProcessInstance) not in self._instances_graph:
            return {"triggered": False, "count": 0, "errors": ["instance_not_found"]}

        process_def_uri = self._instances_graph.value(instance_uri, INST.processDefinition)
        if not process_def_uri:
            return {"triggered": False, "count": 0, "errors": ["missing_process_definition"]}

        triggered_count = 0
        errors = []
        event_subprocesses = self._event_subprocess_scopes(URIRef(process_def_uri))

        for scope_uri in event_subprocesses:
            for start_uri in self._find_scope_start_events(scope_uri):
                info = self._event_start_info(start_uri)
                if any(d["variant"] == "unsupported" for d in info["defs"]):
                    self._audit_repo.log_event(
                        instance_uri,
                        "EVENT_SUBPROCESS_START_UNSUPPORTED",
                        "System",
                        f"Unsupported start event definition at {str(start_uri)}",
                    )
                    errors.append(f"unsupported_start_definition:{str(start_uri)}")

                if variant not in info["variants"]:
                    continue

                matched = False
                if variant == "conditional":
                    matched = self._matches_conditional_trigger(info.get("condition"), variables)
                elif variant == "timer":
                    matched = True
                else:
                    configured = info.get(variant)
                    matched = configured is None or str(configured) == str(trigger_value)

                if not matched:
                    continue

                if self._trigger_event_subprocess_start(
                    instance_id=instance_id,
                    start_uri=start_uri,
                    variables=variables,
                    source=source or f"{variant}:{trigger_value}",
                ):
                    triggered_count += 1

        if triggered_count:
            self._save_graph(self._instances_graph, "instances.ttl")

        return {"triggered": triggered_count > 0, "count": triggered_count, "errors": errors}

    def _trigger_event_subprocess_message(
        self,
        instance_id: str,
        message_name: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Trigger message-based event subprocess starts for an instance."""
        result = self._trigger_event_subprocess_variant(
            instance_id=instance_id,
            variant="message",
            trigger_value=message_name,
            variables=variables,
            source=f"message:{message_name}",
        )
        return bool(result.get("triggered"))

    def throw_error(
        self,
        instance_id: str,
        error_code: str,
        error_message: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Trigger error-start event subprocesses for an instance."""
        payload = dict(variables or {})
        payload["errorCode"] = error_code
        if error_message:
            payload["errorMessage"] = error_message
        result = self._trigger_event_subprocess_variant(
            instance_id=instance_id,
            variant="error",
            trigger_value=error_code,
            variables=payload,
            source=f"error:{error_code}",
        )
        if not result.get("triggered"):
            self._audit_repo.log_event(
                INST[instance_id],
                "EVENT_SUBPROCESS_TRIGGER_MISS",
                "System",
                f"No error-start event subprocess matched '{error_code}'",
            )
        return result

    def throw_signal(
        self,
        signal_name: str,
        correlation_key: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Trigger signal-start event subprocesses."""
        candidate_instance_ids = []
        if correlation_key:
            candidate_instance_ids.append(correlation_key)
        else:
            for inst_uri in self._instances_graph.subjects(RDF.type, INST.ProcessInstance):
                candidate_instance_ids.append(str(inst_uri).split("/")[-1])

        triggered = []
        errors = []
        for instance_id in candidate_instance_ids:
            result = self._trigger_event_subprocess_variant(
                instance_id=instance_id,
                variant="signal",
                trigger_value=signal_name,
                variables=variables,
                source=f"signal:{signal_name}",
            )
            if result.get("triggered"):
                triggered.append(instance_id)
            errors.extend(result.get("errors", []))

        if not triggered:
            for instance_id in candidate_instance_ids:
                self._audit_repo.log_event(
                    INST[instance_id],
                    "EVENT_SUBPROCESS_TRIGGER_MISS",
                    "System",
                    f"No signal-start event subprocess matched '{signal_name}'",
                )
        return {"triggered_instances": triggered, "errors": errors}

    def throw_escalation(
        self,
        instance_id: str,
        escalation_code: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Trigger escalation-start event subprocesses for an instance."""
        payload = dict(variables or {})
        payload["escalationCode"] = escalation_code
        result = self._trigger_event_subprocess_variant(
            instance_id=instance_id,
            variant="escalation",
            trigger_value=escalation_code,
            variables=payload,
            source=f"escalation:{escalation_code}",
        )
        if not result.get("triggered"):
            self._audit_repo.log_event(
                INST[instance_id],
                "EVENT_SUBPROCESS_TRIGGER_MISS",
                "System",
                f"No escalation-start event subprocess matched '{escalation_code}'",
            )
        return result

    def trigger_conditional_event_subprocesses(
        self,
        instance_id: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Evaluate and trigger conditional-start event subprocesses."""
        result = self._trigger_event_subprocess_variant(
            instance_id=instance_id,
            variant="conditional",
            variables=variables,
            source="conditional",
        )
        if not result.get("triggered"):
            self._audit_repo.log_event(
                INST[instance_id],
                "EVENT_SUBPROCESS_TRIGGER_MISS",
                "System",
                "No conditional-start event subprocess condition matched",
            )
        return result

    # ==================== Internal Execution ====================

    def _execute_instance(
        self,
        instance_uri: URIRef,
        instance_id: str,
        process_timers: bool = True,
    ) -> None:
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

        self._schedule_event_subprocess_timers(instance_uri)

        if process_timers:
            # Fire any due timers first so waiting tokens can become active.
            self.run_due_timers()

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
            "send_task": self._handle_send_task,
            "user_task": self._handle_user_task,
            "manual_task": self._handle_manual_task,
            "exclusive_gateway": self._handle_exclusive_gateway,
            "parallel_gateway": self._handle_parallel_gateway,
            "inclusive_gateway": self._handle_inclusive_gateway,
            "event_based_gateway": self._handle_event_based_gateway,
            "script_task": self._handle_script_task,
            "receive_task": self._handle_receive_task,
            "intermediate_catch_event": self._handle_intermediate_catch_event,
            "intermediate_throw_event": self._handle_intermediate_throw_event,
            "boundary_event": self._handle_boundary_event,
            "error_end_event": self._handle_error_end_event,
            "cancel_end_event": self._handle_cancel_end_event,
            "compensation_end_event": self._handle_compensation_end_event,
            "terminate_end_event": self._handle_terminate_end_event,
            "expanded_subprocess": self._handle_expanded_subprocess,
            "call_activity": self._handle_call_activity,
            "event_subprocess": self._handle_event_subprocess,
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

    def _handle_send_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle send task by emitting a message if configured, then continue."""
        message_name = self._definitions_graph.value(node_uri, BPMN.message)
        if not message_name:
            message_name = self._definitions_graph.value(node_uri, BPMN.messageRef)
        if not message_name:
            camunda_msg = URIRef("http://camunda.org/schema/1.0/bpmn#message")
            message_name = self._definitions_graph.value(node_uri, camunda_msg)

        if message_name:
            self.send_message(str(message_name))
            self._audit_repo.log_event(
                instance_uri,
                "SEND_TASK",
                "System",
                f"{str(node_uri)} (message: {str(message_name)})",
            )
        else:
            self._audit_repo.log_event(
                instance_uri,
                "SEND_TASK",
                "System",
                f"{str(node_uri)} (no message configured)",
            )

        self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)

    def _handle_manual_task(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        """Handle manual task as a recorded pass-through activity."""
        self._audit_repo.log_event(
            instance_uri,
            "MANUAL_TASK",
            "System",
            f"{str(node_uri)}",
        )
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
        self._schedule_boundary_timer_jobs(instance_uri, token_uri, node_uri)

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
            self._schedule_boundary_timer_jobs(instance_uri, token_uri, node_uri)
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

    def _find_scope_start_events(self, scope_uri: URIRef) -> List[URIRef]:
        starts = []
        for candidate in self._definitions_graph.subjects(BPMN.hasParent, scope_uri):
            for _, _, o in self._definitions_graph.triples((candidate, RDF.type, None)):
                if "startevent" in str(o).lower():
                    starts.append(URIRef(candidate))
                    break
        return starts

    def _execute_embedded_scope(
        self,
        scope_uri: URIRef,
        instance_uri: URIRef,
        instance_id: str,
        event_name: str,
    ) -> bool:
        starts = self._find_scope_start_events(scope_uri)
        if not starts:
            return False

        sub_instance_id = f"{instance_id}_sub_{str(uuid.uuid4())[:8]}"
        sub_token_uri = self._execution_engine.create_token(
            instance_uri,
            starts[0],
            sub_instance_id,
        )
        self._audit_repo.log_event(
            instance_uri,
            event_name,
            "System",
            f"Started scope {str(scope_uri)}",
        )
        while self._execution_engine.get_token_status(sub_token_uri) == "ACTIVE":
            self._execute_token(instance_uri, sub_token_uri, sub_instance_id, merged_gateways=set())
        self._execution_engine.consume_token(sub_token_uri)
        return True

    def _handle_expanded_subprocess(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        executed = self._execute_embedded_scope(
            scope_uri=node_uri,
            instance_uri=instance_uri,
            instance_id=instance_id,
            event_name="EXPANDED_SUBPROCESS_STARTED",
        )
        if executed:
            self._audit_repo.log_event(
                instance_uri,
                "EXPANDED_SUBPROCESS_COMPLETED",
                "System",
                f"Completed expanded subprocess {str(node_uri)}",
            )
        self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)

    def _handle_call_activity(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        def _parse_var_list(node: URIRef, local_name: str) -> List[str]:
            values: List[str] = []
            predicates = [
                BPMN[local_name],
                URIRef(f"http://camunda.org/schema/1.0/bpmn#{local_name}"),
            ]
            for pred in predicates:
                raw = self._definitions_graph.value(node, pred)
                if raw:
                    values.extend(
                        [item.strip() for item in str(raw).split(",") if item.strip()]
                    )
            return values

        def _copy_vars(
            source_instance_id: str,
            target_instance_id: str,
            names: Optional[List[str]] = None,
        ) -> int:
            source_vars = self._variables_service.get_variables(source_instance_id)
            count = 0
            for name, value in source_vars.items():
                if names is not None and name not in names:
                    continue
                self._variables_service.set_variable(
                    target_instance_id, name, value, save=False
                )
                count += 1
            return count

        called_element = self._definitions_graph.value(node_uri, BPMN.calledElement)
        if not called_element:
            self._audit_repo.log_event(
                instance_uri,
                "CALL_ACTIVITY_SKIPPED",
                "System",
                f"No calledElement on {str(node_uri)}",
            )
            self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)
            return

        starts = self._find_scope_start_events(URIRef(called_element))
        if not starts:
            self._audit_repo.log_event(
                instance_uri,
                "CALL_ACTIVITY_SKIPPED",
                "System",
                f"Called element has no start event: {str(called_element)}",
            )
            self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)
            return

        in_names = _parse_var_list(node_uri, "inVariables")
        out_names = _parse_var_list(node_uri, "outVariables")
        in_filter = in_names if in_names else None
        out_filter = out_names if out_names else None

        sub_instance_id = f"{instance_id}_call_{str(uuid.uuid4())[:8]}"
        sub_token_uri = self._execution_engine.create_token(
            instance_uri,
            starts[0],
            sub_instance_id,
        )

        call_exec_uri = INST[f"call_exec_{str(uuid.uuid4())[:8]}"]
        self._instances_graph.add((call_exec_uri, RDF.type, INST.CallActivityExecution))
        self._instances_graph.add((call_exec_uri, INST.parentInstance, instance_uri))
        self._instances_graph.add((call_exec_uri, INST.callNode, node_uri))
        self._instances_graph.add((call_exec_uri, INST.calledElement, URIRef(called_element)))
        self._instances_graph.add((call_exec_uri, INST.childExecutionId, Literal(sub_instance_id)))
        self._instances_graph.add(
            (call_exec_uri, INST.startedAt, Literal(datetime.utcnow().isoformat()))
        )
        self._instances_graph.add((call_exec_uri, INST.status, Literal("RUNNING")))
        self._instances_graph.add((instance_uri, INST.hasCallExecution, call_exec_uri))

        copied_in = _copy_vars(instance_id, sub_instance_id, names=in_filter)
        self._audit_repo.log_event(
            instance_uri,
            "CALL_ACTIVITY_STARTED",
            "System",
            f"Started call activity to {str(called_element)} with child {sub_instance_id}",
        )

        while self._execution_engine.get_token_status(sub_token_uri) == "ACTIVE":
            self._execute_token(
                instance_uri,
                sub_token_uri,
                sub_instance_id,
                merged_gateways=set(),
            )
        self._execution_engine.consume_token(sub_token_uri)

        copied_out = _copy_vars(sub_instance_id, instance_id, names=out_filter)
        self._instances_graph.set(
            (call_exec_uri, INST.endedAt, Literal(datetime.utcnow().isoformat()))
        )
        self._instances_graph.set((call_exec_uri, INST.status, Literal("COMPLETED")))
        self._instances_graph.set((call_exec_uri, INST.copiedInCount, Literal(str(copied_in))))
        self._instances_graph.set(
            (call_exec_uri, INST.copiedOutCount, Literal(str(copied_out)))
        )
        executed = True
        if executed:
            self._audit_repo.log_event(
                instance_uri,
                "CALL_ACTIVITY_COMPLETED",
                "System",
                f"Completed call activity to {str(called_element)} (in={copied_in}, out={copied_out})",
            )
        else:
            self._audit_repo.log_event(
                instance_uri,
                "CALL_ACTIVITY_SKIPPED",
                "System",
                f"Called element has no start event: {str(called_element)}",
            )
        self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)

    def _handle_event_subprocess(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        # Event subprocesses are normally triggered by events and not sequence flow.
        self._audit_repo.log_event(
            instance_uri,
            "EVENT_SUBPROCESS_SKIPPED",
            "System",
            f"Event subprocess node reached in normal flow: {str(node_uri)}",
        )
        self._execution_engine.consume_token(token_uri)

    def _handle_intermediate_throw_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        message_name = self._definitions_graph.value(node_uri, BPMN.messageRef)
        if not message_name:
            message_name = self._definitions_graph.value(
                node_uri, URIRef("http://camunda.org/schema/1.0/bpmn#message")
            )
        if message_name:
            self.send_message(str(message_name))
            self._audit_repo.log_event(
                instance_uri,
                "MESSAGE_THROWN",
                "System",
                f"Intermediate throw message: {str(message_name)}",
            )
        self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)

    def _handle_intermediate_catch_event(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        merged_gateways: set,
    ) -> None:
        # Timer catch event: park token and schedule timer.
        if self._node_has_timer_definition(node_uri):
            self._execution_engine.set_token_waiting(token_uri)
            due_at = self._timer_due_for_node(node_uri)
            self._schedule_timer_job(instance_uri, token_uri, node_uri, due_at=due_at)
            self._audit_repo.log_event(
                instance_uri,
                "WAITING_FOR_TIMER",
                "System",
                f"Timer scheduled at {due_at.isoformat()} for {str(node_uri)}",
            )
            return

        # Message catch event: behave like receive task.
        message_name = self._definitions_graph.value(node_uri, BPMN.messageRef)
        if not message_name:
            message_name = self._definitions_graph.value(
                node_uri, URIRef("http://camunda.org/schema/1.0/bpmn#message")
            )
        if message_name:
            self._execution_engine.set_token_waiting(token_uri)
            self._audit_repo.log_event(
                instance_uri,
                "WAITING_FOR_MESSAGE",
                "System",
                f"Waiting for message '{str(message_name)}' at {str(node_uri)}",
            )
            return

        self._execution_engine.move_token_to_next(instance_uri, token_uri, instance_id)

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


def get_facade(data_dir: str = "data/spear_rdf") -> StorageFacade:
    """Get or create the shared storage facade instance."""
    global _shared_facade
    if _shared_facade is None:
        _shared_facade = StorageFacade(data_dir)
    return _shared_facade


def reset_facade() -> None:
    """Reset the shared facade (useful for testing)."""
    global _shared_facade
    _shared_facade = None
