# Task Management API Endpoints
# REST API for managing user tasks in process instances

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from src.api.storage import RDFStorageService, get_storage

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# Use shared storage service
storage = get_storage()


class TaskClaimRequest(BaseModel):
    """Request model for claiming a task"""
    user_id: str = Field(..., description="User ID claiming the task")


class TaskCompleteRequest(BaseModel):
    """Request model for completing a task"""
    user_id: str = Field(..., description="User ID completing the task")
    variables: Optional[Dict[str, Any]] = Field(None, description="Variables to set on completion")


class TaskAssignRequest(BaseModel):
    """Request model for assigning a task"""
    assignee: str = Field(..., description="User ID to assign the task to")
    assigner: str = Field("System", description="User performing the assignment")


class TaskResponse(BaseModel):
    """Response model for a task"""
    id: str
    instance_id: str
    node_uri: Optional[str]
    name: str
    status: str
    assignee: Optional[str]
    candidate_users: List[str]
    candidate_groups: List[str]
    form_data: Dict[str, Any]
    created_at: Optional[str]
    claimed_at: Optional[str]
    completed_at: Optional[str]


class TaskListResponse(BaseModel):
    """Response for list of tasks"""
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    instance_id: Optional[str] = Query(None, description="Filter by instance ID"),
    status: Optional[str] = Query(None, description="Filter by status (CREATED, CLAIMED, COMPLETED)"),
    assignee: Optional[str] = Query(None, description="Filter by assignee"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    List all tasks with optional filtering.
    
    Returns a paginated list of user tasks from all process instances.
    """
    result = storage.list_tasks(
        instance_id=instance_id,
        status=status,
        assignee=assignee,
        page=page,
        page_size=page_size
    )
    
    tasks = []
    for task_data in result["tasks"]:
        tasks.append(TaskResponse(
            id=task_data["id"],
            instance_id=task_data["instance_id"],
            node_uri=task_data["node_uri"],
            name=task_data["name"],
            status=task_data["status"],
            assignee=task_data["assignee"],
            candidate_users=task_data["candidate_users"],
            candidate_groups=task_data["candidate_groups"],
            form_data=task_data["form_data"],
            created_at=task_data["created_at"],
            claimed_at=task_data["claimed_at"],
            completed_at=task_data["completed_at"]
        ))
    
    return TaskListResponse(
        tasks=tasks,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"]
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """
    Get a specific task by ID.
    
    Returns detailed information about the task including assignment and form data.
    """
    task = storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return TaskResponse(
        id=task["id"],
        instance_id=task["instance_id"],
        node_uri=task["node_uri"],
        name=task["name"],
        status=task["status"],
        assignee=task["assignee"],
        candidate_users=task["candidate_users"],
        candidate_groups=task["candidate_groups"],
        form_data=task["form_data"],
        created_at=task["created_at"],
        claimed_at=task["claimed_at"],
        completed_at=task["completed_at"]
    )


@router.post("/{task_id}/claim", response_model=TaskResponse)
async def claim_task(task_id: str, request: TaskClaimRequest):
    """
    Claim a task for a user.
    
    The task must be in CREATED status. If the task has candidate users or groups,
    the claiming user must be authorized.
    """
    try:
        task = storage.claim_task(task_id, request.user_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        return TaskResponse(
            id=task["id"],
            instance_id=task["instance_id"],
            node_uri=task["node_uri"],
            name=task["name"],
            status=task["status"],
            assignee=task["assignee"],
            candidate_users=task["candidate_users"],
            candidate_groups=task["candidate_groups"],
            form_data=task["form_data"],
            created_at=task["created_at"],
            claimed_at=task["claimed_at"],
            completed_at=task["completed_at"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(task_id: str, request: TaskCompleteRequest):
    """
    Complete a task.
    
    The task must be CLAIMED or ASSIGNED. The completing user must be the assignee.
    Optionally provides variables to set on the process instance.
    """
    try:
        task = storage.complete_task(task_id, request.user_id, request.variables)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # Resume the process instance after task completion
        storage.resume_instance_from_task(task_id)
        
        return TaskResponse(
            id=task["id"],
            instance_id=task["instance_id"],
            node_uri=task["node_uri"],
            name=task["name"],
            status=task["status"],
            assignee=task["assignee"],
            candidate_users=task["candidate_users"],
            candidate_groups=task["candidate_groups"],
            form_data=task["form_data"],
            created_at=task["created_at"],
            claimed_at=task["claimed_at"],
            completed_at=task["completed_at"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{task_id}/assign", response_model=TaskResponse)
async def assign_task(task_id: str, request: TaskAssignRequest):
    """
    Assign a task to a user.
    
    Assigns the task to a specific user, changing its status to ASSIGNED.
    """
    try:
        task = storage.assign_task(task_id, request.assignee, request.assigner)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        return TaskResponse(
            id=task["id"],
            instance_id=task["instance_id"],
            node_uri=task["node_uri"],
            name=task["name"],
            status=task["status"],
            assignee=task["assignee"],
            candidate_users=task["candidate_users"],
            candidate_groups=task["candidate_groups"],
            form_data=task["form_data"],
            created_at=task["created_at"],
            claimed_at=task["claimed_at"],
            completed_at=task["completed_at"]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/instance/{instance_id}")
async def get_instance_tasks(instance_id: str):
    """
    Get all tasks for a specific process instance.
    
    Returns all user tasks associated with the given process instance.
    """
    result = storage.list_tasks(instance_id=instance_id)
    
    tasks = []
    for task_data in result["tasks"]:
        tasks.append(TaskResponse(
            id=task_data["id"],
            instance_id=task_data["instance_id"],
            node_uri=task_data["node_uri"],
            name=task_data["name"],
            status=task_data["status"],
            assignee=task_data["assignee"],
            candidate_users=task_data["candidate_users"],
            candidate_groups=task_data["candidate_groups"],
            form_data=task_data["form_data"],
            created_at=task_data["created_at"],
            claimed_at=task_data["claimed_at"],
            completed_at=task_data["completed_at"]
        ))
    
    return {
        "instance_id": instance_id,
        "tasks": tasks,
        "total": len(tasks)
    }


@router.get("/user/{user_id}")
async def get_user_tasks(user_id: str):
    """
    Get all tasks for a specific user.
    
    Returns tasks assigned to or claimable by the given user.
    """
    result = storage.list_tasks(assignee=user_id)
    
    tasks = []
    for task_data in result["tasks"]:
        tasks.append(TaskResponse(
            id=task_data["id"],
            instance_id=task_data["instance_id"],
            node_uri=task_data["node_uri"],
            name=task_data["name"],
            status=task_data["status"],
            assignee=task_data["assignee"],
            candidate_users=task_data["candidate_users"],
            candidate_groups=task_data["candidate_groups"],
            form_data=task_data["form_data"],
            created_at=task_data["created_at"],
            claimed_at=task_data["claimed_at"],
            completed_at=task_data["completed_at"]
        ))
    
    return {
        "user_id": user_id,
        "tasks": tasks,
        "total": len(tasks)
    }
