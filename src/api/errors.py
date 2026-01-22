# Error Event API Endpoints
# REST API for error handling operations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from src.api.models import (
    ErrorResponse,
    ErrorThrowRequest,
    ErrorThrowResponse,
    InstanceResponse,
)
from src.api.storage import RDFStorageService, get_storage

router = APIRouter(prefix="/errors", tags=["Error Handling"])

# Use shared storage service
storage = get_storage()


@router.post(
    "/throw",
    response_model=ErrorThrowResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Instance not found"},
        400: {"model": ErrorResponse, "description": "Invalid operation"},
    },
)
async def throw_error(request: ErrorThrowRequest):
    """
    Throw an error in a running process instance.

    This endpoint allows external injection of errors into a running process instance.
    The error will be caught by an error boundary event if one is attached to the
    current activity with a matching error code.

    Args:
        request: Error throw request containing instance_id and error_code

    Returns:
        ErrorThrowResponse with status of the error throw operation
    """
    try:
        result = storage.throw_error(
            instance_id=request.instance_id,
            error_code=request.error_code,
            error_message=request.error_message,
        )

        return ErrorThrowResponse(
            instance_id=request.instance_id,
            error_code=request.error_code,
            status=result["status"],
            caught_by_boundary_event=result.get("caught_by_boundary_event", False),
            message=result.get("message"),
        )

    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/cancel",
    response_model=InstanceResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Instance not found"},
        400: {"model": ErrorResponse, "description": "Invalid operation"},
    },
)
async def cancel_instance(
    instance_id: str = Query(..., description="The process instance ID to cancel"),
    reason: Optional[str] = Query(None, description="Reason for cancellation"),
):
    """
    Cancel a running process instance.

    This endpoint terminates a running process instance immediately, similar to
    a cancel end event in a transaction subprocess. All active tokens are consumed
    and the instance status is set to CANCELLED.

    Args:
        instance_id: The process instance ID to cancel
        reason: Optional reason for cancellation

    Returns:
        InstanceResponse with updated instance state
    """
    try:
        result = storage.cancel_instance(instance_id, reason)

        if not result:
            raise HTTPException(
                status_code=404, detail=f"Instance {instance_id} not found"
            )

        return InstanceResponse(
            id=result["id"],
            process_id=result["process_id"],
            process_version="1.0.0",
            status=result["status"],
            current_nodes=result.get("current_nodes", []),
            variables=result.get("variables", {}),
            created_at=result.get("created_at", ""),
            updated_at=result.get("updated_at", ""),
            completed_at=result.get("updated_at")
            if result["status"] in ["COMPLETED", "TERMINATED", "CANCELLED"]
            else None,
        )

    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{instance_id}/error-variables",
    responses={
        404: {"model": ErrorResponse, "description": "Instance not found"},
    },
)
async def get_instance_error_variables(instance_id: str):
    """
    Get error-related variables for a process instance.

    Returns any error-related variables stored on the instance, such as:
    - errorCode: The error code if the instance ended with an error
    - lastErrorCode: The last error code thrown via API
    - lastErrorMessage: The last error message thrown via API
    - errorNode: The node where an error end event occurred

    Args:
        instance_id: The process instance ID

    Returns:
        Dictionary of error-related variables
    """
    instance = storage.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")

    variables = instance.get("variables", {})
    error_variables = {
        "errorCode": variables.get("errorCode"),
        "lastErrorCode": variables.get("lastErrorCode"),
        "lastErrorMessage": variables.get("lastErrorMessage"),
        "errorNode": variables.get("errorNode"),
    }

    return {
        "instance_id": instance_id,
        "error_variables": {k: v for k, v in error_variables.items() if v is not None},
        "instance_status": instance["status"],
    }
