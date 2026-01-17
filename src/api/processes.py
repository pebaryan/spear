# Process Definition API Endpoints
# REST API for managing BPMN process definitions

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Optional
from datetime import datetime
from src.api.models import (
    ProcessDefinitionCreate,
    ProcessDefinitionUpdate,
    ProcessDefinitionResponse,
    ProcessDefinitionListResponse,
    ErrorResponse
)
from src.api.storage import RDFStorageService, get_storage

router = APIRouter(prefix="/processes", tags=["Process Definitions"])

# Use shared storage service
storage = get_storage()


@router.get("", response_model=ProcessDefinitionListResponse)
async def list_processes(
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    List all process definitions.
    
    Returns a paginated list of deployed BPMN processes.
    """
    result = storage.list_processes(status=status, page=page, page_size=page_size)
    return ProcessDefinitionListResponse(**result)


@router.get("/{process_id}", response_model=ProcessDefinitionResponse)
async def get_process(process_id: str):
    """
    Get a specific process definition by ID.
    
    Returns metadata and statistics about the process.
    """
    process = storage.get_process(process_id)
    if not process:
        raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
    return ProcessDefinitionResponse(**process)


@router.post("", response_model=ProcessDefinitionResponse, status_code=201)
async def create_process(process: ProcessDefinitionCreate):
    """
    Deploy a new BPMN process definition.
    
    Accepts BPMN XML content and creates a new process definition stored as RDF.
    """
    try:
        process_id = storage.deploy_process(
            name=process.name,
            description=process.description,
            bpmn_content=process.bpmn_file,
            version=process.version
        )
        
        # Return the created process
        created = storage.get_process(process_id)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create process")
        
        return ProcessDefinitionResponse(**created)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{process_id}", response_model=ProcessDefinitionResponse)
async def update_process(
    process_id: str,
    updates: ProcessDefinitionUpdate
):
    """
    Update a process definition.
    
    Can update the name, description, or status.
    """
    process = storage.get_process(process_id)
    if not process:
        raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
    
    # Apply updates
    updated = storage.update_process(
        process_id=process_id,
        name=updates.name,
        description=updates.description,
        status=updates.status.value if updates.status else None
    )
    
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update process")
    
    return ProcessDefinitionResponse(**updated)


@router.delete("/{process_id}", status_code=204)
async def delete_process(process_id: str):
    """
    Delete a process definition.
    
    Removes the process and all its RDF triples from storage.
    """
    process = storage.get_process(process_id)
    if not process:
        raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
    
    storage.delete_process(process_id)
    return None


@router.get("/{process_id}/rdf")
async def get_process_rdf(process_id: str):
    """
    Get the RDF representation of a process.
    
    Returns the raw RDF graph for the process definition.
    """
    graph = storage.get_process_graph(process_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
    
    return {
        "process_id": process_id,
        "triples": len(graph),
        "rdf": graph.serialize(format="turtle")
    }


@router.get("/{process_id}/statistics")
async def get_process_statistics(process_id: str):
    """
    Get statistics about a process.
    
    Returns usage statistics and metadata.
    """
    process = storage.get_process(process_id)
    if not process:
        raise HTTPException(status_code=404, detail=f"Process {process_id} not found")
    
    # Get instance statistics
    instances = storage.list_instances(process_id=process_id)
    
    return {
        "process_id": process_id,
        "name": process["name"],
        "rdf_triples_count": process["rdf_triples_count"],
        "total_instances": instances["total"],
        "status": process["status"],
        "deployed_at": process.get("deployed_at")
    }
