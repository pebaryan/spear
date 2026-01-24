# Task Repository for SPEAR Engine
# Handles CRUD operations for user tasks

import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from rdflib import Literal, RDF, URIRef

from .base import BaseStorageService, TASK, INST, LOG

if TYPE_CHECKING:
    from rdflib import Graph

logger = logging.getLogger(__name__)


class TaskRepository:
    """
    Repository for managing user tasks in BPMN processes.

    Handles:
    - Creating tasks when user task nodes are reached
    - Claiming tasks by users
    - Completing tasks with optional variables
    - Assigning tasks to users
    - Querying tasks by various criteria

    Tasks are stored in the tasks_graph with:
    - Task metadata (name, status, timestamps)
    - Assignment info (assignee, candidates)
    - Form data
    - Link to instance and node
    """

    def __init__(self, base_storage: BaseStorageService):
        """
        Initialize the task repository.

        Args:
            base_storage: The base storage service providing graph access
        """
        self._storage = base_storage

    @property
    def _graph(self) -> "Graph":
        """Get the tasks graph."""
        return self._storage.tasks_graph

    @property
    def _instances_graph(self) -> "Graph":
        """Get the instances graph (for linking tasks to instances)."""
        return self._storage.instances_graph

    @property
    def _audit_graph(self) -> "Graph":
        """Get the audit graph (for task events)."""
        return self._storage.audit_graph

    def create(
        self,
        instance_id: str,
        node_uri: str,
        name: str = "User Task",
        assignee: Optional[str] = None,
        candidate_users: Optional[List[str]] = None,
        candidate_groups: Optional[List[str]] = None,
        form_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new user task.

        Args:
            instance_id: ID of the process instance
            node_uri: URI of the BPMN user task node
            name: Task name/title
            assignee: Optional direct assignee
            candidate_users: Optional list of candidate user IDs
            candidate_groups: Optional list of candidate group IDs
            form_data: Optional form field data

        Returns:
            The created task data
        """
        task_id = str(uuid.uuid4())
        task_uri = TASK[task_id]
        instance_uri = INST[instance_id]

        # Create task in RDF
        self._graph.add((task_uri, RDF.type, TASK.UserTask))
        self._graph.add((task_uri, TASK.instance, instance_uri))
        self._graph.add((task_uri, TASK.node, URIRef(node_uri)))
        self._graph.add((task_uri, TASK.name, Literal(name)))
        self._graph.add((task_uri, TASK.status, Literal("CREATED")))
        self._graph.add((task_uri, TASK.createdAt, Literal(datetime.now().isoformat())))

        if assignee:
            self._graph.add((task_uri, TASK.assignee, Literal(assignee)))

        if candidate_users:
            for user in candidate_users:
                self._graph.add((task_uri, TASK.candidateUser, Literal(user)))

        if candidate_groups:
            for group in candidate_groups:
                self._graph.add((task_uri, TASK.candidateGroup, Literal(group)))

        if form_data:
            form_uri = TASK[f"form_{task_id}"]
            self._graph.add((task_uri, TASK.hasForm, form_uri))
            for key, value in form_data.items():
                self._graph.add((form_uri, TASK.fieldName, Literal(key)))
                self._graph.add((form_uri, TASK.fieldValue, Literal(str(value))))

        # Link task to instance
        self._instances_graph.add((instance_uri, INST.hasTask, task_uri))

        # Save both graphs
        self._storage.save_tasks()
        self._storage.save_instances()

        logger.info(f"Created task {task_id} for instance {instance_id}")

        return self.get(task_id)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a task by ID.

        Args:
            task_id: The task ID

        Returns:
            Task data dictionary, or None if not found
        """
        task_uri = TASK[task_id]

        if (task_uri, RDF.type, TASK.UserTask) not in self._graph:
            return None

        instance_uri = self._graph.value(task_uri, TASK.instance)
        node_uri = self._graph.value(task_uri, TASK.node)
        name = self._graph.value(task_uri, TASK.name)
        status = self._graph.value(task_uri, TASK.status)
        assignee = self._graph.value(task_uri, TASK.assignee)
        created_at = self._graph.value(task_uri, TASK.createdAt)
        claimed_at = self._graph.value(task_uri, TASK.claimedAt)
        completed_at = self._graph.value(task_uri, TASK.completedAt)

        instance_id = str(instance_uri).split("/")[-1] if instance_uri else None

        # Collect candidate users and groups
        candidate_users = [
            str(u) for u in self._graph.objects(task_uri, TASK.candidateUser)
        ]
        candidate_groups = [
            str(g) for g in self._graph.objects(task_uri, TASK.candidateGroup)
        ]

        # Collect form data
        form_data = {}
        form_uri = self._graph.value(task_uri, TASK.hasForm)
        if form_uri:
            for field_name in self._graph.objects(form_uri, TASK.fieldName):
                field_value = self._graph.value(form_uri, TASK[field_name])
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

    def list(
        self,
        instance_id: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        List tasks with optional filtering.

        Args:
            instance_id: Filter by instance ID
            status: Filter by status
            assignee: Filter by assignee
            page: Page number (1-based)
            page_size: Items per page

        Returns:
            Dictionary with tasks list and pagination info
        """
        tasks = []

        for task_uri in self._graph.subjects(RDF.type, TASK.UserTask):
            task_id = str(task_uri).split("/")[-1]
            task_data = self.get(task_id)

            if not task_data:
                continue

            # Apply filters
            if instance_id and task_data["instance_id"] != instance_id:
                continue
            if status and task_data["status"] != status:
                continue
            if assignee and task_data["assignee"] != assignee:
                continue

            tasks.append(task_data)

        # Pagination
        total = len(tasks)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_tasks = tasks[start:end]

        return {
            "tasks": paginated_tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def claim(self, task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Claim a task for a user.

        Args:
            task_id: The task ID
            user_id: The user claiming the task

        Returns:
            Updated task data, or None if not found

        Raises:
            ValueError: If task cannot be claimed or user not authorized
        """
        task_uri = TASK[task_id]

        if (task_uri, RDF.type, TASK.UserTask) not in self._graph:
            return None

        status = self._graph.value(task_uri, TASK.status)
        if status and str(status) != "CREATED":
            raise ValueError(f"Task {task_id} cannot be claimed (status: {status})")

        # Check authorization
        assignee = self._graph.value(task_uri, TASK.assignee)
        if assignee and str(assignee) != user_id:
            candidate_users = [
                str(u) for u in self._graph.objects(task_uri, TASK.candidateUser)
            ]
            if user_id not in candidate_users:
                raise ValueError(
                    f"User {user_id} is not authorized to claim task {task_id}"
                )

        # Update task
        self._graph.set((task_uri, TASK.assignee, Literal(user_id)))
        self._graph.set((task_uri, TASK.status, Literal("CLAIMED")))
        self._graph.set((task_uri, TASK.claimedAt, Literal(datetime.now().isoformat())))

        self._log_task_event(task_uri, "CLAIMED", user_id)
        self._storage.save_tasks()

        logger.info(f"Task {task_id} claimed by user {user_id}")

        return self.get(task_id)

    def complete(
        self,
        task_id: str,
        user_id: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Complete a task.

        Note: This only marks the task as complete. Variable setting and
        instance resumption should be handled by the caller.

        Args:
            task_id: The task ID
            user_id: The user completing the task
            variables: Optional variables to return (stored for reference)

        Returns:
            Updated task data, or None if not found

        Raises:
            ValueError: If task cannot be completed or user not authorized
        """
        task_uri = TASK[task_id]

        if (task_uri, RDF.type, TASK.UserTask) not in self._graph:
            return None

        status = self._graph.value(task_uri, TASK.status)
        if status and str(status) not in ["CREATED", "CLAIMED"]:
            raise ValueError(f"Task {task_id} cannot be completed (status: {status})")

        assignee = self._graph.value(task_uri, TASK.assignee)
        if assignee and str(assignee) != user_id:
            raise ValueError(
                f"User {user_id} cannot complete task {task_id} (assigned to {assignee})"
            )

        # Update task
        self._graph.set((task_uri, TASK.status, Literal("COMPLETED")))
        self._graph.set(
            (task_uri, TASK.completedAt, Literal(datetime.now().isoformat()))
        )

        self._log_task_event(task_uri, "COMPLETED", user_id)
        self._storage.save_tasks()

        logger.info(f"Task {task_id} completed by user {user_id}")

        return self.get(task_id)

    def assign(
        self,
        task_id: str,
        assignee: str,
        assigner: str = "System",
    ) -> Optional[Dict[str, Any]]:
        """
        Assign a task to a user.

        Args:
            task_id: The task ID
            assignee: The user to assign the task to
            assigner: The user/system making the assignment

        Returns:
            Updated task data, or None if not found
        """
        task_uri = TASK[task_id]

        if (task_uri, RDF.type, TASK.UserTask) not in self._graph:
            return None

        old_assignee = self._graph.value(task_uri, TASK.assignee)

        # Update task
        self._graph.set((task_uri, TASK.assignee, Literal(assignee)))
        self._graph.set((task_uri, TASK.status, Literal("ASSIGNED")))

        self._log_task_event(
            task_uri,
            "ASSIGNED",
            assigner,
            f"Assigned from {old_assignee} to {assignee}",
        )
        self._storage.save_tasks()

        logger.info(f"Task {task_id} assigned to {assignee}")

        return self.get(task_id)

    def _log_task_event(
        self,
        task_uri: URIRef,
        event_type: str,
        user: str,
        details: str = "",
    ) -> None:
        """Log a task event to the audit graph."""
        event_uri = LOG[f"task_event_{str(uuid.uuid4())}"]

        self._audit_graph.add((event_uri, RDF.type, LOG.Event))
        self._audit_graph.add((event_uri, LOG.task, task_uri))
        self._audit_graph.add((event_uri, LOG.eventType, Literal(event_type)))
        self._audit_graph.add((event_uri, LOG.user, Literal(user)))
        self._audit_graph.add(
            (event_uri, LOG.timestamp, Literal(datetime.now().isoformat()))
        )
        if details:
            self._audit_graph.add((event_uri, LOG.details, Literal(details)))

        self._storage.save_audit()

    def get_for_instance_node(
        self,
        instance_id: str,
        node_uri: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the task associated with a specific instance and node.

        Args:
            instance_id: The instance ID
            node_uri: The node URI

        Returns:
            Task data if found, None otherwise
        """
        for task_uri in self._graph.subjects(RDF.type, TASK.UserTask):
            task_instance = self._graph.value(task_uri, TASK.instance)
            task_node = self._graph.value(task_uri, TASK.node)

            if task_instance and task_node:
                task_instance_id = str(task_instance).split("/")[-1]
                if task_instance_id == instance_id and str(task_node) == node_uri:
                    task_id = str(task_uri).split("/")[-1]
                    return self.get(task_id)

        return None

    def exists(self, task_id: str) -> bool:
        """Check if a task exists."""
        task_uri = TASK[task_id]
        return (task_uri, RDF.type, TASK.UserTask) in self._graph

    def count(
        self,
        instance_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Count tasks with optional filters."""
        if instance_id is None and status is None:
            return len(list(self._graph.subjects(RDF.type, TASK.UserTask)))

        count = 0
        for task_uri in self._graph.subjects(RDF.type, TASK.UserTask):
            if instance_id:
                task_instance = self._graph.value(task_uri, TASK.instance)
                if task_instance:
                    task_instance_id = str(task_instance).split("/")[-1]
                    if task_instance_id != instance_id:
                        continue

            if status:
                task_status = self._graph.value(task_uri, TASK.status)
                if not task_status or str(task_status) != status:
                    continue

            count += 1

        return count
