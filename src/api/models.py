# Pydantic models for SPEAR API
# Request and response schemas for REST API

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class ProcessStatus(str, Enum):
    """Process definition status"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class InstanceStatus(str, Enum):
    """Process instance status"""
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"
    ERROR = "ERROR"


# ==================== Process Definition Models ====================

class ProcessDefinitionCreate(BaseModel):
    """Request model for creating a process definition"""
    name: str = Field(..., description="Human-readable process name")
    description: Optional[str] = Field(None, description="Process description")
    version: Optional[str] = Field("1.0.0", description="Process version")
    bpmn_file: str = Field(..., description="BPMN XML content or file path")


class ProcessDefinitionUpdate(BaseModel):
    """Request model for updating a process definition"""
    name: Optional[str] = Field(None, description="Human-readable process name")
    description: Optional[str] = Field(None, description="Process description")
    status: Optional[ProcessStatus] = Field(None, description="Process status")


class ProcessDefinitionResponse(BaseModel):
    """Response model for process definition"""
    id: str
    name: str
    description: Optional[str]
    version: str
    status: ProcessStatus
    rdf_triples_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProcessDefinitionListResponse(BaseModel):
    """Response for list of process definitions"""
    processes: List[ProcessDefinitionResponse]
    total: int
    page: int
    page_size: int


# ==================== Process Instance Models ====================

class VariableCreate(BaseModel):
    """Request model for creating/updating a variable"""
    name: str = Field(..., description="Variable name")
    value: Any = Field(..., description="Variable value")
    datatype: Optional[str] = Field(None, description="Data type (string, integer, float, etc.)")


class InstanceCreate(BaseModel):
    """Request model for starting a process instance"""
    process_id: str = Field(..., description="Process definition ID")
    variables: Optional[Dict[str, Any]] = Field(None, description="Initial variables")
    start_event_id: Optional[str] = Field(None, description="Specific start event to use")


class InstanceResponse(BaseModel):
    """Response model for process instance"""
    id: str
    process_id: str
    process_version: str
    status: InstanceStatus
    current_nodes: List[str]
    variables: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InstanceListResponse(BaseModel):
    """Response for list of process instances"""
    instances: List[InstanceResponse]
    total: int
    page: int
    page_size: int


class InstanceActionResponse(BaseModel):
    """Response for instance actions (start/stop/suspend/resume)"""
    success: bool
    message: str
    instance: Optional[InstanceResponse] = None


# ==================== Variable Models ====================

class VariableResponse(BaseModel):
    """Response model for a variable"""
    name: str
    value: Any
    datatype: Optional[str]
    updated_at: datetime


class VariableListResponse(BaseModel):
    """Response for list of variables"""
    variables: Dict[str, VariableResponse]


# ==================== Task Models ====================

class TaskStatus(str, Enum):
    """Task status"""
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskResponse(BaseModel):
    """Response model for a user task"""
    id: str
    instance_id: str
    process_id: str
    task_name: str
    assignee: Optional[str]
    candidate_users: List[str]
    candidate_groups: List[str]
    status: TaskStatus
    form_data: Optional[Dict[str, Any]]
    created_at: datetime
    due_date: Optional[datetime]

    class Config:
        from_attributes = True


class TaskClaimRequest(BaseModel):
    """Request model for claiming a task"""
    user_id: str = Field(..., description="User ID claiming the task")


class TaskCompleteRequest(BaseModel):
    """Request model for completing a task"""
    variables: Optional[Dict[str, Any]] = Field(None, description="Variables to set on completion")


# ==================== Health & Info Models ====================

class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    version: str
    uptime_seconds: float
    triple_count: int


class ApiInfoResponse(BaseModel):
    """Response model for API information"""
    name: str
    version: str
    description: str
    endpoints_count: int
    documentation_url: str


# ==================== Error Models ====================

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str]
    code: str
    timestamp: datetime


class ValidationErrorResponse(BaseModel):
    """Validation error response"""
    error: str = "Validation Error"
    details: List[Dict[str, Any]]
    code: str = "VALIDATION_ERROR"
    timestamp: datetime
