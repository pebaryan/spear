# Process Instance API Endpoints
# REST API for managing process instances

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from src.api.models import (
    InstanceCreate,
    InstanceResponse,
    InstanceListResponse,
    VariableCreate,
    VariableListResponse,
)
from src.api.storage import get_storage

router = APIRouter(prefix="/instances", tags=["Process Instances"])
logger = logging.getLogger(__name__)

# Use shared storage service
storage = get_storage()


def _to_instance_response_payload(instance: dict) -> dict:
    """Normalize storage instance payload to API response schema."""
    status = instance.get("status", "CREATED")
    completed_at = instance.get("completed_at")
    if completed_at is None and status in ["COMPLETED", "TERMINATED", "CANCELLED"]:
        completed_at = instance.get("updated_at")

    return {
        "id": instance["id"],
        "process_id": instance["process_id"],
        "process_version": instance.get("process_version", "1.0.0"),
        "status": status,
        "current_nodes": instance.get("current_nodes", []),
        "variables": instance.get("variables", {}),
        "created_at": instance.get("created_at"),
        "updated_at": instance.get("updated_at"),
        "completed_at": completed_at,
    }


@router.get("", response_model=InstanceListResponse)
async def list_instances(
    process_id: Optional[str] = Query(None, description="Filter by process ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    List all process instances.
    
    Returns a paginated list of process instances with optional filtering.
    """
    result = storage.list_instances(
        process_id=process_id,
        status=status,
        page=page,
        page_size=page_size
    )

    normalized_instances = [
        _to_instance_response_payload(instance) for instance in result["instances"]
    ]

    return InstanceListResponse(
        instances=normalized_instances,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(instance_id: str):
    """
    Get a specific process instance by ID.
    
    Returns detailed information about the instance including variables and current state.
    """
    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    return InstanceResponse(**_to_instance_response_payload(instance))


@router.post("", response_model=InstanceResponse, status_code=201)
async def create_instance(instance: InstanceCreate):
    """
    Start a new process instance.
    
    Creates and starts a new instance of the specified process with optional initial variables.
    """
    try:
        # Create instance
        result = storage.create_instance(
            process_id=instance.process_id,
            variables=instance.variables,
            start_event_id=instance.start_event_id
        )
        
        # Get full instance details
        instance_data = storage.get_instance(result["id"])
        if not instance_data:
            raise HTTPException(status_code=500, detail="Failed to create instance")
        
        return InstanceResponse(**_to_instance_response_payload(instance_data))
        
    except ValueError:
        raise HTTPException(
            status_code=404, detail="Process not found or invalid start event"
        )
    except Exception:
        logger.exception("Failed to create process instance")
        raise HTTPException(status_code=400, detail="Invalid instance creation request")


@router.post("/{instance_id}/stop", response_model=InstanceResponse)
async def stop_instance(instance_id: str, reason: str = "User request"):
    """
    Stop a running process instance.
    
    Terminates the instance with the specified reason.
    """
    try:
        result = storage.stop_instance(instance_id, reason)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
        
        instance_data = storage.get_instance(instance_id)
        
        return InstanceResponse(**_to_instance_response_payload(instance_data))
        
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")


@router.delete("/{instance_id}", status_code=204)
async def delete_instance(instance_id: str):
    """
    Delete a process instance.
    
    Removes the instance from storage (audit log may be retained).
    """
    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    # For now, just stop it (full deletion would require more logic)
    storage.stop_instance(instance_id, "Deleted via API")
    return None


# ==================== Variable Management ====================

@router.get("/{instance_id}/variables", response_model=VariableListResponse)
async def get_instance_variables(instance_id: str):
    """
    Get all variables for a process instance.
    
    Returns a dictionary of all variables and their values.
    """
    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    variables = storage.get_instance_variables(instance_id)
    
    return VariableListResponse(
        variables={
            name: {
                "name": name,
                "value": value,
                "datatype": "string",
                "updated_at": ""
            }
            for name, value in variables.items()
        }
    )


@router.put("/{instance_id}/variables/{variable_name}")
async def set_instance_variable(
    instance_id: str,
    variable_name: str,
    variable: VariableCreate
):
    """
    Set a variable on a process instance.
    
    Creates or updates a variable with the specified value.
    """
    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    success = storage.set_instance_variable(instance_id, variable_name, variable.value)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set variable")
    
    return {
        "instance_id": instance_id,
        "variable_name": variable_name,
        "value": variable.value,
        "datatype": variable.datatype
    }


@router.get("/{instance_id}/audit-log")
async def get_instance_audit_log(instance_id: str):
    """
    Get the audit log for a process instance.
    
    Returns a chronological list of all events for the instance.
    """
    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    events = storage.get_instance_audit_log(instance_id)
    
    return {
        "instance_id": instance_id,
        "events": events,
        "total_events": len(events)
    }


@router.get("/{instance_id}/statistics")
async def get_instance_statistics(instance_id: str):
    """
    Get statistics about a process instance.
    
    Returns usage and execution statistics.
    """
    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    events = storage.get_instance_audit_log(instance_id)
    
    return {
        "instance_id": instance_id,
        "process_id": instance["process_id"],
        "status": instance["status"],
        "variables_count": len(instance.get("variables", {})),
        "current_nodes": instance.get("current_nodes", []),
        "events_count": len(events),
        "created_at": instance.get("created_at"),
        "updated_at": instance.get("updated_at")
    }
